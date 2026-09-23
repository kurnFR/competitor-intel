from sqlalchemy import Numeric

from app.models.source import SourceRegistry, SourceUrl, CrawlJob
from app.models.geography import Geography
from app.models.promotion import Promotion, PromotionObservation, PromotionEvidence, PromotionGeography


def test_source_registry_has_lifecycle_and_access_state():
    assert SourceRegistry.lifecycle_status.default.arg == "CANDIDATE"
    assert SourceRegistry.access_mode.default.arg == "HTTP"
    assert SourceRegistry.access_status.default.arg == "UNKNOWN"


def test_source_url_is_first_class():
    assert SourceUrl.__tablename__ == "source_urls"
    assert "source_id" in SourceUrl.__table__.c
    assert "next_crawl_at" in SourceUrl.__table__.c


def test_crawl_job_can_reference_source_url():
    assert "source_url_id" in CrawlJob.__table__.c


def test_geography_is_relational():
    assert Geography.__tablename__ == "geographies"
    assert "parent_id" in Geography.__table__.c
    assert "geography_id" in PromotionGeography.__table__.c


def test_promotion_does_not_default_missing_geography_to_indonesia():
    assert Promotion.legacy_geography.default is None


def test_promotion_money_uses_numeric():
    for column in ("regular_price", "promo_price", "cashback_amount", "voucher_amount", "minimum_purchase_amount"):
        assert isinstance(Promotion.__table__.c[column].type, Numeric)
        assert Promotion.__table__.c[column].type.precision == 18
        assert Promotion.__table__.c[column].type.scale == 2


def test_verification_and_observation_linkage_exist():
    assert "last_verified_at" in Promotion.__table__.c
    assert "last_verified_at" in PromotionObservation.__table__.c
    assert "observation_id" in PromotionEvidence.__table__.c
