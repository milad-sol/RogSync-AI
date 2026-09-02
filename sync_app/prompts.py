"""Fill prompt placeholders and split a single AI response into WooCommerce fields."""
import json
import re


PLACEHOLDER_KEYS = (
    "product_name",
    "brand",
    "compatibility",
    "gpu_model",
    "reference_url",
    "config_note",
    "seo_keywords",
)

_SHORT_MARKERS = re.compile(
    r"\[(?:short\s*description|توضیحات?\s*کوتاه)\]",
    re.IGNORECASE,
)
_MAIN_MARKERS = re.compile(
    r"\[(?:main\s*description|توضیحات?\s*(?:اصلی|کامل)|محتوا)\]",
    re.IGNORECASE,
)
_FENCE_RE = re.compile(r"^```(?:html|xml|markdown|md)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)
_TAG_RE = re.compile(r"<[^>]+>")

_BRAND_NAMES = ("brand", "برند", "سازنده", "manufacturer")
_COMPAT_NAMES = ("compatibility", "سازگاری", "compatible", "پلتفرم", "platform")
_GPU_NAMES = ("gpu", "vga", "گرافیک", "graphics", "video card")


def fill_placeholders(template: str, values: dict) -> str:
    """Replace {product_name}-style tokens without touching other braces."""
    text = template or ""
    for key in PLACEHOLDER_KEYS:
        text = text.replace("{" + key + "}", str(values.get(key) or ""))
    return text


def _attribute_value(attributes, names) -> str:
    wanted = tuple(name.lower() for name in names)
    for attr in attributes or []:
        if not isinstance(attr, dict):
            continue
        label = f"{attr.get('name') or ''} {attr.get('slug') or ''}".lower()
        if not any(name in label for name in wanted):
            continue
        options = attr.get("options") or []
        if isinstance(options, list):
            return "، ".join(str(item).strip() for item in options if str(item).strip())
        return str(options).strip()
    return ""


def prompt_variables(product, seo_keywords: str) -> dict:
    attributes = product.attributes if isinstance(getattr(product, "attributes", None), list) else []
    return {
        "product_name": product.title or "",
        "brand": _attribute_value(attributes, _BRAND_NAMES),
        "compatibility": _attribute_value(attributes, _COMPAT_NAMES),
        "gpu_model": _attribute_value(attributes, _GPU_NAMES),
        "reference_url": getattr(product, "source_permalink", "") or "",
        "config_note": (product.original_short_desc or "").strip(),
        "seo_keywords": seo_keywords or "",
    }


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", (text or "").strip()).strip()


def _clean_block(text: str) -> str:
    block = _strip_fences(text)
    block = re.sub(r"^(?:format|قالب)\s*:\s*", "", block, flags=re.IGNORECASE).strip()
    return block


def split_generated_content(raw: str) -> tuple[str, str]:
    """
    Split one model response into (short_description, main_description).

    Expected markers: [Short Description] and [Main Description].
    """
    text = _strip_fences(raw)
    if not text:
        return "", ""

    short_match = _SHORT_MARKERS.search(text)
    main_match = _MAIN_MARKERS.search(text)

    short = ""
    main = ""

    if short_match and main_match:
        if short_match.start() < main_match.start():
            short = text[short_match.end():main_match.start()]
            main = text[main_match.end():]
        else:
            main = text[main_match.end():short_match.start()]
            short = text[short_match.end():]
    elif main_match:
        short = text[:main_match.start()]
        main = text[main_match.end():]
        if short_match:
            short = text[short_match.end():main_match.start()]
    elif short_match:
        short = text[short_match.end():]
    else:
        main = text

    short = _clean_block(short)
    main = _clean_block(main)

    if not short and main:
        first_line, sep, rest = main.partition("\n")
        plain = _TAG_RE.sub("", first_line).strip()
        if "|" in plain and len(plain) <= 400:
            short = first_line.strip()
            main = rest.strip()

    return short, main


def build_generation_prompt(template_body: str, product, seo_keywords: str) -> str:
    filled = fill_placeholders(template_body, prompt_variables(product, seo_keywords))
    sections = [
        filled.strip(),
        "",
        "--- PRODUCT CONTEXT ---",
        f"product_name: {product.title or ''}",
    ]
    permalink = getattr(product, "source_permalink", "") or ""
    if permalink:
        sections.append(f"reference_url: {permalink}")
    if product.original_short_desc:
        sections.append("Source short description HTML:\n" + product.original_short_desc)
    if product.original_desc:
        sections.append("Source main description HTML:\n" + product.original_desc)
    if product.attributes:
        sections.append(
            "Product attributes JSON:\n"
            + json.dumps(product.attributes, ensure_ascii=False)
        )
    sections.append(
        "\nOUTPUT RULES:\n"
        "- Generate BOTH sections in a single response.\n"
        "- Put the short WooCommerce excerpt after the exact marker [Short Description].\n"
        "- Put the full HTML review after the exact marker [Main Description].\n"
        "- Do not wrap the output in markdown code fences."
    )
    return "\n".join(sections)
