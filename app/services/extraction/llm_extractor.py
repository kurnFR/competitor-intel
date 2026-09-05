import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import List, Optional

from openai import OpenAI

from app.core.config import settings
from app.schemas.ai import ExtractedPromotionItem, ExtractedPromotionBatch

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an FMCG Competitor Promotion Intelligence Extraction Engine specialized in the Indonesian market.
Your task is to analyze Indonesian retail catalog text and extract structured promotion activities for biscuits, crackers, wafers, cookies, and related snacks.

STRICT EXTRACTION RULES:
1. NEVER invent or assume prices, products, or dates. If not explicitly in the text, use null.
2. Normalize promotion mechanisms:
   - "Beli 1 Gratis 1", "B1G1", "Buy 1 Get 1" -> promotion_type = "BUY_X_GET_Y", buy_quantity = 1, free_quantity = 1
   - "Beli 2 Gratis 1", "B2G1" -> promotion_type = "BUY_X_GET_Y", buy_quantity = 2, free_quantity = 1
   - "Diskon X%", "Hemat X%", price drop -> promotion_type = "DISCOUNT"
   - "Beli 2 Rp...", "Multi-buy", "2 lebih hemat" -> promotion_type = "MULTIBUY"
   - "Khusus Member", "Member price" -> promotion_type = "MEMBER_PRICE"
   - "Cashback" -> promotion_type = "CASHBACK"
   - "Bundle", "Paket" -> promotion_type = "BUNDLE"
3. Category must be one of: BISCUIT, CRACKER, COOKIE, WAFER, SNACK, OTHER.
4. Normalize prices into numeric IDR (e.g., "Rp6.500" -> 6500, "18.900" -> 18900).
5. Normalize dates to ISO YYYY-MM-DD. If year is omitted (e.g. "Sampai 7 Sep"), use the CURRENT_DATE supplied by the caller to determine the year. Do not use a hardcoded year.
6. Provide exact quote from source in evidence_quote.
7. Return valid JSON only with structure: {"promotions": [...]}
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
Use CURRENT_DATE only to resolve the year when a source date explicitly omits its year. Never invent a missing day, month, start date, or end date.

{text_chunk}

Respond with valid JSON matching:
{{
  "promotions": [
    {{
      "product_name": "...",
      "brand": "...",
      "competitor": "...",
      "category": "BISCUIT",
      "variant": "...",
      "pack_size": "...",
      "regular_price": 10000.0,
      "promo_price": 7000.0,
      "discount_percentage": 30.0,
      "promotion_type": "DISCOUNT",
      "buy_quantity": null,
      "free_quantity": null,
      "start_date": "{extraction_date.isoformat()}",
      "end_date": null,
      "retailer": "Indomaret",
      "evidence_quote": "...",
      "confidence": 0.95
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
            batch = ExtractedPromotionBatch.model_validate(parsed)

            items: List[ExtractedPromotionItem] = []
            rejected_items: List[dict] = []
            raw_items = parsed.get("promotions", [])
            for index, item in enumerate(raw_items):
                try:
                    validated = ExtractedPromotionItem.model_validate(item)
                    items.append(validated)
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
