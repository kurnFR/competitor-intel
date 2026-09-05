"""Product-specific conservative entity resolution."""
from __future__ import annotations
from typing import Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models.entity import Product
from app.services.entity_resolution.resolver import FUZZY_AUTO_THRESHOLD, FUZZY_DOMINANCE_MARGIN, FUZZY_REVIEW_THRESHOLD, ResolutionResult, normalize_str


def resolve_product_result(db: Session, product_name: Optional[str], brand_id, *, sku: Optional[str] = None, barcode: Optional[str] = None, pack_size: Optional[str] = None) -> ResolutionResult:
    """Resolve a product only within a resolved brand; never create silently."""
    if not product_name:
        return ResolutionResult(None, 0.0, "NONE", "UNRESOLVED", reason="Product name is missing")
    if brand_id is None:
        return ResolutionResult(None, 0.0, "DEPENDENT", "REVIEW", reason="Product cannot be resolved without a canonical brand")
    if barcode:
        product = db.query(Product).filter(Product.brand_id == brand_id, Product.barcode == str(barcode).strip()).first()
        if product:
            return ResolutionResult(product, 1.0, "BARCODE", "RESOLVED")
    if sku:
        product = db.query(Product).filter(Product.brand_id == brand_id, Product.sku == str(sku).strip()).first()
        if product:
            return ResolutionResult(product, 1.0, "SKU", "RESOLVED")
    norm = normalize_str(product_name)
    product = db.query(Product).filter(Product.brand_id == brand_id, Product.normalized_name == norm).first()
    if product:
        return ResolutionResult(product, 1.0, "NORMALIZED", "RESOLVED")
    rows = db.execute(text("""
        SELECT id, name, sku, barcode, pack_size_value, pack_size_unit,
               similarity(normalized_name, :norm) AS sim
        FROM competitor_intel.products
        WHERE brand_id = :brand_id
          AND similarity(normalized_name, :norm) >= :threshold
        ORDER BY sim DESC LIMIT 2
    """), {"brand_id": brand_id, "norm": norm, "threshold": FUZZY_REVIEW_THRESHOLD}).fetchall()
    if not rows:
        return ResolutionResult(None, 0.0, "NONE", "UNRESOLVED", reason="No sufficiently similar canonical product found within resolved brand")
    best = float(rows[0].sim)
    second = float(rows[1].sim) if len(rows) > 1 else 0.0
    candidate = db.query(Product).filter(Product.id == rows[0].id).first()
    if candidate and best >= FUZZY_AUTO_THRESHOLD and best - second >= FUZZY_DOMINANCE_MARGIN:
        if pack_size and candidate.pack_size_value is not None:
            supplied = normalize_str(pack_size)
            canonical = normalize_str(f"{candidate.pack_size_value}{candidate.pack_size_unit or ''}")
            if supplied and canonical and supplied != canonical:
                return ResolutionResult(None, best, "FUZZY", "REVIEW", candidate.id, "Product name matches but explicit pack size conflicts")
        return ResolutionResult(candidate, best, "FUZZY", "RESOLVED")
    return ResolutionResult(None, best, "FUZZY", "REVIEW", rows[0].id, f"Ambiguous/insufficient product match within brand (best={best:.3f}, second={second:.3f})")
