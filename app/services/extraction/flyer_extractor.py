"""Multimodal Flyer Vision Extraction Engine.

Specialized for extracting structured FMCG competitor promotions from retail promotional
flyers, weekly catalogs, and JSM banner images (Indomaret, Alfamart, Superindo, etc.)
using vision-capable LLM models.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from openai import OpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai import ExtractedPromotionItem
from app.services.extraction.date_parser import (
    extract_banner_validity,
    extract_pack_size_from_name,
    parse_indonesian_date,
    parse_indonesian_date_range,
    sanitize_price,
)
from app.services.extraction.llm_extractor import ExtractionResult

logger = logging.getLogger(__name__)

FLYER_SYSTEM_PROMPT = """You are an FMCG Competitor Promotion Vision Intelligence Engine specialized in Indonesian Modern Trade retail flyers and promotional images.
Your task is to analyze Indonesian retail flyer / catalog images (such as Indomaret JSM, Alfamart Katalog Mingguan, Super Indo Koran Promo, Hypermart) and extract structured promotion activities for biscuits, crackers, wafers, cookies, and related FMCG packaged snacks.

STRICT VISUAL EXTRACTION RULES:
1. Extract ONLY facts explicitly legible in the promotional image (product title on pack or splash text, stated regular price, promo price, discount badges, valid date banner).
2. If a field is not explicitly visible or legible in the image, return null. NEVER invent prices, discounts, or dates.
3. Check header/footer date banners for validity (e.g. "Berlaku 12 - 14 Mei 2026", "Periode 1-15 Oktober", "Promo JSM 24 - 26 Juli 2026", "Katalog Super Hemat 28 Okt - 03 Nov 2026"). Provide the banner validity in "banner_date".
4. For items, convert visible validity dates to ISO "YYYY-MM-DD" if legible, or return null if items rely on the flyer banner date.
5. Normalize mechanisms:
   - "Beli 1 Gratis 1", "B1G1", "Buy 1 Get 1" -> promotion_type = "BUY_X_GET_Y", buy_quantity = 1, free_quantity = 1
   - "Beli 2 Gratis 1", "B2G1" -> promotion_type = "BUY_X_GET_Y", buy_quantity = 2, free_quantity = 1
   - "Diskon X%", "Hemat X%", price strike-through -> promotion_type = "DISCOUNT"
   - "Beli 2 Rp...", "2 Lebih Hemat" -> promotion_type = "MULTIBUY"
   - "Khusus Member", "Harga Member" -> promotion_type = "MEMBER_PRICE"
   - "Cashback" -> promotion_type = "CASHBACK"
   - "Paket Hemat", "Bundle" -> promotion_type = "BUNDLE"
6. Category must be one of: BISCUIT, CRACKER, COOKIE, WAFER, SNACK, OTHER.
7. Normalize prices into numeric IDR numbers only (e.g. "Rp 14.500" -> 14500).
8. For evidence_quote, provide the verbatim text read from the image for that item (e.g. "Oreo Vanilla 133g Rp 8.900 (Hemat 25%)").
9. geography: if a regional condition is visible (e.g. "Berlaku di Jawa & Bali", "Khusus Luar Jawa"), extract it verbatim; otherwise return null.
10. Return valid JSON only with structure:
{
  "banner_date": "12 - 14 Mei 2026",
  "promotions": [...]
}
"""


class FlyerVisionExtractor:
    """Extracts promotions from promotional flyer images using multimodal LLMs."""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or getattr(settings, "LLM_VISION_MODEL", None) or settings.LLM_MODEL
        self.client = OpenAI(
            base_url=base_url or settings.LLM_BASE_URL,
            api_key=api_key or settings.LLM_API_KEY or "dummy-key",
        )

    def extract_from_image_bytes(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        current_date: Optional[date] = None,
        source_url: Optional[str] = None,
    ) -> ExtractionResult:
        """Extract promotions from raw image bytes."""
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_data}"
        return self.extract_from_data_url(data_url, current_date=current_date, source_url=source_url)

    def extract_from_image_path(
        self,
        image_path: Union[str, Path],
        current_date: Optional[date] = None,
        source_url: Optional[str] = None,
    ) -> ExtractionResult:
        """Extract promotions from an image file on disk."""
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Flyer image not found: {path}")

        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "image/jpeg"
        image_bytes = path.read_bytes()
        return self.extract_from_image_bytes(image_bytes, mime_type=mime_type, current_date=current_date, source_url=source_url)

    def extract_from_data_url(
        self,
        data_url: str,
        current_date: Optional[date] = None,
        source_url: Optional[str] = None,
    ) -> ExtractionResult:
        """Execute multimodal vision inference on an image data URL."""
        extraction_date = current_date or date.today()
        extracted_at = datetime.now(timezone.utc)

        user_content: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"Analyze this Indonesian FMCG retail flyer image and extract all biscuit, cracker, wafer, cookie, "
                    f"and snack promotions.\n"
                    f"CURRENT_DATE: {extraction_date.isoformat()}\n"
                    f"SOURCE_REFERENCE: {source_url or 'Flyer scan'}\n"
                    "Respond with valid JSON containing the array 'promotions'."
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
        ]

        raw_response: Optional[str] = None
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": FLYER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw_response = response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("Vision model call failed for flyer extraction: %s", exc)
            return ExtractionResult(
                items=[],
                rejected_items=[{"error": str(exc), "stage": "llm_call"}],
                raw_response=raw_response,
                model=self.model,
                extracted_at=extracted_at,
                parser_status="LLM_ERROR",
            )

        return self._parse_json_payload(raw_response, extracted_at, default_year=extraction_date.year)

    def _parse_json_payload(
        self,
        raw_response: str,
        extracted_at: datetime,
        default_year: Optional[int] = None,
    ) -> ExtractionResult:
        """Parse, validate, and normalize the raw vision response."""
        try:
            cleaned = raw_response.strip()
            # If wrapped in markdown codeblock
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            payload = json.loads(cleaned)
        except Exception as exc:
            logger.warning("Failed to parse flyer vision response as JSON: %s", exc)
            return ExtractionResult(
                items=[],
                rejected_items=[{"error": str(exc), "stage": "json_decode", "raw": raw_response[:500]}],
                raw_response=raw_response,
                model=self.model,
                extracted_at=extracted_at,
                parser_status="JSON_ERROR",
            )

        # Extract flyer-wide banner validity dates if visible in payload
        banner_start, banner_end = extract_banner_validity(payload, default_year=default_year)

        raw_items = payload.get("promotions", [])
        if not isinstance(raw_items, list):
            return ExtractionResult(
                items=[],
                rejected_items=[{"error": "Key 'promotions' is not a list", "stage": "structure"}],
                raw_response=raw_response,
                model=self.model,
                extracted_at=extracted_at,
                parser_status="INVALID_STRUCTURE",
            )

        items: List[ExtractedPromotionItem] = []
        rejected: List[dict] = []

        for idx, item_data in enumerate(raw_items):
            if not isinstance(item_data, dict):
                rejected.append({"index": idx, "error": "Item is not an object", "item": item_data})
                continue

            try:
                # 1. Normalize category if invalid
                cat = str(item_data.get("category") or "OTHER").upper()
                if cat not in ("BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK", "OTHER"):
                    item_data["category"] = "OTHER"

                # 2. Date parsing and normalization
                # Check if item itself has validity_period / period / promo_period
                item_period = item_data.get("validity_period") or item_data.get("period") or item_data.get("periode") or item_data.get("promo_period")
                if item_period and isinstance(item_period, str):
                    p_start, p_end = parse_indonesian_date_range(item_period, default_year=default_year)
                    if p_start and not item_data.get("start_date"):
                        item_data["start_date"] = p_start
                    if p_end and not item_data.get("end_date"):
                        item_data["end_date"] = p_end

                # Normalize start_date if string
                start_val = item_data.get("start_date")
                if start_val and isinstance(start_val, str):
                    # Check if start_date accidentally holds a date range e.g. "12 - 14 Mei 2026"
                    if any(sep in start_val for sep in (" - ", " s/d ", " sd ", " sampai ", " -")):
                        s_iso, e_iso = parse_indonesian_date_range(start_val, default_year=default_year)
                        if s_iso:
                            item_data["start_date"] = s_iso
                        if e_iso and not item_data.get("end_date"):
                            item_data["end_date"] = e_iso
                    else:
                        s_dt = parse_indonesian_date(start_val, default_year=default_year)
                        item_data["start_date"] = s_dt.isoformat() if s_dt else None

                # Normalize end_date if string
                end_val = item_data.get("end_date")
                if end_val and isinstance(end_val, str):
                    e_dt = parse_indonesian_date(end_val, default_year=default_year)
                    item_data["end_date"] = e_dt.isoformat() if e_dt else None

                # Fallback to flyer banner validity dates if missing on the item
                if not item_data.get("start_date") and banner_start:
                    item_data["start_date"] = banner_start
                if not item_data.get("end_date") and banner_end:
                    item_data["end_date"] = banner_end

                # Fallback: check evidence_quote for date range if still missing
                if not item_data.get("end_date") and item_data.get("evidence_quote"):
                    ev_start, ev_end = parse_indonesian_date_range(item_data["evidence_quote"], default_year=default_year)
                    if ev_start and not item_data.get("start_date"):
                        item_data["start_date"] = ev_start
                    if ev_end and not item_data.get("end_date"):
                        item_data["end_date"] = ev_end

                # 3. Numeric price normalization (handle string formats like "Rp 10.500")
                for price_field in ("regular_price", "promo_price"):
                    if item_data.get(price_field) is not None:
                        item_data[price_field] = sanitize_price(item_data[price_field])

                # 4. Pack size normalization (extract from product_name if missing)
                if item_data.get("pack_size") and isinstance(item_data["pack_size"], str):
                    item_data["pack_size"] = item_data["pack_size"].strip()
                elif not item_data.get("pack_size") and item_data.get("product_name"):
                    extracted_size = extract_pack_size_from_name(item_data["product_name"])
                    if extracted_size:
                        item_data["pack_size"] = extracted_size

                # 5. Promotion type normalization
                p_type = str(item_data.get("promotion_type") or "DISCOUNT").strip().upper()
                if p_type not in ("DISCOUNT", "BUY_X_GET_Y", "MULTIBUY", "CASHBACK", "VOUCHER", "MEMBER_PRICE", "BUNDLE", "OTHER"):
                    item_data["promotion_type"] = "OTHER"
                else:
                    item_data["promotion_type"] = p_type

                parsed_item = ExtractedPromotionItem.model_validate(item_data)
                items.append(parsed_item)
            except ValidationError as err:
                rejected.append({"index": idx, "error": str(err), "item": item_data})
            except Exception as err:
                rejected.append({"index": idx, "error": f"Unexpected error: {err}", "item": item_data})

        parser_status = "SUCCESS" if items else ("EMPTY" if not rejected else "VALIDATION_FAILED")
        return ExtractionResult(
            items=items,
            rejected_items=rejected,
            raw_response=raw_response,
            model=self.model,
            extracted_at=extracted_at,
            parser_status=parser_status,
        )
