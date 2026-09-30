"""Score the LLM extraction against hand-labelled examples.

Put pairs in tests/fixtures/extraction_gold/:  name.txt (page text) and name.json (list of expected items,
each with product_name and optionally promo_price, regular_price, discount_percentage, promotion_type).

    python -m scripts.eval_extraction            # all pairs
    python -m scripts.eval_extraction --min-f1 0.8   # exit 1 if below the bar (for CI / release checks)

Label real pages from your sources; 15-30 pages give a trustworthy picture. Re-run after changing the
prompt or model to see whether quality went up or down.
"""
import argparse
import json
import sys
from pathlib import Path

from app.services.extraction.cards import split_into_cards
from app.services.extraction.evaluation import EvalReport, score_extraction
from app.services.extraction.llm_extractor import LLMExtractor

GOLD = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "extraction_gold"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-f1", type=float, default=None)
    args = parser.parse_args()

    pairs = sorted(p for p in GOLD.glob("*.txt") if p.with_suffix(".json").exists())
    if not pairs:
        print(f"No labelled examples found in {GOLD}", file=sys.stderr)
        return 2
    extractor, total = LLMExtractor(), EvalReport()
    for txt in pairs:
        expected = json.loads(txt.with_suffix(".json").read_text(encoding="utf-8"))
        cards, _ = split_into_cards(txt.read_text(encoding="utf-8"), max_cards=300)
        actual = []
        for i in range(0, len(cards), 6):
            actual += [item.model_dump() for item in extractor.extract_with_metadata("\n\n".join(cards[i:i + 6])).items]
        report = score_extraction(expected, actual)
        print(f"{txt.name}: expected={report.expected} extracted={report.extracted} matched={report.matched} "
              f"precision={report.precision:.0%} recall={report.recall:.0%}")
        for m in report.missed:
            print("   MISSED    ", m)
        for u in report.unexpected:
            print("   UNEXPECTED", u)
        total.merge(report)
    print(f"\nOVERALL precision={total.precision:.0%} recall={total.recall:.0%} F1={total.f1:.0%}")
    for name, acc in sorted(total.field_accuracy().items()):
        print(f"   {name} correct: {acc:.0%}")
    return 1 if args.min_f1 is not None and total.f1 < args.min_f1 else 0


if __name__ == "__main__":
    sys.exit(main())
