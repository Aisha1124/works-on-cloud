from decimal import Decimal

import pytest

from agents.catalog.normalize import (
    merge_drafts,
    normalise_label,
    normalise_name,
    parse_price,
    sort_variants,
    to_draft,
)
from agents.catalog.schema import (
    CatalogDraft,
    DraftProduct,
    GeminiCatalog,
    GeminiOption,
    GeminiProduct,
    GeminiSection,
    GeminiVariant,
)
from backend.models import ProductOption, Variant


def gp(name="Kuih Lapis", price=None, variants=(), options=(), unit="", confidence=0.95,
       unclear=False, unclear_reason=""):
    return GeminiProduct(
        name=name, price=price, unit=unit,
        variants=[GeminiVariant(label=lbl, price=p) for lbl, p in variants],
        options=[GeminiOption(name=n, choices=list(c)) for n, c in options],
        confidence=confidence, unclear=unclear, unclear_reason=unclear_reason,
    )


def catalog(*products, warnings=()):
    return GeminiCatalog(shop_name_guess="", sections=[GeminiSection(category="Kuih", items=list(products))],
                         warnings=list(warnings))


# --- parse_price ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$4.50", "4.50"),
        ("S$4.5", "4.50"),
        ("4.50", "4.50"),
        ("$4", "4.00"),
        ("SGD 12", "12.00"),
        ("sgd12.9", "12.90"),
        ("$1,200", "1200.00"),
        ("$ 26", "26.00"),
        ("3 for $5", "5.00"),
        ("3 for 5", "5.00"),
        ("2/$3.50", "3.50"),
        ("$.50", "0.50"),
        ("$4.50/pc", "4.50"),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == Decimal(expected)


@pytest.mark.parametrize("text", [None, "", "   ", "market price", "$", "N/A", "sold out"])
def test_parse_price_junk_is_none(text):
    assert parse_price(text) is None


# --- labels and sorting ---------------------------------------------------------


def test_normalise_label():
    assert normalise_label("20pcs") == "20 pcs"
    assert normalise_label(" 50  PCS ") == "50 pcs"
    assert normalise_label("100 pieces") == "100 pcs"
    assert normalise_label("1pc") == "1 pc"
    assert normalise_label("10 inch") == "10 inch"


def v(label, price):
    return Variant(label=label, price=Decimal(price))


def test_sort_variants_by_pack_size():
    shuffled = [v("100 pcs", "80"), v("20 pcs", "16"), v("50 pcs", "40")]
    assert [x.label for x in sort_variants(shuffled)] == ["20 pcs", "50 pcs", "100 pcs"]


def test_sort_variants_sizes_and_dimensions():
    assert [x.label for x in sort_variants([v("L", "6"), v("S", "4"), v("M", "5")])] == ["S", "M", "L"]
    assert [x.label for x in sort_variants([v("10 inch", "60"), v("7 inch", "38")])] == [
        "7 inch", "10 inch"]
    assert [x.label for x in sort_variants([v("8x8", "50"), v("7x7", "40")])] == ["7x7", "8x8"]


def test_sort_variants_keeps_menu_order_when_unparseable():
    items = [v("Party box", "50"), v("20 pcs", "16")]
    assert sort_variants(items) == items


# --- to_draft --------------------------------------------------------------------


def test_pack_pricing_becomes_sorted_variants_with_null_base_price():
    draft = to_draft(catalog(gp(variants=[("100pcs", "$80"), ("20 pcs", "$16"), ("50 PCS", "S$40")])))
    p = draft.products[0]
    assert p.base_price is None
    assert [(x.label, x.price) for x in p.variants] == [
        ("20 pcs", Decimal("16.00")), ("50 pcs", Decimal("40.00")), ("100 pcs", Decimal("80.00"))]


def test_single_pack_becomes_base_price_and_unit():
    draft = to_draft(catalog(gp(name="Mini Egg Tart", variants=[("24pcs", "$24")])))
    p = draft.products[0]
    assert p.base_price == Decimal("24.00")
    assert p.unit == "24 pcs"
    assert p.variants == []


def test_flavours_stay_options():
    draft = to_draft(catalog(gp(name="Cookies", price="$12",
                                options=[("Flavour", ["Nutella", "Red Velvet", "Oreo", "oreo"])])))
    p = draft.products[0]
    assert p.base_price == Decimal("12.00")
    assert p.variants == []
    assert p.options == [ProductOption(name="Flavour", choices=["Nutella", "Red Velvet", "Oreo"])]


def test_unreadable_price_is_null_low_confidence_and_warned():
    draft = to_draft(catalog(gp(name="Ondeh Ondeh", price=None, confidence=0.9)))
    p = draft.products[0]
    assert p.base_price is None
    assert p.confidence <= 0.4
    assert any("Ondeh Ondeh" in w and "price" in w for w in draft.warnings)


def test_unreadable_variant_price_is_dropped_not_invented():
    draft = to_draft(catalog(gp(variants=[("20 pcs", "$16"), ("50 pcs", "??"), ("100 pcs", "$80")])))
    p = draft.products[0]
    assert [x.label for x in p.variants] == ["20 pcs", "100 pcs"]
    assert p.confidence <= 0.4
    assert any("50 pcs" in w for w in draft.warnings)


def test_empty_names_are_skipped_and_categories_collected():
    draft = to_draft(catalog(gp(name="  "), gp(name="Kaya Toast", price="$2")))
    assert [p.name for p in draft.products] == ["Kaya Toast"]
    assert draft.categories == ["Kuih"]


# --- dedupe and merge ---------------------------------------------------------------


def test_normalise_name():
    assert normalise_name("  Mini Chocolate Éclair ") == "mini chocolate eclair"
    assert normalise_name("Kaya & Butter Toast!") == "kaya and butter toast"
    assert normalise_name("Mini  Chocolate-Eclair") == "mini chocolate eclair"


def dp(name, price=None, variants=(), confidence=0.9, options=()):
    return DraftProduct(
        name=name, base_price=Decimal(price) if price else None,
        variants=[v(lbl, p) for lbl, p in variants], confidence=confidence,
        options=[ProductOption(name=n, choices=list(c)) for n, c in options],
    )


def test_merge_dedupes_by_normalised_name():
    a = CatalogDraft(shop_name_guess="Sample Bakery", products=[dp("Mini Egg Tart", "24")])
    b = CatalogDraft(products=[dp("mini egg tart", "24"), dp("Mini Cream Puff", "24")])
    merged = merge_drafts([a, b])
    assert [p.name for p in merged.products] == ["Mini Egg Tart", "Mini Cream Puff"]
    assert merged.shop_name_guess == "Sample Bakery"
    assert merged.warnings == []


def test_merge_price_conflict_keeps_higher_confidence_and_warns():
    a = CatalogDraft(products=[dp("Curry Puff", "2.00", confidence=0.6)])
    b = CatalogDraft(products=[dp("Curry Puff", "2.20", confidence=0.95)])
    merged = merge_drafts([a, b])
    assert len(merged.products) == 1
    assert merged.products[0].base_price == Decimal("2.20")
    assert any("Curry Puff" in w and "different prices" in w for w in merged.warnings)


def test_merge_unions_variants_and_options():
    a = CatalogDraft(products=[dp("Kuih Lapis", variants=[("50 pcs", "40"), ("20 pcs", "16")],
                                  options=[("Flavour", ["Pandan"])])])
    b = CatalogDraft(products=[dp("Kuih Lapis", variants=[("100 pcs", "80")], confidence=0.5,
                                  options=[("Flavour", ["Pandan", "Gula Melaka"])])])
    p = merge_drafts([a, b]).products[0]
    assert [x.label for x in p.variants] == ["20 pcs", "50 pcs", "100 pcs"]
    assert p.options[0].choices == ["Pandan", "Gula Melaka"]
