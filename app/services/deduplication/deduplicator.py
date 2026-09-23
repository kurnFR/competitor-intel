import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.promotion import Promotion, PromotionEvidence, PromotionGeography
from app.models.entity import Competitor, Brand, Product, Retailer
from app.models.source import CrawlDocument
from app.models.geography import Geography
from app.schemas.ai import ExtractedPromotionItem
from app.services.validation.validator import PromotionValidator
from app.services.entity_resolution.resolver import EntityResolver, normalize_str
from app.services.ranking.scorer import PromotionScorer

logger = logging.getLogger(__name__)


class PromotionDeduplicator:
    """Reconcile observations into canonical promotions without overwriting material differences."""

    def __init__(self, db: Session):
        self.db = db
        self.resolver = EntityResolver(db)

    @staticmethod
    def _same_optional(a, b) -> bool:
        return (a or None) == (b or None)

    def _quality_passes(self, item: ExtractedPromotionItem, doc: CrawlDocument, start_dt, end_dt) -> bool:
        if doc.http_status != 200:
            return False
        if not item.evidence_quote or len(item.evidence_quote.strip()) < 8:
            return False
        if start_dt and end_dt and end_dt < start_dt:
            return False
        if not item.retailer:
            return False
        return True

    def _attach_geography(self, promotion: Promotion, geography_text: Optional[str], now: datetime) -> None:
        if not geography_text:
            return
        normalized = normalize_str(geography_text)
        geography = (
            self.db.query(Geography)
            .filter(Geography.normalized_name == normalized)
            .first()
        )
        if geography:
            self.db.add(PromotionGeography(
                promotion_id=promotion.id,
                geography_id=geography.id,
                inclusion_type="INCLUDE",
                source_text=geography_text,
                created_at=now,
            ))

    def _find_match(self, item: ExtractedPromotionItem, retailer: Optional[Retailer], start_dt, end_dt):
        norm_prod = normalize_str(item.product_name)
        candidates = self.db.query(Promotion).filter(
            Promotion.retailer_id == (retailer.id if retailer else None),
            Promotion.status.in_(["ACTIVE", "PENDING_REVIEW"]),
            Promotion.product_name.is_not(None),
        ).all()
        for ep in candidates:
            if normalize_str(ep.product_name) != norm_prod:
                continue
            if ep.promotion_type != item.promotion_type:
                continue
            if not self._same_optional(ep.channel, item.channel or (retailer.channel_type if retailer else None)):
                continue
            if not self._same_optional(ep.legacy_geography, item.geography):
                continue
            if not self._same_optional(ep.buy_quantity, item.buy_quantity):
                continue
            if not self._same_optional(ep.free_quantity, item.free_quantity):
                continue
            if not self._same_optional(ep.start_date, start_dt):
                continue
            if not self._same_optional(ep.end_date, end_dt):
                continue
            return ep
        return None

    def process_and_save(
        self,
        item: ExtractedPromotionItem,
        doc: CrawlDocument,
        observation_id=None,
        source_reliability: float = 0.85,
    ) -> Optional[Promotion]:
        is_valid, reason, start_dt, end_dt, eff_discount = PromotionValidator.validate_and_normalize(item)
        if not is_valid:
            logger.info("Skipping invalid item '%s': %s", item.product_name, reason)
            return None

        retailer = self.resolver.resolve_retailer(item.retailer)
        brand, competitor = self.resolver.resolve_brand_and_competitor(item.brand, item.product_name)
        comp_importance = competitor.importance_score if competitor else 0.5
        now = datetime.now(timezone.utc)
        quality_pass = self._quality_passes(item, doc, start_dt, end_dt)

        matched_promo = self._find_match(item, retailer, start_dt, end_dt)
        channel = item.channel or (retailer.channel_type if retailer else None)

        if matched_promo:
            matched_promo.last_seen_at = now
            matched_promo.source_reliability = max(matched_promo.source_reliability, source_reliability)
            matched_promo.ai_confidence = max(matched_promo.ai_confidence, item.confidence)
            if quality_pass:
                matched_promo.last_verified_at = now
                matched_promo.status = "ACTIVE"
            matched_promo.rank_score = PromotionScorer.compute_total_score(
                promotion_type=matched_promo.promotion_type,
                discount_percentage=matched_promo.discount_percentage,
                source_reliability=matched_promo.source_reliability,
                last_seen_at=now,
                category=matched_promo.category,
                competitor_importance=comp_importance,
                ai_confidence=matched_promo.ai_confidence,
            )
            evidence = PromotionEvidence(
                promotion_id=matched_promo.id,
                observation_id=observation_id,
                document_id=doc.id,
                evidence_type="TEXT",
                evidence_text=item.evidence_quote,
                source_url=doc.url,
                captured_at=now,
                created_at=now,
            )
            self.db.add(evidence)
            self.db.commit()
            return matched_promo

        rank_score = PromotionScorer.compute_total_score(
            promotion_type=item.promotion_type,
            discount_percentage=eff_discount,
            source_reliability=source_reliability,
            last_seen_at=now,
            category=item.category,
            competitor_importance=comp_importance,
            ai_confidence=item.confidence,
        )
        new_promo = Promotion(
            competitor_id=competitor.id if competitor else None,
            brand_id=brand.id if brand else None,
            retailer_id=retailer.id if retailer else None,
            product_name=item.product_name,
            pack_size=item.pack_size,
            category=item.category,
            regular_price=item.regular_price,
            promo_price=item.promo_price,
            currency="IDR",
            discount_percentage=eff_discount,
            promotion_type=item.promotion_type,
            buy_quantity=item.buy_quantity,
            free_quantity=item.free_quantity,
            start_date=start_dt,
            end_date=end_dt,
            channel=channel,
            legacy_geography=item.geography,
            status="ACTIVE" if quality_pass else "PENDING_REVIEW",
            source_reliability=source_reliability,
            ai_confidence=item.confidence,
            rank_score=rank_score,
            first_seen_at=now,
            last_seen_at=now,
            last_verified_at=now if quality_pass else None,
            created_at=now,
        )
        self.db.add(new_promo)
        self.db.flush()
        self._attach_geography(new_promo, item.geography, now)
        self.db.add(PromotionEvidence(
            promotion_id=new_promo.id,
            observation_id=observation_id,
            document_id=doc.id,
            evidence_type="TEXT",
            evidence_text=item.evidence_quote,
            source_url=doc.url,
            captured_at=now,
            created_at=now,
        ))
        self.db.commit()
        return new_promo
