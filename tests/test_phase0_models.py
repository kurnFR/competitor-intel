from app.models import (
    SourceRegistry, SourceUrl, Geography, PromotionObservation,
    Promotion, PromotionEvidence, PromotionPriceObservation, PromotionGeography,
)


def test_phase0_models_are_registered():
    names = {
        SourceRegistry.__tablename__,
        SourceUrl.__tablename__,
        Geography.__tablename__,
        PromotionObservation.__tablename__,
        Promotion.__tablename__,
        PromotionEvidence.__tablename__,
        PromotionPriceObservation.__tablename__,
        PromotionGeography.__tablename__,
    }
    assert "source_urls" in names
    assert "promotion_observations" in names
    assert "promotion_price_observations" in names
    assert "promotion_geographies" in names


def test_money_columns_are_numeric():
    for model, fields in [
        (Promotion, ("regular_price", "promo_price", "cashback_amount", "voucher_amount")),
        (PromotionPriceObservation, ("regular_price", "promo_price", "minimum_purchase_amount")),
    ]:
        for field in fields:
            assert "NUMERIC" in str(model.__table__.c[field].type).upper()
