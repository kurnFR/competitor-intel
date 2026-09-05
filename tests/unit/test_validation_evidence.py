from app.schemas.ai import ExtractedPromotionItem
from app.services.validation.validator import PromotionValidator


def _item(evidence_quote: str) -> ExtractedPromotionItem:
    return ExtractedPromotionItem(
        product_name="Roma Kelapa 300g",
        evidence_quote=evidence_quote,
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
