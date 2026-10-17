"""Pure post-processing for catalog extraction: prices, variants, dedupe and merge.

Everything here is deterministic Python. The model only reads text off the photo.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from agents.catalog.schema import CatalogDraft, DraftProduct, GeminiCatalog
from agents.risk.scorer import looks_like_instructions
from backend.models import ProductOption, Variant

CENT = Decimal("0.01")
LOW_CONFIDENCE = 0.4

# --- prices -------------------------------------------------------------------

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?|\.\d{1,2}"
_MULTI_BUY = re.compile(rf"^\s*\d+\s*(?:for|/)\s*(?:S\$|SGD|\$)?\s*({_NUMBER})", re.I)
_PRICE = re.compile(rf"(?:S\$|SGD|\$)?\s*({_NUMBER})", re.I)


_CLEAN_PRICE = re.compile(
    rf"^\s*(?:\d+\s*(?:for|/)\s*)?(?:S\$|SGD|\$)?\s*(?:{_NUMBER})\s*"
    r"(?:(?:/|per|each|ea\.?|nett|net|only)\s*[a-z]*\.?)?\s*$", re.I)


def is_clean_price(text: str | None) -> bool:
    """True if the printed price is just a number (with an optional $ / S$ / SGD, "3 for",
    "/pc", "each", "nett"). '$l.5O?' parses as 0.50 but is not clean: the owner should look."""
    return bool(text and _CLEAN_PRICE.match(text))


def parse_price(text: str | None) -> Decimal | None:
    """'$4.50', 'S$4.5', '4.50', 'SGD 12', '$1,200', '3 for $5' -> Decimal. Junk -> None.

    For multi-buy text like '3 for $5' this returns the price paid (5), never a per-unit
    split. The pack size belongs in the variant label.
    """
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    match = _MULTI_BUY.match(text) or _PRICE.search(text)
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    if value < 0:
        return None
    return value.quantize(CENT)


# --- variant labels and order -----------------------------------------------------

_SIZE_WORDS = {
    "xs": 0, "s": 1, "small": 1, "regular": 2, "m": 2, "medium": 2, "std": 2, "standard": 2,
    "l": 3, "large": 3, "xl": 4, "xxl": 5,
}
_PCS = re.compile(r"^\s*(\d+)\s*(?:pcs?|pieces?|pc\.?)\s*$", re.I)
_DIMENSIONS = re.compile(r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)", re.I)
_FIRST_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def normalise_label(label: str) -> str:
    """'20pcs' / '20 PCS' / '20 pieces' -> '20 pcs'; '1pc' -> '1 pc'. Other labels are only trimmed."""
    label = " ".join(label.split())
    m = _PCS.match(label)
    if not m:
        return label
    return f"{m.group(1)} pc" if m.group(1) == "1" else f"{m.group(1)} pcs"


def variant_sort_key(label: str) -> float | None:
    """A number that orders packs/sizes, or None if the label can't be ordered."""
    text = label.strip().lower()
    if text in _SIZE_WORDS:
        return float(_SIZE_WORDS[text])
    if m := _DIMENSIONS.search(text):  # "7x7" -> 49 (area)
        return float(m.group(1)) * float(m.group(2))
    if m := _FIRST_NUMBER.search(text):  # "20 pcs", "x50", "10 inch", "12-15 cups"
        return float(m.group(0))
    return None


def sort_variants(variants: list[Variant]) -> list[Variant]:
    """Sort by pack size / size. If any label can't be ordered, keep the menu's order."""
    keys = [variant_sort_key(v.label) for v in variants]
    if any(k is None for k in keys):
        return list(variants)
    return [v for _, v in sorted(zip(keys, variants), key=lambda kv: kv[0])]


# --- names --------------------------------------------------------------------


def normalise_name(name: str) -> str:
    """Key for dedupe: 'Mini Chocolate Éclair ' -> 'mini chocolate eclair'."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


# --- model output -> draft ----------------------------------------------------------


def _unique(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        item = item.strip()
        if item and item.casefold() not in {s.casefold() for s in seen}:
            seen[item] = None
    return list(seen)


INSTRUCTIONS_REASON = "Its text looks like instructions to an AI. We kept it as plain text."
MAX_REASON_LEN = 120


def _sentence(text: str) -> str:
    """Gemini's short reason as one tidy sentence: 'price smudged' -> 'Price smudged.'"""
    text = " ".join(text.split())[:MAX_REASON_LEN].rstrip(" .")
    return f"{text[:1].upper()}{text[1:]}." if text else ""


def _bad_price(printed: str | None, what: str, read_as: Decimal | None = None) -> str:
    printed = " ".join((printed or "").split())[:20]
    if not printed:
        return f"We couldn't read {what}."
    text = f'{what[:1].upper()}{what[1:]} on the photo ("{printed}") isn\'t a clear number.'
    return f"{text} We read it as ${read_as}." if read_as is not None else text


def to_draft(raw: GeminiCatalog) -> CatalogDraft:
    """Parse prices, apply the variant rules, and collect warnings."""
    warnings = [w.strip() for w in raw.warnings if w.strip()]
    products: list[DraftProduct] = []

    for category, gp in raw.items():
        name = " ".join(gp.name.split())
        if not name:
            continue
        confidence = min(max(gp.confidence, 0.0), 1.0)
        # Why the owner should check this item. Gemini's own "unclear" flag plus what Python
        # finds while parsing; whole-menu rules are added later (checks.py).
        reasons: list[str] = []
        if gp.unclear or gp.unclear_reason.strip():
            reasons.append(_sentence(gp.unclear_reason) or "Hard to read on the photo.")

        variants: list[Variant] = []
        seen_labels: set[str] = set()
        for gv in gp.variants:
            label = normalise_label(gv.label)
            price = parse_price(gv.price)
            if not label or label.casefold() in seen_labels:
                continue
            if price is None:
                warnings.append(f'{name}: could not read the price for "{label}". Please add it.')
                reasons.append(_bad_price(gv.price, f'the price for "{label}"'))
                confidence = min(confidence, LOW_CONFIDENCE)
                continue
            if not is_clean_price(gv.price):
                reasons.append(_bad_price(gv.price, f'the price for "{label}"', read_as=price))
            seen_labels.add(label.casefold())
            variants.append(Variant(label=label, price=price))

        unit = " ".join(gp.unit.split())
        base_price: Decimal | None = None
        if len(variants) == 1:
            # One pack size is just the price of the item ("24pcs $26").
            base_price = variants[0].price
            unit = unit or variants[0].label
            variants = []
        elif len(variants) >= 2:
            variants = sort_variants(variants)
        else:
            base_price = parse_price(gp.price)
            if base_price is not None and not is_clean_price(gp.price):
                reasons.append(_bad_price(gp.price, "the price", read_as=base_price))
            if base_price is None and not gp.variants:
                warnings.append(f"{name}: could not read the price. Please add it.")
                if (gp.price or "").strip():  # a missing price is a whole-menu rule (checks.py)
                    reasons.append(_bad_price(gp.price, "the price"))
                confidence = min(confidence, LOW_CONFIDENCE)

        options = [
            ProductOption(name=o.name.strip() or "Choice", choices=_unique(o.choices))
            for o in gp.options
        ]
        options = [o for o in options if o.choices]

        if gp.unclear_reason.strip():
            warnings.append(f"{name}: {gp.unclear_reason.strip()}")
        elif confidence <= LOW_CONFIDENCE and not reasons:
            reasons.append("We weren't sure we read this right.")

        # Text on the photo is data. If it reads like instructions to an AI, keep it as plain
        # text but make the owner look at it before going live.
        texts = (name, gp.local, gp.description, gp.unclear_reason)
        if any(looks_like_instructions(t) for t in texts):
            warnings.append(f"{name}: this item's text looks like instructions to an AI. We kept "
                            "it as plain text and changed nothing. Please check it.")
            reasons = [INSTRUCTIONS_REASON]  # never echo that text back as a reason
            confidence = min(confidence, LOW_CONFIDENCE)

        products.append(
            DraftProduct(
                name=name,
                name_local=gp.local.strip(),
                category=category.strip(),
                base_price=base_price,
                unit=normalise_label(unit),
                variants=variants,
                options=options,
                description=gp.description.strip(),
                confidence=round(confidence, 2),
                check_reasons=_unique(reasons),
            )
        )

    shop_name = raw.shop_name_guess.strip()
    if looks_like_instructions(shop_name):
        warnings.append("The shop name on the photo looks like instructions to an AI, so we "
                        "didn't use it. Please type your shop name.")
        shop_name = ""
    return CatalogDraft(
        shop_name_guess=shop_name,
        currency=(raw.currency.strip().upper() or "SGD")[:3],
        categories=_unique([p.category for p in products]),
        products=products,
        warnings=_unique(warnings),
    )


# --- merge several photos ---------------------------------------------------------


def _price_summary(p: DraftProduct) -> str:
    if p.variants:
        return ", ".join(f"{v.label} ${v.price}" for v in p.variants)
    return f"${p.base_price}" if p.base_price is not None else "no price"


def merge_drafts(drafts: list[CatalogDraft]) -> CatalogDraft:
    """Merge photos into one catalog. Same normalised name -> one product.

    The higher-confidence reading wins; variants and options from the other reading are
    added if missing. A price disagreement becomes a warning for the owner.
    """
    merged: dict[str, DraftProduct] = {}
    warnings: list[str] = []
    for draft in drafts:
        warnings.extend(draft.warnings)
        for product in draft.products:
            key = normalise_name(product.name)
            existing = merged.get(key)
            if existing is None:
                merged[key] = product.model_copy(deep=True)
                continue

            conflict = ""
            if _price_summary(existing) != _price_summary(product):
                conflict = (f"Read twice with different prices ({_price_summary(existing)} vs "
                            f"{_price_summary(product)}).")
                warnings.append(
                    f"{product.name} appears twice with different prices "
                    f"({_price_summary(existing)} vs {_price_summary(product)}). Please check."
                )
            keep, other = (
                (existing, product) if existing.confidence >= product.confidence
                else (product.model_copy(deep=True), existing)
            )
            keep.check_reasons = _unique(keep.check_reasons + other.check_reasons
                                         + ([conflict] if conflict else []))
            labels = {v.label.casefold() for v in keep.variants}
            extra = [v for v in other.variants if v.label.casefold() not in labels]
            if extra and keep.base_price is None:
                keep.variants = sort_variants(keep.variants + extra)
            options = {o.name.casefold(): o for o in keep.options}
            for o in other.options:
                if o.name.casefold() in options:
                    target = options[o.name.casefold()]
                    target.choices = _unique(target.choices + o.choices)
                else:
                    keep.options.append(o)
            for field in ("name_local", "category", "unit", "description"):
                if not getattr(keep, field):
                    setattr(keep, field, getattr(other, field))
            merged[key] = keep

    products = list(merged.values())
    first = drafts[0] if drafts else CatalogDraft()
    return CatalogDraft(
        shop_name_guess=next((d.shop_name_guess for d in drafts if d.shop_name_guess), ""),
        currency=first.currency,
        categories=_unique([p.category for p in products]),
        products=products,
        warnings=_unique(warnings),
    )
