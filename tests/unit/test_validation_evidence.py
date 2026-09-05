from app.schemas.ai import ExtractedPromotionItem
from app.services.validation.validator import PromotionValidator


def _item(evidence_quote: str, **kwargs) -> ExtractedPromotionItem:
    return ExtractedPromotionItem(
        product_name="Roma Kelapa 300g",
        evidence_quote=evidence_quote,
        **kwargs,
    )


def test_evidence_quote_must_exist_verbatim():
    item = _item("Roma Kelapa 300g Diskon 20%")
    valid, reason = PromotionValidator.validate_evidence_quote(
        item,
        "Promo hari ini: Roma Kelapa 300g Diskon 20% di Indomaret",
    )

    assert valid is True
    assert reason == "Valid"


def test_evidence_quote_rejects_invented_text():
    item = _item("Roma Kelapa 300g Diskon 50%")
    valid, reason = PromotionValidator.validate_evidence_quote(
        item,
        "Promo hari ini: Roma Kelapa 300g Diskon 20% di Indomaret",
    )

    assert valid is False
    assert reason == "Evidence quote is not present verbatim in source text"


def test_evidence_quote_requires_source_text():
    item = _item("Roma Kelapa 300g Diskon 20%")
    valid, reason = PromotionValidator.validate_evidence_quote(item, None)

    assert valid is False
    assert reason == "Missing source text for evidence verification"


def test_evidence_quote_is_case_sensitive():
    item = _item("Roma Kelapa 300g Diskon 20%")
    valid, reason = PromotionValidator.validate_evidence_quote(
        item,
        "Promo hari ini: roma kelapa 300g diskon 20% di Indomaret",
    )

    assert valid is False
    assert reason == "Evidence quote is not present verbatim in source text"


def test_date_only_end_date_is_inclusive_through_end_of_day():
    item = _item(
        "Roma Kelapa 300g Diskon 20%",
        start_date="2026-09-01",
        end_date="2026-09-05",
    )

    valid, reason, start_dt, end_dt, _ = PromotionValidator.validate_and_normalize(item)

    assert valid is True
    assert reason == "Valid"
    assert start_dt.isoformat() == "2026-09-01T00:00:00+00:00"
    assert end_dt.isoformat() == "2026-09-05T23:59:59.999999+00:00"
