from types import SimpleNamespace
from unittest.mock import MagicMock
from app.services.entity_resolution.product import resolve_product_result

def test_missing_product_is_unresolved():
    result = resolve_product_result(MagicMock(), None, None)
    assert result.status == "UNRESOLVED"

def test_missing_brand_is_review():
    result = resolve_product_result(MagicMock(), "Roma Kelapa", None)
    assert result.status == "REVIEW"
    assert result.method == "DEPENDENT"

def test_sku_match_resolves_before_name_fuzzy_match():
    product = SimpleNamespace(id="p1", brand_id="b1", sku="SKU-1", barcode=None, pack_size_value=300, pack_size_unit="g")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = product
    result = resolve_product_result(db, "Roma Kelapa", "b1", sku="SKU-1")
    assert result.status == "RESOLVED"
    assert result.method == "SKU"

def test_ambiguous_fuzzy_product_goes_to_review():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [None, None]
    db.execute.return_value.fetchall.return_value = [SimpleNamespace(id="p1", sim=0.84), SimpleNamespace(id="p2", sim=0.82)]
    result = resolve_product_result(db, "Roma Kelapa", "b1")
    assert result.status == "REVIEW"
    assert result.candidate_id == "p1"

def test_pack_size_conflict_blocks_fuzzy_auto_resolution():
    product = SimpleNamespace(id="p1", brand_id="b1", sku=None, barcode=None, pack_size_value=300, pack_size_unit="g")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [None, product]
    db.execute.return_value.fetchall.return_value = [SimpleNamespace(id="p1", sim=0.98)]
    result = resolve_product_result(db, "Roma Kelapa", "b1", pack_size="500g")
    assert result.status == "REVIEW"
    assert result.candidate_id == "p1"
