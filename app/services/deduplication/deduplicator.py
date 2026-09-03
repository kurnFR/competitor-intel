import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.promotion import Promotion, PromotionEvidence
from app.models.entity import Competitor, Brand, Product, Retailer
from app.models.source import CrawlDocument
from app.schemas.ai import ExtractedPromotionItem
from app.services.validation.validator import PromotionValidator
from app.services.entity_resolution.resolver import EntityResolver, normalize_str
from app.services.ranking.scorer import PromotionScorer

logger = logging.getLogger(__name__)


class PromotionDeduplicator:
    def __init__(self, db: Session):
        self.db = db
        self.resolver = EntityResolver(db)

    def process_and_save(
        self,
        item: ExtractedPromotionItem,
        doc: CrawlDocument,
        source_reliability: float = 0.85
    ) -> Optional[Promotion]:
        # 1. Validate
        is_valid, reason, start_dt, end_dt, eff_discount = PromotionValidator.validate_and_normalize(item)
        if not is_valid:
            logger.info(f"Skipping invalid item '{item.product_name}': {reason}")
            return None

        # 2. Resolve entities
        retailer = self.resolver.resolve_retailer(item.retailer)
        brand, competitor = self.resolver.resolve_brand_and_competitor(item.brand, item.product_name)

        comp_importance = competitor.importance_score if competitor else 0.5
        now = datetime.now(timezone.utc)

        # 3. Check for existing promotion (Deduplication)
        norm_prod = normalize_str(item.product_name)
        existing = (
            self.db.query(Promotion)
            .filter(
                Promotion.retailer_id == (retailer.id if retailer else None),
                Promotion.promotion_type == item.promotion_type,
                Promotion.status == "ACTIVE"
            )
            .all()
        )

        matched_promo = None
        for ep in existing:
            if normalize_str(ep.product_name) == norm_prod or norm_prod in normalize_str(ep.product_name):
                matched_promo = ep
                break

        if matched_promo:
            # Consolidate duplicate observation: Update last_seen and attach evidence
            matched_promo.last_seen_at = now
            if item.promo_price:
                matched_promo.promo_price = item.promo_price
            if eff_discount > (matched_promo.discount_percentage or 0.0):
                matched_promo.discount_percentage = eff_discount
            if item.end_date and not matched_promo.end_date:
                matched_promo.end_date = end_dt

            # Recalculate rank score
            matched_promo.rank_score = PromotionScorer.compute_total_score(
                promotion_type=matched_promo.promotion_type,
                discount_percentage=matched_promo.discount_percentage,
                source_reliability=max(matched_promo.source_reliability, source_reliability),
                last_seen_at=now,
                category=matched_promo.category,
                competitor_importance=comp_importance,
                ai_confidence=max(matched_promo.ai_confidence, item.confidence)
            )

            # Add evidence item
            evidence = PromotionEvidence(
                promotion_id=matched_promo.id,
                document_id=doc.id,
                evidence_type="TEXT",
                evidence_text=item.evidence_quote,
                source_url=doc.url,
                captured_at=now,
                created_at=now
            )
            self.db.add(evidence)
            self.db.commit()
            return matched_promo

        # 4. Create new canonical Promotion
        rank_score = PromotionScorer.compute_total_score(
            promotion_type=item.promotion_type,
            discount_percentage=eff_discount,
            source_reliability=source_reliability,
            last_seen_at=now,
            category=item.category,
            competitor_importance=comp_importance,
            ai_confidence=item.confidence
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
            channel=retailer.channel_type if retailer else "SUPERMARKET",
            geography="Indonesia",
            status="ACTIVE",
            source_reliability=source_reliability,
            ai_confidence=item.confidence,
            rank_score=rank_score,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now
        )
        self.db.add(new_promo)
        self.db.flush()

        # Add initial evidence
        evidence = PromotionEvidence(
            promotion_id=new_promo.id,
            document_id=doc.id,
            evidence_type="TEXT",
            evidence_text=item.evidence_quote,
            source_url=doc.url,
            captured_at=now,
            created_at=now
        )
        self.db.add(evidence)
        self.db.commit()
        return new_promo
