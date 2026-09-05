import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional

from openai import OpenAI

from app.core.config import settings
from app.schemas.ai import ExtractedPromotionItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an FMCG Competitor Promotion Intelligence Extraction Engine specialized in the Indonesian market.
Your task is to analyze Indonesian retail catalog text and extract structured promotion activities for biscuits, crackers, wafers, cookies, and related snacks.

STRICT EXTRACTION RULES:
1. Extract ONLY facts explicitly supported by the supplied source text. NEVER invent or infer prices, products, brands, competitors, retailers, promotion mechanics, or dates.
2. If a field is not explicitly supported by the source text, return null. This includes start_date and end_date.
3. A crawl/retrieval date is NOT a promotion start date or end date. Never convert "today", crawl time, or CURRENT_DATE into a promotion date unless the source text explicitly establishes that date.
4. CURRENT_DATE may ONLY resolve the YEAR of an explicitly stated source date that omits its year (for example, "sampai 7 Sep"). It must never supply a missing day, month, start date, or end date.
5. Normalize promotion mechanisms:
   - "Beli 1 Gratis 1", "B1G1", "Buy 1 Get 1" -> promotion_type = "BUY_X_GET_Y", buy_quantity = 1, free_quantity = 1
   - "Beli 2 Gratis 1", "B2G1" -> promotion_type = "BUY_X_GET_Y", buy_quantity = 2, free_quantity = 1
   - "Diskon X%", "Hemat X%", price drop -> promotion_type = "DISCOUNT"
   - "Beli 2 Rp...", "Multi-buy", "2 lebih hemat" -> promotion_type = "MULTIBUY"
   - "Khusus Member", "Member price" -> promotion_type = "MEMBER_PRICE"
   - "Cashback" -> promotion_type = "CASHBACK"
   - "Bundle", "Paket" -> promotion_type = "BUNDLE"
6. Category must be one of: BISCUIT, CRACKER, COOKIE, WAFER, SNACK, OTHER. Use OTHER when the source does not support a more specific category.
7. Normalize prices into numeric IDR only when a price is explicitly present (e.g. "Rp6.500" -> 6500, "18.900" -> 18900). Do not derive a price from unrelated text.
8. Provide an exact, contiguous quote from the supplied source text in evidence_quote. The quote must support the extracted promotion; do not fabricate or paraphrase evidence.
9. Confidence must reflect evidence quality, not model certainty. Lower confidence when the source is ambiguous or incomplete.
10. Return valid JSON only with structure: {"promotions": [...]}
"""


@dataclass
class ExtractionResult:
    """Auditable result of one LLM extraction attempt."""

    items: List[ExtractedPromotionItem]
    rejected_items: List[dict]
    raw_response: Optional[str]
    model: str
    extracted_at: datetime
    parser_status: str


class LLMExtractor:
    def __init__(self):
        self.client = OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or "dummy-key"
        )
        self.model = settings.LLM_MODEL

    def extract_from_text(self, text_chunk: str, current_date: Optional[date] = None) -> List[ExtractedPromotionItem]:
        """Extract promotions while preserving the existing list-returning API."""
        return self.extract_with_metadata(text_chunk, current_date=current_date).items

    def extract_with_metadata(
        self,
        text_chunk: str,
        current_date: Optional[date] = None,
    ) -> ExtractionResult:
        """Extract promotions and return parser/validation provenance for auditability."""
        extraction_date = current_date or date.today()
        prompt = f"""Extract all FMCG biscuit, cracker, wafer, and snack promotions from the following catalog text.

CURRENT_DATE: {extraction_date.isoformat()}
Use CURRENT_DATE only to resolve the year when a source date explicitly omits its year. Never use CURRENT_DATE as a substitute for an absent promotion date.

{text_chunk}

Respond with valid JSON matching:
{{
  "promotions": [
    {{
      "product_name": "...",
      "brand": null,
      "competitor": null,
      "category": "BISCUIT",
      "variant": null,
      "pack_size": null,
      "regular_price": null,
      "promo_price": null,
      "discount_percentage": null,
      "promotion_type": "DISCOUNT",
      "buy_quantity": null,
      "free_quantity": null,
      "start_date": null,
      "end_date": null,
      "retailer": null,
      "evidence_quote": "exact source text",
      "confidence": 0.0
    }}
  ]
}}"""

        extracted_at = datetime.now(timezone.utc)
        raw_content: Optional[str] = None

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            raw_content = (response.choices[0].message.content or "").strip()
            if not raw_content:
                logger.error("LLM extraction returned an empty response")
                return ExtractionResult([], [], raw_content, self.model, extracted_at, "EMPTY_RESPONSE")

            # Strip markdown json blocks if present.
            if raw_content.startswith("```"):
                raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
                raw_content = re.sub(r"\s*```$", "", raw_content)

            parsed = json.loads(raw_content)
            if not isinstance(parsed, dict) or not isinstance(parsed.get("promotions"), list):
                logger.error("LLM extraction JSON has invalid top-level structure")
                return ExtractionResult([], [], raw_content, self.model, extracted_at, "INVALID_SCHEMA")

            items: List[ExtractedPromotionItem] = []
            rejected_items: List[dict] = []
            raw_items = parsed["promotions"]
            for index, item in enumerate(raw_items):
                if not isinstance(item, dict):
                    rejected_items.append({
                        "index": index,
                        "item": item,
                        "error": "Promotion item must be a JSON object",
                    })
                    continue
                try:
                    items.append(ExtractedPromotionItem(**item))
                except Exception as validation_error:
                    rejected_items.append({
                        "index": index,
                        "item": item,
                        "error": str(validation_error),
                    })

            logger.info(
                "LLM extraction completed: model=%s current_date=%s returned=%d accepted=%d rejected=%d",
                self.model,
                extraction_date.isoformat(),
                len(raw_items),
                len(items),
                len(rejected_items),
            )
            return ExtractionResult(
                items=items,
                rejected_items=rejected_items,
                raw_response=raw_content,
                model=self.model,
                extracted_at=extracted_at,
                parser_status="PARTIAL_SUCCESS" if rejected_items else "SUCCESS",
            )

        except json.JSONDecodeError as parse_error:
            logger.error("LLM extraction returned invalid JSON: %s", parse_error)
            return ExtractionResult([], [], raw_content, self.model, extracted_at, "INVALID_JSON")
        except Exception as error:
            logger.error("LLM extraction error: %s", error)
            return ExtractionResult([], [], raw_content, self.model, extracted_at, "ERROR")
