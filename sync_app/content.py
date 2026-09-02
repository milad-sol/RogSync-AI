"""HTML helpers for keyword-safe saves and in-post gallery images."""
import html
import re


INLINE_FIGURE_CLASS = "product-inline-image"
_FIGURE_RE = re.compile(
    rf'<figure[^>]*class=["\'][^"\']*{re.escape(INLINE_FIGURE_CLASS)}[^"\']*["\'][^>]*>.*?</figure>',
    re.IGNORECASE | re.DOTALL,
)
_MARK_RE = re.compile(r"</?mark\b[^>]*>", re.IGNORECASE)


def strip_keyword_marks(raw_html: str) -> str:
    """Remove visual keyword highlight tags before persisting content."""
    return _MARK_RE.sub("", raw_html or "")


def strip_inline_figures(raw_html: str) -> str:
    return _FIGURE_RE.sub("", raw_html or "")


def _figure_html(image: dict) -> str:
    src = html.escape((image.get("src") or "").strip(), quote=True)
    alt = html.escape((image.get("alt") or "").strip(), quote=True)
    if not src:
        return ""
    return (
        f'<figure class="{INLINE_FIGURE_CLASS}">'
        f'<img src="{src}" alt="{alt}" />'
        f"</figure>"
    )


def _usable_images(images) -> list:
    usable = []
    for item in images or []:
        if isinstance(item, dict) and (item.get("src") or "").strip():
            usable.append(item)
    return usable


def ensure_paragraphs(raw_html: str) -> str:
    """Make sure the description can receive one image after each <p>."""
    text = (raw_html or "").strip()
    if not text:
        return ""
    if re.search(r"<p[\s>]", text, re.IGNORECASE):
        return text

    normalized = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", normalized) if chunk.strip()]
    if len(chunks) <= 1:
        return f"<p>{text}</p>"
    return "".join(f"<p>{chunk}</p>" for chunk in chunks)


def embed_images_after_paragraphs(raw_html: str, images) -> str:
    """
    Place every extracted image inside the post body.

    Gallery/featured images are inserted after successive <p> tags so the
    published product HTML contains the photos, not only the WooCommerce gallery.
    Leftover images are appended at the end.
    """
    body = ensure_paragraphs(strip_inline_figures(raw_html or ""))
    photos = _usable_images(images)
    if not photos:
        return body
    if not body:
        return "".join(_figure_html(img) for img in photos)

    parts = re.split(r"(</p>)", body, flags=re.IGNORECASE)
    output = []
    photo_index = 0
    for part in parts:
        output.append(part)
        if part.lower() == "</p>" and photo_index < len(photos):
            figure = _figure_html(photos[photo_index])
            if figure:
                output.append(figure)
            photo_index += 1

    while photo_index < len(photos):
        figure = _figure_html(photos[photo_index])
        if figure:
            output.append(figure)
        photo_index += 1

    return "".join(output)
