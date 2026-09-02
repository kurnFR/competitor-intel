import json
import logging
import re
from typing import List, Optional
from datetime import datetime
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
5. Normalize dates to ISO YYYY-MM-DD. If year is omitted (e.g. "Sampai 7 Sep"), use current year 2026.
6. Provide exact quote from source in evidence_quote.
7. Return valid JSON only with structure: {"promotions": [...]}
"""


class LLMExtractor:
    def __init__(self):
        self.client = OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or "dummy-key"
        )
        self.model = settings.LLM_MODEL

    def extract_from_text(self, text_chunk: str) -> List[ExtractedPromotionItem]:
        prompt = f"""Extract all FMCG biscuit, cracker, wafer, and snack promotions from the following catalog text:

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
      "start_date": "2026-09-01",
      "end_date": "2026-09-07",
      "retailer": "Indomaret",
      "evidence_quote": "...",
      "confidence": 0.95
    }}
  ]
}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            raw_content = response.choices[0].message.content.strip()

            # Strip markdown json blocks if present
            if raw_content.startswith("```"):
                raw_content = re.sub(r"^```(?:json)?\n", "", raw_content)
                raw_content = re.sub(r"\n```$", "", raw_content)

            parsed = json.loads(raw_content)
            items = []
            for p in parsed.get("promotions", []):
                try:
                    items.append(ExtractedPromotionItem(**p))
                except Exception as ve:
                    logger.warning(f"Validation error for item {p}: {ve}")
            return items

        except Exception as e:
            logger.error(f"LLM extraction error: {e}")
            return []
