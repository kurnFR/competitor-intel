"""Conservative entity resolution for competitor intelligence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.entity import Competitor, Brand, Product, Retailer
from app.models.resolution import EntityMapping


FUZZY_AUTO_THRESHOLD = 0.92
FUZZY_REVIEW_THRESHOLD = 0.70


def normalize_str(value: Optional[str]) -> str:
    """Normalize source/canonical entity text for deterministic matching."""
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]", "", value.casefold())


@dataclass(frozen=True)
class ResolutionResult:
    """Resolution outcome suitable for automatic use or human review."""

    entity: object | None
    confidence: float
    method: str
    status: str  # RESOLVED, REVIEW, UNRESOLVED
    candidate_id: object | None = None
    reason: str | None = None


class EntityResolver:
    def __init__(self, db: Session):
        self.db = db

    def _mapping_lookup(self, entity_type: str, source_value: str) -> ResolutionResult | None:
        norm = normalize_str(source_value)
        if not norm:
            return None

        mapping = (
            self.db.query(EntityMapping)
            .filter(
                EntityMapping.entity_type == entity_type,
                func.regexp_replace(func.lower(EntityMapping.source_value), r"[^a-z0-9]", "", "g") == norm,
            )
            .first()
        )
        if not mapping:
            return None

        model = {
            "RETAILER": Retailer,
            "BRAND": Brand,
            "PRODUCT": Product,
            "COMPETITOR": Competitor,
        }.get(entity_type)
        if model is None:
            return None

        entity = self.db.query(model).filter(model.id == mapping.canonical_entity_id).first()
        if not entity:
            return ResolutionResult(
                None, 0.0, "MAPPING", "REVIEW", mapping.canonical_entity_id,
                "Alias points to a missing canonical entity",
            )
        return ResolutionResult(entity, mapping.confidence or 1.0, mapping.match_method or "MAPPING", "RESOLVED")

    def resolve_retailer_result(self, retailer_name: Optional[str]) -> ResolutionResult:
        if not retailer_name:
            return ResolutionResult(None, 0.0, "NONE", "UNRESOLVED", reason="Retailer name is missing")

        norm = normalize_str(retailer_name)
        mapped = self._mapping_lookup("RETAILER", retailer_name)
        if mapped:
            return mapped

        retailer = self.db.query(Retailer).filter(Retailer.normalized_name == norm).first()
        if retailer:
            return ResolutionResult(retailer, 1.0, "NORMALIZED", "RESOLVED")

        rows = self.db.execute(
            text("""
                SELECT id, name, similarity(normalized_name, :norm) AS sim
                FROM competitor_intel.retailers
                WHERE similarity(normalized_name, :norm) >= :threshold
                ORDER BY sim DESC
                LIMIT 2
            """),
            {"norm": norm, "threshold": FUZZY_REVIEW_THRESHOLD},
        ).fetchall()

        if not rows:
            return ResolutionResult(None, 0.0, "NONE", "UNRESOLVED", reason="No sufficiently similar canonical retailer found")

        best = float(rows[0].sim)
        second = float(rows[1].sim) if len(rows) > 1 else 0.0
        margin = best - second

        if best >= FUZZY_AUTO_THRESHOLD and margin >= 0.08:
            entity = self.db.query(Retailer).filter(Retailer.id == rows[0].id).first()
            return ResolutionResult(entity, best, "FUZZY", "RESOLVED")

        return ResolutionResult(
            None, best, "FUZZY", "REVIEW", rows[0].id,
            f"Ambiguous/insufficient fuzzy match (best={best:.3f}, second={second:.3f})",
        )

    def resolve_retailer(self, retailer_name: Optional[str]) -> Optional[Retailer]:
        """Backward-compatible API: return only automatically resolved entities."""
        result = self.resolve_retailer_result(retailer_name)
        return result.entity if result.status == "RESOLVED" else None

    def resolve_brand_and_competitor_result(
        self, brand_name: Optional[str], product_name: str
    ) -> Tuple[ResolutionResult, ResolutionResult]:
        query_text = brand_name or product_name
        if not query_text:
            empty = ResolutionResult(None, 0.0, "NONE", "UNRESOLVED", reason="Brand/product name is missing")
            return empty, empty

        mapped = self._mapping_lookup("BRAND", query_text)
        if mapped and mapped.entity is not None:
            brand = mapped.entity
            competitor = self.db.query(Competitor).filter(Competitor.id == brand.competitor_id).first()
            competitor_result = (
                ResolutionResult(competitor, 1.0, "RELATION", "RESOLVED")
                if competitor else ResolutionResult(None, 0.0, "RELATION", "REVIEW", reason="Brand has no canonical competitor")
            )
            return mapped, competitor_result

        norm = normalize_str(query_text)
        brand = self.db.query(Brand).filter(Brand.normalized_name == norm).first()
        if brand:
            competitor = self.db.query(Competitor).filter(Competitor.id == brand.competitor_id).first()
            competitor_result = (
                ResolutionResult(competitor, 1.0, "RELATION", "RESOLVED")
                if competitor else ResolutionResult(None, 0.0, "RELATION", "REVIEW", reason="Brand has no canonical competitor")
            )
            return ResolutionResult(brand, 1.0, "NORMALIZED", "RESOLVED"), competitor_result

        candidate = self.db.execute(
            text("""
                SELECT id, name, similarity(normalized_name, :norm) AS sim
                FROM competitor_intel.brands
                WHERE similarity(normalized_name, :norm) >= :threshold
                ORDER BY sim DESC
                LIMIT 2
            """),
            {"norm": norm, "threshold": FUZZY_REVIEW_THRESHOLD},
        ).fetchall()

        if candidate:
            best = float(candidate[0].sim)
            second = float(candidate[1].sim) if len(candidate) > 1 else 0.0
            margin = best - second
            if best >= FUZZY_AUTO_THRESHOLD and margin >= 0.08:
                brand = self.db.query(Brand).filter(Brand.id == candidate[0].id).first()
                competitor = self.db.query(Competitor).filter(Competitor.id == brand.competitor_id).first() if brand else None
                return (
                    ResolutionResult(brand, best, "FUZZY", "RESOLVED"),
                    ResolutionResult(competitor, best, "RELATION", "RESOLVED") if competitor else ResolutionResult(None, 0.0, "RELATION", "REVIEW", reason="Brand has no canonical competitor"),
                )
            reason = f"Ambiguous/insufficient brand match (best={best:.3f}, second={second:.3f})"
        else:
            reason = "No sufficiently similar canonical brand found"

        review = ResolutionResult(
            None,
            float(candidate[0].sim) if candidate else 0.0,
            "FUZZY",
            "REVIEW",
            candidate[0].id if candidate else None,
            reason,
        )
        return review, ResolutionResult(None, 0.0, "DEPENDENT", "REVIEW", reason="Competitor cannot be resolved until brand is resolved")

    def resolve_brand_and_competitor(
        self, brand_name: Optional[str], product_name: str
    ) -> Tuple[Optional[Brand], Optional[Competitor]]:
        """Backward-compatible API: return only automatically resolved entities."""
        brand_result, competitor_result = self.resolve_brand_and_competitor_result(brand_name, product_name)
        brand = brand_result.entity if brand_result.status == "RESOLVED" else None
        competitor = competitor_result.entity if competitor_result.status == "RESOLVED" else None
        return brand, competitor
