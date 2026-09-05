from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.entity_resolution.resolver import EntityResolver, normalize_str


def test_normalize_str_removes_case_spacing_and_punctuation():
    assert normalize_str("  Super-Indo  ") == "superindo"


def test_retailer_missing_name_is_unresolved():
    db = MagicMock()
    result = EntityResolver(db).resolve_retailer_result(None)
    assert result.status == "UNRESOLVED"
    assert result.entity is None


def test_retailer_does_not_auto_create_unknown_entity():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.execute.return_value.fetchall.return_value = []

    result = EntityResolver(db).resolve_retailer_result("Unknown Retailer")

    assert result.status == "UNRESOLVED"
    assert result.entity is None
    db.add.assert_not_called()
    db.flush.assert_not_called()


def test_ambiguous_fuzzy_retailer_goes_to_review():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.execute.return_value.fetchall.return_value = [
        SimpleNamespace(id="a", name="Retailer A", sim=0.80),
        SimpleNamespace(id="b", name="Retailer B", sim=0.79),
    ]

    result = EntityResolver(db).resolve_retailer_result("Retailer")

    assert result.status == "REVIEW"
    assert result.entity is None
    assert result.candidate_id == "a"


def test_high_confidence_dominant_fuzzy_retailer_resolves():
    retailer = SimpleNamespace(id="a", name="Super Indo")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [None, retailer]
    db.execute.return_value.fetchall.return_value = [
        SimpleNamespace(id="a", name="Super Indo", sim=0.97),
        SimpleNamespace(id="b", name="Other", sim=0.72),
    ]

    result = EntityResolver(db).resolve_retailer_result("SuperIndo")

    assert result.status == "RESOLVED"
    assert result.method == "FUZZY"
    assert result.entity is retailer
