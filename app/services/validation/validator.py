import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from app.schemas.ai import ExtractedPromotionItem

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK"}


class PromotionValidator:
    @staticmethod
    def validate_and_normalize(item: ExtractedPromotionItem) -> Tuple[bool, str, Optional[datetime], Optional[datetime], float]:
        """
        Validates an extracted promotion item.
        Returns: (is_valid, rejection_reason, start_dt, end_dt, effective_discount)
        """
        # 1. Product Name check
        if not item.product_name or len(item.product_name.strip()) < 2:
            return False, "Missing product name", None, None, 0.0

        # 2. Category Check
        category = (item.category or "BISCUIT").upper()
        if category not in VALID_CATEGORIES and "OTHER" in category:
            # Check if product text has biscuit/cracker/wafer keywords
            txt = f"{item.product_name} {item.brand or ''}".lower()
            if not any(k in txt for k in ["biskuit", "biscuit", "cracker", "kraker", "malkist", "wafer", "cookie", "kukis", "soes", "pie", "creme"]):
                return False, f"Category '{category}' outside core snack/biscuit scope", None, None, 0.0

        # 3. Date Validation
        start_dt = None
        end_dt = None
        now = datetime.now(timezone.utc)

        if item.start_date:
            try:
                start_dt = datetime.fromisoformat(item.start_date).replace(tzinfo=timezone.utc)
            except Exception:
                pass

        if item.end_date:
            try:
                end_dt = datetime.fromisoformat(item.end_date).replace(tzinfo=timezone.utc)
                # End date shouldn't be older than 3 months
                three_months_ago = now - timedelta(days=90)
                if end_dt < three_months_ago:
                    return False, f"Promotion expired over 3 months ago ({item.end_date})", None, None, 0.0
            except Exception:
                pass

        # 4. Price & Discount Validation
        effective_discount = item.discount_percentage or 0.0

        # Handle Buy X Get Y effective discount
        if item.promotion_type == "BUY_X_GET_Y":
            buy_q = item.buy_quantity or 1
            free_q = item.free_quantity or 1
            calculated_eff = (free_q / (buy_q + free_q)) * 100.0
            effective_discount = max(effective_discount, calculated_eff)

        # Consistency check: Promo price shouldn't exceed Regular price
        if item.regular_price and item.promo_price:
            if item.promo_price > item.regular_price:
                return False, f"Promo price (Rp{item.promo_price}) exceeds regular price (Rp{item.regular_price})", None, None, 0.0
            if item.regular_price > 0 and effective_discount == 0.0:
                effective_discount = round(((item.regular_price - item.promo_price) / item.regular_price) * 100.0, 2)

        return True, "Valid", start_dt, end_dt, effective_discount
