"""Re-resolve promotions against the expanded reference data."""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.promotion import Promotion, PromotionObservation
from app.models.resolution import ReviewQueue
from app.services.entity_resolution.resolver import EntityResolver
from app.services.ranking.rescore import rescore_promotions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ReResolver")


def re_resolve():
    db: Session = SessionLocal()
    try:
        resolver = EntityResolver(db)
        promotions = db.query(Promotion).all()
        logger.info(f"Checking {len(promotions)} promotions for entity resolution...")

        updated_count = 0
        resolved_brand_count = 0
        resolved_retailer_count = 0

        for p in promotions:
            # 1. Fetch observation extracted data if available
            obs = db.query(PromotionObservation).filter(
                PromotionObservation.promotion_id == p.id
            ).order_by(PromotionObservation.observed_at.desc()).first()

            extracted = obs.extracted_json if obs and obs.extracted_json else {}
            brand_val = extracted.get("brand")
            retailer_val = extracted.get("retailer")
            prod_name = extracted.get("product_name") or p.product_name

            # 2. Resolve Brand & Competitor
            if not p.brand_id or not p.competitor_id:
                # Try with brand_val and prod_name
                brand_res, comp_res = resolver.resolve_brand_and_competitor_result(brand_val, prod_name)
                
                # If still unresolved, try parsing leading token or known brands from prod_name
                if brand_res.status != "RESOLVED" and prod_name:
                    first_word = prod_name.split()[0].strip() if prod_name.split() else ""
                    if first_word and len(first_word) >= 3:
                        bw_res, cw_res = resolver.resolve_brand_and_competitor_result(first_word, prod_name)
                        if bw_res.status == "RESOLVED":
                            brand_res, comp_res = bw_res, cw_res

                if brand_res.status == "RESOLVED" and brand_res.entity:
                    p.brand_id = brand_res.entity.id
                    if comp_res.status == "RESOLVED" and comp_res.entity:
                        p.competitor_id = comp_res.entity.id
                    updated_count += 1
                    resolved_brand_count += 1

            # 3. Resolve Retailer if missing
            if not p.retailer_id and retailer_val:
                ret_res = resolver.resolve_retailer_result(retailer_val)
                if ret_res.status == "RESOLVED" and ret_res.entity:
                    p.retailer_id = ret_res.entity.id
                    updated_count += 1
                    resolved_retailer_count += 1

        db.commit()
        logger.info(f"Promotions updated: {updated_count} (Brands resolved: {resolved_brand_count}, Retailers resolved: {resolved_retailer_count})")

        # 4. Clean up review queue for promotions that are now resolved
        now = datetime.now(timezone.utc)
        resolved_promos = {
            p.id: p for p in db.query(Promotion).filter(
                Promotion.brand_id.isnot(None),
                Promotion.competitor_id.isnot(None)
            ).all()
        }
        
        rq_items = db.query(ReviewQueue).filter(ReviewQueue.status == "PENDING").all()
        rq_cleared = 0
        for rq in rq_items:
            if rq.promotion_id in resolved_promos:
                p = resolved_promos[rq.promotion_id]
                if rq.entity_type in ("BRAND", "COMPETITOR"):
                    rq.status = "APPROVED"
                    rq.reviewed_at = now
                    rq.review_notes = "Auto-resolved via dictionary expansion"
                    rq_cleared += 1
                elif rq.entity_type == "RETAILER" and p.retailer_id is not None:
                    rq.status = "APPROVED"
                    rq.reviewed_at = now
                    rq.review_notes = "Auto-resolved via dictionary expansion"
                    rq_cleared += 1

        db.commit()
        logger.info(f"Review queue items cleared: {rq_cleared} (Remaining pending: {db.query(ReviewQueue).filter(ReviewQueue.status == 'PENDING').count()})")

        # 5. Rescore all promotions
        logger.info("Rescoring promotions...")
        rescore_promotions(db)
        logger.info("Rescoring completed successfully.")

    except Exception:
        logger.exception("Error during re-resolution")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    re_resolve()

