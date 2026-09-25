import logging
from datetime import date, datetime, time, timezone
from typing import Tuple, Optional
from app.schemas.ai import ExtractedPromotionItem

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK"}
VALID_PROMOTION_TYPES = {
    "DISCOUNT", "BUY_X_GET_Y", "MULTIBUY", "CASHBACK", "VOUCHER",
    "MEMBER_PRICE", "BUNDLE", "OTHER",
}


class PromotionValidator:
    @staticmethod
    def _parse_date(value: Optional[str], *, end_of_day_for_date_only: bool = False) -> Tuple[Optional[datetime], Optional[str]]:
        if not value:
            return None, None
        raw = value.strip()
        if not raw:
            return None, None
        try:
            parsed_date = date.fromisoformat(raw)
            if end_of_day_for_date_only:
                parsed = datetime.combine(parsed_date, time.max, tzinfo=timezone.utc)
            else:
                parsed = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
            return parsed, None
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed, None
        except ValueError:
            return None, f"Invalid date format: {value}"

    @staticmethod
    def validate_evidence_quote(item: ExtractedPromotionItem, raw_text: Optional[str]) -> Tuple[bool, str]:
        evidence = (item.evidence_quote or "").strip()
        source = raw_text or ""
        if not evidence:
            return False, "Missing evidence quote"
        if not source:
            return False, "Missing source text for evidence verification"
        if evidence not in source:
            return False, "Evidence quote is not present verbatim in source text"
        return True, "Valid"

    @staticmethod
    def validate_and_normalize(
        item: ExtractedPromotionItem,
    ) -> Tuple[bool, str, Optional[datetime], Optional[datetime], Optional[float]]:
        """Validate without fabricating a missing discount value."""
        if not item.product_name or len(item.product_name.strip()) < 2:
            return False, "Missing product name", None, None, None

        category = (item.category or "BISCUIT").strip().upper()
        if category not in VALID_CATEGORIES:
            txt = f"{item.product_name} {item.brand or ''}".lower()
            if category != "OTHER" or not any(k in txt for k in [
                "biskuit", "biscuit", "cracker", "kraker", "malkist", "wafer", "cookie", "kukis", "soes", "pie", "creme",
            ]):
                return False, f"Category '{category}' outside core snack/biscuit scope", None, None, None

        promotion_type = (item.promotion_type or "DISCOUNT").strip().upper()
        if promotion_type not in VALID_PROMOTION_TYPES:
            return False, f"Unsupported promotion type: {promotion_type}", None, None, None

        start_dt, start_error = PromotionValidator._parse_date(item.start_date)
        if start_error:
            return False, start_error, None, None, None
        end_dt, end_error = PromotionValidator._parse_date(item.end_date, end_of_day_for_date_only=True)
        if end_error:
            return False, end_error, None, None, None
        if start_dt and end_dt and end_dt < start_dt:
            return False, "Promotion end date is before start date", None, None, None

        effective_discount = None if item.discount_percentage is None else float(item.discount_percentage)
        if effective_discount is not None and (effective_discount < 0 or effective_discount > 100):
            return False, "Discount percentage must be between 0 and 100", None, None, None

        if promotion_type == "BUY_X_GET_Y":
            buy_q = item.buy_quantity
            free_q = item.free_quantity
            if not buy_q or buy_q <= 0 or not free_q or free_q <= 0:
                return False, "BUY_X_GET_Y requires positive buy and free quantities", None, None, None
            calculated_eff = (free_q / (buy_q + free_q)) * 100.0
            effective_discount = max(effective_discount or 0.0, calculated_eff)

        regular_price = item.regular_price
        promo_price = item.promo_price
        if regular_price is not None and regular_price < 0:
            return False, "Regular price cannot be negative", None, None, None
        if promo_price is not None and promo_price < 0:
            return False, "Promo price cannot be negative", None, None, None
        if regular_price is not None and promo_price is not None:
            if regular_price == 0 and promo_price > 0:
                return False, "Promo price cannot exceed a zero regular price", None, None, None
            if promo_price > regular_price:
                return False, f"Promo price (Rp{promo_price}) exceeds regular price (Rp{regular_price})", None, None, None
            if regular_price > 0 and effective_discount is None:
                effective_discount = round(((regular_price - promo_price) / regular_price) * 100.0, 2)

        if effective_discount is not None and (effective_discount < 0 or effective_discount > 100):
            return False, "Effective discount must be between 0 and 100", None, None, None

        return True, "Valid", start_dt, end_dt, round(effective_discount, 2) if effective_discount is not None else None
