"""Schemas for catalog extraction.

GeminiCatalog is what the model returns: prices stay as the strings printed on the menu, so
the model never does arithmetic. Python turns them into Decimal (see normalize.py) and
produces a CatalogDraft.
"""

from decimal import Decimal

from pydantic import BaseModel, Field

from backend.models import ProductOption, Variant

# --- What Gemini returns ------------------------------------------------------
# Output tokens are most of the latency (~100 tokens/s), so optional fields have defaults
# and are left out of "required": the model can omit them when empty. Items are grouped
# by section so the category isn't repeated on every item.


class GeminiVariant(BaseModel):
    label: str = Field(description='Pack or size as printed, e.g. "20 pcs", "10 inch", "L".')
    price: str | None = Field(description='Price exactly as printed, e.g. "$16". null if unreadable.')


class GeminiOption(BaseModel):
    name: str = Field(description='What the customer chooses, e.g. "Flavour", "Topping".')
    choices: list[str]


class GeminiProduct(BaseModel):
    name: str = Field(description="Clean English name, without item numbers.")
    local: str = Field(
        default="", description="Original non-English name as printed. Omit if English only."
    )
    price: str | None = Field(
        default=None,
        description="Price exactly as printed when the item has ONE price. Omit when the item "
        "has variants. null if unreadable.",
    )
    unit: str = Field(
        default="", description='What the single price buys, e.g. "24 pcs". Omit if not shown.'
    )
    variants: list[GeminiVariant] = Field(
        default_factory=list, description="Packs or sizes with their own prices. Omit if none."
    )
    options: list[GeminiOption] = Field(
        default_factory=list,
        description="Choices that don't change the price (flavours, toppings). Omit if none.",
    )
    description: str = Field(default="", description="Only if printed. Omit otherwise.")
    confidence: float = Field(ge=0, le=1, description="How sure you read this item correctly.")
    unclear: bool = Field(
        default=False,
        description="true if the name, price or pack size was hard to read. Omit if clear.",
    )
    unclear_reason: str = Field(
        default="",
        description='Short reason when unclear, e.g. "price smudged". Omit if clear.',
    )


class GeminiSection(BaseModel):
    category: str = Field(description='Section heading in English, e.g. "Rice". "" if none.')
    items: list[GeminiProduct]


class GeminiCatalog(BaseModel):
    shop_name_guess: str = Field(description="Shop name if printed, else empty.")
    currency: str = Field(default="SGD", description='ISO code. Omit for SGD.')
    sections: list[GeminiSection]
    warnings: list[str] = Field(
        default_factory=list, description="Whole-photo problems (blurry, cut off). Omit if none."
    )

    def items(self) -> list[tuple[str, GeminiProduct]]:
        """(category, product) pairs in menu order."""
        return [(sec.category, item) for sec in self.sections for item in sec.items]


# --- What the rest of the app uses --------------------------------------------


class DraftProduct(BaseModel):
    """Product fields from CLAUDE.md, without id/shop_id (added when saved)."""

    name: str
    name_local: str = ""
    category: str = ""
    base_price: Decimal | None = None
    unit: str = ""
    variants: list[Variant] = Field(default_factory=list)
    options: list[ProductOption] = Field(default_factory=list)
    available: bool = True
    description: str = ""
    confidence: float = Field(default=1.0, ge=0, le=1)
    # Why the owner should check this item (read-time reasons; see agents/catalog/checks.py).
    check_reasons: list[str] = Field(default_factory=list)


class CatalogDraft(BaseModel):
    shop_name_guess: str = ""
    currency: str = "SGD"
    categories: list[str] = Field(default_factory=list)
    products: list[DraftProduct] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
