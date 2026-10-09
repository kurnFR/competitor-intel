"""See what would happen if this page were scanned - and save NOTHING.

    python -m scripts.dry_run page.txt                       # text file (or .html) -> real LLM extraction
    python -m scripts.dry_run page.html --retailer Indomaret # name the retailer if the page does not
    python -m scripts.dry_run page.txt --extracted items.json  # replay saved extraction output (no LLM needed)
    python -m scripts.dry_run page.txt --json

For each promotion it shows what was extracted, whether the retailer / brand / competitor / product were matched,
whether it would be new or match one already stored, and whether it would appear on the dashboard - and if not, why.
Everything runs inside a transaction that is rolled back at the end.
"""
import argparse
import json
import sys
from datetime import datetime, timezone

from app.services.dry_run import run_dry


def read_page(path: str) -> str:
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8", errors="replace").read()
    if path.lower().endswith((".html", ".htm")) or raw.lstrip().lower().startswith(("<!doctype", "<html")):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return raw


class Replay:
    """Stands in for the LLM: returns previously saved items so the rest of the pipeline can be tested without one."""

    def __init__(self, path: str):
        from app.schemas.ai import ExtractedPromotionItem
        data = json.load(open(path, encoding="utf-8"))
        self.items = [ExtractedPromotionItem(**d) for d in (data["promotions"] if isinstance(data, dict) else data)]
        self.used = False

    def extract_with_metadata(self, chunk):
        from app.services.extraction.llm_extractor import ExtractionResult
        items, self.used = ([] if self.used else self.items), True
        return ExtractionResult(items=items, rejected_items=[], raw_response="{}", model="replay",
                                extracted_at=datetime.now(timezone.utc), parser_status="SUCCESS")


def print_report(r: dict) -> None:
    s = r["summary"]
    print(f"Page: {r['page_characters']:,} characters, {len(r['batches'])} extraction batch(es)")
    print(f"The model returned {s['extracted']} promotion(s); {s['rejected']} rejected by the quality checks; "
          f"{s['stored']} would be stored; {s['would_be_shown']} would appear on the dashboard.\n")
    for rej in r["rejected"]:
        name = (rej["item"] or {}).get("product_name") if isinstance(rej["item"], dict) else rej["item"]
        print(f"  REJECTED  {name or '?'}: {rej['reason']}")
    for name in r["geography_dropped"]:
        print(f"  NOTE      location for '{name}' was not found in the page text, so it was dropped (kept as 'Not stated')")
    for n, i in enumerate(r["items"], 1):
        print(f"\n{n}. {i['product']}  [{i['outcome'].replace('_', ' ').lower()}]")
        if i["outcome"] in ("INVALID", "ERROR"):
            print(f"     {i['detail']}")
            continue
        price = " / ".join(x for x in (i["promo_price"], f"{i['discount_percentage']:g}% off" if i["discount_percentage"] else None,
                                       f"was {i['regular_price']}" if i["regular_price"] else None) if x)
        print(f"     {i['promotion_type']} | {price or 'no price'} | pack {i['pack_size'] or '-'} | valid {i['start_date'] or '?'} to {i['end_date'] or '?'}")
        print(f"     location: {i['geography'] or 'not stated'} ({i['region']}) | channel: {i['channel'] or '-'}")
        m = i["matched"]
        print(f"     matched: retailer={m['retailer']} brand={m['brand']} competitor={m['competitor']} product={m['product']}"
              f" | review items created: {i['review_items']}")
        print("     WOULD APPEAR ON THE DASHBOARD: " + ("YES" if i["shown"] else "NO"))
        for why in i["hidden_because"]:
            print(f"        - {why['label']}\n          -> {why['fix']}")
    print("\nNothing was saved.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", help="text or HTML file ('-' for stdin)")
    ap.add_argument("--retailer", help="retailer name to use when the page does not name one")
    ap.add_argument("--extracted", help="JSON file of saved extraction output (skips the LLM)")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args()
    report = run_dry(read_page(args.page), extractor=Replay(args.extracted) if args.extracted else None, retailer_name=args.retailer)
    if args.json:
        print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    else:
        print_report(report)
    return 0 if report["summary"]["stored"] or not report["summary"]["extracted"] else 1


if __name__ == "__main__":
    sys.exit(main())
