from datetime import datetime, timezone
from typing import Optional


class PromotionScorer:
    @staticmethod
    def calculate_promotion_strength(promotion_type: str, discount_percentage: Optional[float]) -> float:
        ptype = (promotion_type or "DISCOUNT").upper()
        disc = discount_percentage or 0.0

        if ptype == "BUY_X_GET_Y":
            if disc >= 50.0:  # B1G1
                return 1.00
            elif disc >= 33.0:  # B2G1
                return 0.90
            return 0.75

        if disc >= 50.0:
            return 0.95
        elif disc >= 40.0:
            return 0.85
        elif disc >= 30.0:
            return 0.75
        elif disc >= 20.0:
            return 0.60
        elif disc >= 10.0:
            return 0.40

        if ptype == "MULTIBUY":
            return 0.55
        elif ptype == "MEMBER_PRICE":
            return 0.50
        elif ptype == "BUNDLE":
            return 0.45
        elif ptype in ("CASHBACK", "VOUCHER", "GIFT_WITH_PURCHASE"):
            return 0.40

        return 0.30

    @staticmethod
    def calculate_freshness(last_seen_at: datetime) -> float:
        if not last_seen_at:
            return 0.5
        now = datetime.now(timezone.utc)
        days = (now - last_seen_at).total_seconds() / 86400.0
        if days <= 1:
            return 1.00
        elif days <= 7:
            return 0.95
        elif days <= 30:
            return 0.85
        elif days <= 60:
            return 0.70
        elif days <= 90:
            return 0.50
        return 0.0

    @classmethod
    def compute_total_score(
        cls,
        promotion_type: str,
        discount_percentage: Optional[float],
        source_reliability: float,
        last_seen_at: datetime,
        category: str,
        competitor_importance: float,
        ai_confidence: float
    ) -> float:
        strength = cls.calculate_promotion_strength(promotion_type, discount_percentage)
        freshness = cls.calculate_freshness(last_seen_at)
        relevance = 1.0 if category.upper() in {"BISCUIT", "CRACKER", "COOKIE", "WAFER"} else 0.8

        # Weighted formula from PRD & Technical Design:
        # 30% strength + 20% reliability + 15% freshness + 15% category + 10% competitor + 10% confidence
        score = (
            0.30 * strength
            + 0.20 * source_reliability
            + 0.15 * freshness
            + 0.15 * relevance
            + 0.10 * competitor_importance
            + 0.10 * ai_confidence
        )
        return round(min(1.0, max(0.0, score)), 4)
