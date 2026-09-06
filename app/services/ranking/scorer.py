from datetime import datetime, timezone
from typing import Optional


class PromotionScorer:
    @staticmethod
    def _bounded(value: Optional[float], default: float = 0.0) -> float:
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def calculate_promotion_strength(promotion_type: str, discount_percentage: Optional[float]) -> float:
        ptype = (promotion_type or "DISCOUNT").upper()
        disc = max(0.0, float(discount_percentage or 0.0))

        if ptype == "BUY_X_GET_Y":
            if disc >= 50.0:
                return 1.00
            if disc >= 33.0:
                return 0.90
            return 0.75

        if disc >= 50.0:
            return 0.95
        if disc >= 40.0:
            return 0.85
        if disc >= 30.0:
            return 0.75
        if disc >= 20.0:
            return 0.60
        if disc >= 10.0:
            return 0.40

        if ptype == "MULTIBUY":
            return 0.55
        if ptype == "MEMBER_PRICE":
            return 0.50
        if ptype == "BUNDLE":
            return 0.45
        if ptype in ("CASHBACK", "VOUCHER", "GIFT_WITH_PURCHASE"):
            return 0.40
        return 0.30

    @staticmethod
    def calculate_freshness(last_seen_at: datetime, *, now: Optional[datetime] = None) -> float:
        if not last_seen_at:
            return 0.5
        now = now or datetime.now(timezone.utc)
        if last_seen_at.tzinfo is None:
            last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        days = max(0.0, (now - last_seen_at).total_seconds() / 86400.0)
        if days <= 1:
            return 1.00
        if days <= 7:
            return 0.95
        if days <= 30:
            return 0.85
        if days <= 60:
            return 0.70
        if days <= 90:
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
        ai_confidence: float,
        *,
        now: Optional[datetime] = None,
    ) -> float:
        strength = cls.calculate_promotion_strength(promotion_type, discount_percentage)
        freshness = cls.calculate_freshness(last_seen_at, now=now)
        relevance = 1.0 if (category or "").upper() in {"BISCUIT", "CRACKER", "COOKIE", "WAFER"} else 0.8
        reliability = cls._bounded(source_reliability, 0.8)
        importance = cls._bounded(competitor_importance, 0.5)
        confidence = cls._bounded(ai_confidence, 0.8)

        score = (
            0.30 * strength
            + 0.20 * reliability
            + 0.15 * freshness
            + 0.15 * relevance
            + 0.10 * importance
            + 0.10 * confidence
        )
        return round(min(1.0, max(0.0, score)), 4)
