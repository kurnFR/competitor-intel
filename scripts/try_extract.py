"""Try the LLM extraction on a text file (or stdin) without touching the database.

    python -m scripts.try_extract page.txt

Shows what would be accepted and what would be rejected (with reasons). Needs the LLM
settings (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL) to be configured.
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.extraction.llm_extractor import LLMExtractor


def main() -> int:
    text = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    result = LLMExtractor().extract_with_metadata(text)
    print(f"status={result.parser_status} model={result.model} accepted={len(result.items)} rejected={len(result.rejected_items)}\n")
    for item in result.items:
        print("ACCEPTED", json.dumps(item.model_dump(), ensure_ascii=False, default=str))
    for rejected in result.rejected_items:
        print("REJECTED", rejected.get("error"), "|", json.dumps(rejected.get("item"), ensure_ascii=False, default=str)[:200])
    return 0 if result.parser_status in ("SUCCESS", "PARTIAL_SUCCESS") else 1


if __name__ == "__main__":
    sys.exit(main())
