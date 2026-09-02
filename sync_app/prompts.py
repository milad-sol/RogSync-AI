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

_ARABIC_YE = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "ؤ": "و", "إ": "ا", "أ": "ا"})
_TOKEN_RE = re.compile(r"[\w\u0600-\u06FF]+")
_COMPAT_NAMES = ("compatibility", "سازگاری", "compatible", "پلتفرم", "platform")
_GPU_NAMES = ("gpu", "vga", "گرافیک", "graphics", "video card")
_BRAND_NAMES = ("brand", "برند", "سازنده", "manufacturer")


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


def _norm_text(value: str) -> str:
    text = (value or "").translate(_ARABIC_YE).lower()
    text = _TAG_RE.sub(" ", text)
    return " ".join(_TOKEN_RE.findall(text))


def product_keyword_context(product) -> str:
    """Plain text used to rank keywords against this product."""
    parts = [
        getattr(product, "title", "") or "",
        getattr(product, "original_short_desc", "") or "",
        (getattr(product, "original_desc", "") or "")[:2500],
        getattr(product, "source_category_label", "") or "",
        getattr(product, "target_category_label", "") or "",
    ]
    for attr in getattr(product, "attributes", None) or []:
        if not isinstance(attr, dict):
            continue
        parts.append(attr.get("name") or "")
        options = attr.get("options") or []
        if isinstance(options, list):
            parts.extend(str(item) for item in options)
        elif options:
            parts.append(str(options))
    return _norm_text(" ".join(parts))


def keyword_relevance_score(keyword: str, context: str, title: str) -> float:
    """Higher score means the keyword belongs in this product's copy."""
    kw = _norm_text(keyword)
    if len(kw) < 2:
        return 0.0
    title_n = _norm_text(title)
    score = 0.0
    if kw in title_n:
        score += 100.0
    elif kw in context:
        score += 55.0
    kw_tokens = [tok for tok in kw.split() if len(tok) > 1]
    ctx_tokens = set(context.split())
    if kw_tokens:
        overlap = sum(1 for tok in kw_tokens if tok in ctx_tokens)
        score += 28.0 * overlap
        score += 20.0 * (overlap / len(kw_tokens))
        if overlap == len(kw_tokens) and overlap >= 2:
            score += 25.0
    if len(kw_tokens) >= 2:
        score += 4.0
    return score


def select_injection_keywords(product, candidates, limit=8) -> list[str]:
    """
    Pick the keywords that best match this product.

    `candidates` is an iterable of (word, priority) where priority is 1–3.
    High-priority generic shop terms can still pass with a weaker match.
    """
    context = product_keyword_context(product)
    title = getattr(product, "title", "") or ""
    ranked = []
    seen = set()
    for item in candidates or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            word, priority = str(item[0]).strip(), int(item[1] or 2)
        else:
            word, priority = str(item).strip(), 2
        key = _norm_text(word)
        if not word or key in seen:
            continue
        seen.add(key)
        score = keyword_relevance_score(word, context, title)
        ranked.append((score, priority, word))

    ranked.sort(key=lambda row: (-row[0], -row[1], -len(row[2])))
    selected = []
    for score, priority, word in ranked:
        if len(selected) >= limit:
            break
        product_match = score >= 40
        generic_shop = priority >= 3 and score >= 12
        medium_fit = priority >= 2 and score >= 28
        if product_match or generic_shop or medium_fit:
            selected.append(word)

    if not selected:
        selected = [word for _score, _priority, word in ranked[: min(5, len(ranked))]]
    return selected


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
        sections.append("Catalog short description:\n" + product.original_short_desc)
    if product.original_desc:
        sections.append("Catalog description HTML:\n" + product.original_desc)
    if product.attributes:
        sections.append(
            "Product attributes JSON:\n"
            + json.dumps(product.attributes, ensure_ascii=False)
        )
    sections.append(
        "\nOUTPUT RULES:\n"
        "- Generate BOTH sections in a single response.\n"
        "- Published copy MUST be 100% Persian. Latin is allowed only for technical tokens "
        "(CPU/GPU names, RAM/SSD sizes, Hz, brand/series SKUs).\n"
        "- Put the short WooCommerce excerpt after the exact marker [Short Description].\n"
        "- Put the full HTML product page after the exact marker [Main Description].\n"
        "- Do not wrap the output in markdown code fences.\n"
        "- {seo_keywords} is already filtered for this product. Inject every remaining term "
        "as natural Persian phrasing (once or twice each), never as a comma list, never stacked, "
        "and never inside the short specification line."
    )
    return "\n".join(sections)
