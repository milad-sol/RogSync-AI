"""Build unique, name-based SKUs for the destination WooCommerce store."""
import re
import unicodedata

_TYPE_PHRASES = (
    (("لپ تاپ", "لپ‌تاپ", "لپتاپ", "laptop", "notebook"), "lpt"),
    (("گوشی", "موبایل", "smartphone", "iphone"), "mob"),
    (("هدست", "هدفون", "headset", "headphone"), "hst"),
    (("دسته بازی", "گیم‌پد", "controller", "gamepad"), "ctl"),
    (("مانیتور", "monitor"), "mon"),
    (("کیبورد", "keyboard"), "kbd"),
    (("ماوس", "mouse"), "mou"),
    (("کنسول", "playstation", "xbox", "nintendo"), "csl"),
    (("تبلت", "tablet", "ipad"), "tbl"),
    (("ساعت", "watch"), "wch"),
    (("شارژر", "charger"), "chg"),
    (("کابل", "cable"), "cbl"),
)

_LETTER_MAP = {
    "ا": "a", "آ": "a", "ب": "b", "پ": "p", "ت": "t", "ث": "s",
    "ج": "j", "چ": "c", "ح": "h", "خ": "k", "د": "d", "ذ": "z",
    "ر": "r", "ز": "z", "ژ": "z", "س": "s", "ش": "s", "ص": "s",
    "ض": "z", "ط": "t", "ظ": "z", "ع": "a", "غ": "g", "ف": "f",
    "ق": "q", "ک": "k", "ك": "k", "گ": "g", "ل": "l", "م": "m",
    "ن": "n", "و": "v", "ه": "h", "ی": "i", "ي": "i", "ء": "",
    "ئ": "i", "ؤ": "v", "ة": "h",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_VOWELS = set("aeiou")


def _fold(text: str) -> str:
    text = (text or "").replace("\u200c", " ")
    return " ".join(text.lower().split())


def transliterate(text: str) -> str:
    chars = [_LETTER_MAP.get(ch, ch) for ch in _fold(text)]
    latin = "".join(chars)
    return unicodedata.normalize("NFKD", latin).encode("ascii", "ignore").decode("ascii")


def latin_tokens(text: str) -> list[str]:
    return [tok for tok in _NON_ALNUM.split(transliterate(text)) if tok]


def consonant_code(word: str, size=3) -> str:
    word = re.sub(r"[^a-z0-9]", "", (word or "").lower())
    if not word:
        return "prd"[:size]
    cons = [c for c in word if c not in _VOWELS and not c.isdigit()]
    body = "".join(cons) if cons else word
    return (body + word)[:size].ljust(size, "x")


def sku_stem(title: str) -> str:
    """Short Latin stem from the product name, e.g. لپ تاپ → lpt."""
    folded = _fold(title)
    latin_folded = transliterate(folded)
    for aliases, stem in _TYPE_PHRASES:
        for alias in aliases:
            if alias in folded or alias in latin_folded:
                return stem
    tokens = latin_tokens(title)
    if not tokens:
        return "prd"
    return consonant_code("".join(tokens[:2]), 3)


def sanitize_sku(sku: str) -> str:
    cleaned = _NON_ALNUM.sub("-", (sku or "").lower()).strip("-")
    return (cleaned or "prd")[:80]


def unique_sku(base: str, taken: set[str], extra="") -> str:
    candidate = sanitize_sku(base)
    if candidate not in taken:
        taken.add(candidate)
        return candidate
    if extra:
        candidate = sanitize_sku(f"{base}-{extra}")
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    index = 2
    while True:
        candidate = sanitize_sku(f"{base}-{index}")
        if candidate not in taken:
            taken.add(candidate)
            return candidate
        index += 1


def name_code(token: str, size=3) -> str:
    token = re.sub(r"[^a-z0-9]", "", (token or "").lower())
    if not token:
        return ""
    if any(ch.isdigit() for ch in token):
        return token[:6]
    if len(token) <= size:
        return token
    cons = [ch for ch in token if ch not in _VOWELS]
    if len(cons) >= size:
        return "".join(cons[:size])
    return token[:size]


def product_sku(title: str, source_id: int, taken: set[str], source_sku="") -> str:
    """Keep the source SKU when present; otherwise build one from the title."""
    source_sku = (source_sku or "").strip()
    if source_sku:
        taken.add(source_sku)
        return source_sku
    stem = sku_stem(title)
    remaining = _fold(title)
    latin_remaining = transliterate(remaining)
    for aliases, alias_stem in _TYPE_PHRASES:
        if alias_stem != stem:
            continue
        for alias in sorted(aliases, key=len, reverse=True):
            remaining = remaining.replace(alias, " ")
            latin_remaining = latin_remaining.replace(alias, " ")
        break
    extras = []
    for token in latin_tokens(remaining) or latin_tokens(latin_remaining):
        code = name_code(token, 3)
        if code and code != stem:
            extras.append(code)
        if len(extras) == 2:
            break
    base = "-".join([stem] + extras)
    return unique_sku(base, taken, extra=str(source_id))


def _option_code(option: str) -> str:
    raw = "".join(latin_tokens(option)) or re.sub(r"[^a-z0-9]", "", option.lower())
    if not raw:
        return ""
    if any(ch.isdigit() for ch in raw):
        return re.sub(r"[^a-z0-9]", "", raw)[:6]
    return consonant_code(raw, 3)


def variation_sku(parent_sku: str, variation: dict, taken: set[str]) -> str:
    existing = (variation.get("sku") or "").strip() if isinstance(variation, dict) else ""
    if existing:
        taken.add(existing)
        return existing
    parts = [parent_sku]
    for attr in (variation or {}).get("attributes") or []:
        if not isinstance(attr, dict):
            continue
        code = _option_code((attr.get("option") or "").strip())
        if code:
            parts.append(code)
    extra = (variation or {}).get("id") or ""
    return unique_sku("-".join(parts), taken, extra=str(extra))


def release_skus(product, taken: set[str]) -> None:
    """Drop a product's current SKUs so a re-fetch can reclaim the same codes."""
    if product is None:
        return
    sku = (getattr(product, "target_sku", "") or "").strip()
    if sku:
        taken.discard(sku)
    for item in getattr(product, "variations_data", None) or []:
        if isinstance(item, dict):
            value = (item.get("sku") or "").strip()
            if value:
                taken.discard(value)


def collect_taken_skus(exclude_pk=None) -> set[str]:
    from .models import ProductSync

    qs = ProductSync.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    taken = set()
    for sku, variations in qs.values_list("target_sku", "variations_data"):
        if sku:
            taken.add(sku.strip())
        for item in variations or []:
            if isinstance(item, dict):
                value = (item.get("sku") or "").strip()
                if value:
                    taken.add(value)
    return taken


def assign_skus(product, taken=None, source_sku="") -> set[str]:
    """Fill empty product and variation SKUs. Mutates the product instance."""
    if taken is None:
        taken = collect_taken_skus(exclude_pk=getattr(product, "pk", None))
    current = (getattr(product, "target_sku", "") or "").strip()
    if current:
        taken.add(current)
        product.target_sku = current
    else:
        product.target_sku = product_sku(
            product.title,
            product.source_id,
            taken,
            source_sku=source_sku,
        )
    rows = []
    changed = False
    for item in product.variations_data or []:
        if not isinstance(item, dict):
            rows.append(item)
            continue
        row = dict(item)
        new_sku = variation_sku(product.target_sku, row, taken)
        if row.get("sku") != new_sku:
            row["sku"] = new_sku
            changed = True
        else:
            row["sku"] = new_sku
        rows.append(row)
    if rows or product.variations_data:
        product.variations_data = rows
    return taken
