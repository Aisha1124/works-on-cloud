"""Evaluate the catalog agent on sample menus.

For every image in tests/eval_data/menus/ this runs the real extraction (calls Gemini),
saves the output to tests/eval_data/out/<name>.json, and, if <name>.json exists next to the
image, compares item names, prices, pack units and variant counts.

Usage:
    uv run python scripts/eval_catalog.py
    uv run python scripts/eval_catalog.py --image hawker_board
    uv run python scripts/eval_catalog.py --rescore      (re-score saved output, no API calls)
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.catalog.extract import CatalogExtractionError, extract_catalog  # noqa: E402
from agents.catalog.normalize import normalise_label, normalise_name  # noqa: E402
from agents.catalog.schema import CatalogDraft, DraftProduct  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MENUS = ROOT / "tests" / "eval_data" / "menus"
OUT = ROOT / "tests" / "eval_data" / "out"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MATCH_THRESHOLD = 0.8
NAME_WORDS_OK = 0.8  # share of expected words that must appear in the extracted English name


def name_similarity(expected: str, got: str) -> float:
    a, b = normalise_name(expected), normalise_name(got)
    score = SequenceMatcher(None, a, b).ratio()
    if a and b and (a in b or b in a):
        score = max(score, 0.9)
    return score


def name_ok(expected: str, got: str) -> bool:
    """Word-level check, so "Rose Fried Rice" is not accepted for "Petai Fried Rice".
    Each word may be fuzzy ("Asam"/"Assam")."""
    want, have = normalise_name(expected).split(), normalise_name(got).split()
    if not want or "".join(want) == "".join(have):  # "Beancurd" vs "Bean Curd"
        return True
    found = sum(
        any(SequenceMatcher(None, w, h).ratio() >= 0.75 for h in have) for w in want
    )
    return found / len(want) >= NAME_WORDS_OK


def similarity(expected: dict, got: DraftProduct) -> float:
    score = name_similarity(expected["name"], got.name)
    local_e = normalise_name(expected.get("name_local", ""))
    if local_e and local_e == normalise_name(got.name_local):
        score = 1.0
    return score


def match(expected: list[dict], got: list[DraftProduct]) -> dict[int, int]:
    """Greedy best-first one-to-one matching. Returns {expected index: got index}."""
    pairs = sorted(
        ((similarity(e, g), i, j) for i, e in enumerate(expected) for j, g in enumerate(got)),
        reverse=True,
    )
    used_e, used_g, result = set(), set(), {}
    for score, i, j in pairs:
        if score < MATCH_THRESHOLD:
            break
        if i in used_e or j in used_g:
            continue
        used_e.add(i)
        used_g.add(j)
        result[i] = j
    return result


def price_str(p: DraftProduct | None) -> str:
    if p is None:
        return ""
    if p.variants:
        return "/".join(f"{v.price.normalize():f}" for v in p.variants)
    return "null" if p.base_price is None else f"{p.base_price.normalize():f}"


def cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "~"


@dataclass
class Score:
    expected: int = 0
    got: int = 0
    matched: int = 0
    name_ok: int = 0
    price_ok: int = 0
    variants_ok: int = 0
    unit_checked: int = 0
    unit_ok: int = 0
    seconds: float = 0.0


def score_image(name: str, draft: CatalogDraft, truth: dict) -> Score:
    exp = truth["products"]
    got = draft.products
    pairs = match(exp, got)
    s = Score(expected=len(exp), got=len(got), matched=len(pairs))

    print(f"\n{'#':>3}  {'expected':34} {'got':34} {'exp $':>6} {'got $':>12} {'var':>5} {'unit':14}  result")
    print("-" * 128)
    for i, e in enumerate(exp):
        j = pairs.get(i)
        g = got[j] if j is not None else None
        problems = []
        exp_price = Decimal(e["base_price"]) if e.get("base_price") is not None else None
        var_cell = f"{e.get('variant_count', 0)}/{len(g.variants) if g else '-'}"
        unit_cell = ""
        if g is None:
            problems.append("MISSING")
        else:
            if name_ok(e["name"], g.name):
                s.name_ok += 1
            else:
                problems.append("NAME")
            if g.base_price == exp_price:
                s.price_ok += 1
            else:
                problems.append("PRICE")
            if len(g.variants) == e.get("variant_count", 0):
                s.variants_ok += 1
            else:
                problems.append("VARIANTS")
            if "unit" in e:
                s.unit_checked += 1
                unit_cell = cut(g.unit or "''", 14)
                if normalise_label(g.unit) == e["unit"]:
                    s.unit_ok += 1
                else:
                    problems.append("UNIT")
        result = "ok" if not problems else " ".join(problems)
        if e.get("check"):
            result += "  (truth unsure)"
        print(
            f"{i + 1:>3}  {cut(e['name'], 34):34} {cut(g.name if g else '-', 34):34} "
            f"{e.get('base_price') or 'null':>6} {cut(price_str(g), 12):>12} {var_cell:>5} "
            f"{unit_cell:14}  {result}"
        )

    extras = [g for j, g in enumerate(got) if j not in set(pairs.values())]
    if extras:
        print(f"\nEXTRA (extracted but not in expected file): {len(extras)}")
        for g in extras:
            print(f"   + {g.name} [{g.name_local}] {price_str(g)} conf={g.confidence}")
    return s


def summarise(name: str, s: Score, partial: bool) -> None:
    def pct(a: int, b: int) -> str:
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "-"

    print(f"\nSUMMARY {name}  ({s.seconds:.1f}s)")
    print(f"  items found (recall)     {pct(s.matched, s.expected)}")
    if not partial:
        print(f"  items correct (precision) {pct(s.matched, s.got)}")
    print(f"  English name correct     {pct(s.name_ok, s.matched)}")
    print(f"  price correct            {pct(s.price_ok, s.matched)}")
    print(f"  variant count correct    {pct(s.variants_ok, s.matched)}")
    print(f"  pack unit correct        {pct(s.unit_ok, s.unit_checked)}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="  [%(levelname)s] %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="only images whose name contains this")
    ap.add_argument("--rescore", action="store_true", help="score saved output, no API calls")
    args = ap.parse_args()

    images = sorted(p for p in MENUS.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if args.image:
        images = [p for p in images if args.image in p.stem]
    if not images:
        print(f"No images found in {MENUS}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    totals = Score()
    failures = 0
    for img in images:
        print("\n" + "=" * 128 + f"\n{img.name}\n" + "=" * 128)
        out_file = OUT / f"{img.stem}.json"
        started = time.monotonic()
        if args.rescore:
            if not out_file.exists():
                print("  no saved output; run without --rescore first")
                continue
            draft = CatalogDraft.model_validate_json(out_file.read_text(encoding="utf-8"))
        else:
            try:
                draft = extract_catalog([img.read_bytes()])
            except CatalogExtractionError as exc:
                failures += 1
                print(f"  EXTRACTION FAILED: {exc}")
                continue
            out_file.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
        elapsed = time.monotonic() - started

        print(f"shop name guess: {draft.shop_name_guess!r}   items: {len(draft.products)}   "
              f"categories: {draft.categories}")
        for w in draft.warnings:
            print(f"  warning: {w}")

        truth_file = img.with_suffix(".json")
        if not truth_file.exists():
            print("  (no expected file; output saved to", out_file.relative_to(ROOT), ")")
            continue
        truth = json.loads(truth_file.read_text(encoding="utf-8"))
        s = score_image(img.stem, draft, truth)
        s.seconds = elapsed
        summarise(img.stem, s, truth.get("partial", False))
        for f in ("seconds", "expected", "got", "matched", "name_ok", "price_ok", "variants_ok", "unit_checked", "unit_ok"):
            setattr(totals, f, getattr(totals, f) + getattr(s, f))

    if totals.expected:
        summarise("ALL", totals, partial=False)
    if failures:
        print(f"\n{failures} image(s) failed to extract.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
