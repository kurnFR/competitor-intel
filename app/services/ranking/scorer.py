from datetime import datetime, timezone
from typing import Optional, Sequence, Mapping, Any


UNDATED_PENALTY = 0.85


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

    @staticmethod
    def calculate_change_impact(changes: Optional[Sequence[Mapping[str, Any]]]) -> float:
        """Score how important a newly observed promotion change is.

        The score is intentionally bounded and based on the change categories
        emitted by change_detection. Missing/unchanged fields produce no impact.
        Multiple changes accumulate with diminishing returns so a noisy document
        cannot overwhelm a genuinely material change.
        """
        if not changes:
            return 0.0

        weights = {
            "PRICE_OR_VALUE_CHANGED": 0.40,
            "MECHANIC_CHANGED": 0.35,
            "DATES_CHANGED": 0.20,
            "TERMS_CHANGED": 0.15,
        }
        impact = 0.0
        seen_fields: set[str] = set()
        for change in changes:
            field = str(change.get("field", ""))
            if field in seen_fields:
                continue
            seen_fields.add(field)
            impact += weights.get(str(change.get("event_type", "TERMS_CHANGED")), 0.15)

        return round(min(1.0, impact), 4)

    # (key, label, weight): the single definition of how a score is built. Strength is the largest single driver; recent
    # material changes carry enough weight to outrank stale, high-discount promotions.
    COMPONENTS = (
        ("strength", "Promotion strength", 0.25),
        ("reliability", "Source reliability", 0.15),
        ("freshness", "Freshness (last verified)", 0.10),
        ("relevance", "Category relevance", 0.15),
        ("importance", "Competitor importance", 0.10),
        ("confidence", "Extraction confidence", 0.10),
        ("change", "Recent change impact", 0.15),
    )

    @classmethod
    def explain(
        cls,
        promotion_type: str,
        discount_percentage: Optional[float],
        source_reliability: float,
        last_seen_at: datetime,
        category: str,
        competitor_importance: float,
        ai_confidence: float,
        *,
        change_impact: float = 0.0,
        dates_known: bool = True,
        now: Optional[datetime] = None,
    ) -> dict:
        """The score and exactly how it was built: each component's value (0-1), weight and points contributed."""
        values = {
            "strength": cls.calculate_promotion_strength(promotion_type, discount_percentage),
            "reliability": cls._bounded(source_reliability, 0.8),
            "freshness": cls.calculate_freshness(last_seen_at, now=now),
            "relevance": 1.0 if (category or "").upper() in {"BISCUIT", "CRACKER", "COOKIE", "WAFER"} else 0.8,
            "importance": cls._bounded(competitor_importance, 0.5),
            "confidence": cls._bounded(ai_confidence, 0.8),
            "change": cls._bounded(change_impact, 0.0),
        }
        components = [
            {"key": key, "label": label, "value": round(values[key], 4), "weight": weight, "points": round(values[key] * weight, 4)}
            for key, label, weight in cls.COMPONENTS
        ]
        base = sum(values[key] * weight for key, _, weight in cls.COMPONENTS)
        # Validity period could not be confirmed on the source; rank slightly lower.
        penalty = 1.0 if dates_known else UNDATED_PENALTY
        return {
            "score": round(min(1.0, max(0.0, base * penalty)), 4),
            "base": round(base, 4),
            "undated_penalty": None if dates_known else UNDATED_PENALTY,
            "components": components,
        }

    @classmethod
    def compute_total_score(cls, *args, **kwargs) -> float:
        return cls.explain(*args, **kwargs)["score"]
