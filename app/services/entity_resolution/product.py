"""Product-specific conservative entity resolution."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.entity import Product
from app.services.entity_resolution.resolver import (
    FUZZY_AUTO_THRESHOLD,
    FUZZY_DOMINANCE_MARGIN,
    FUZZY_REVIEW_THRESHOLD,
    EntityResolver,
    ResolutionResult,
    normalize_str,
)


def _pack_size_conflicts(product: Product, pack_size: Optional[str]) -> bool:
    """Return True only when an explicit source pack size conflicts with canonical data."""
    if not pack_size or product.pack_size_value is None:
        return False
    supplied = normalize_str(pack_size)
    canonical = normalize_str(f"{product.pack_size_value:g}{product.pack_size_unit or ''}")
    return bool(supplied and canonical and supplied != canonical)


def _resolved_product(product: Product, method: str, confidence: float = 1.0) -> ResolutionResult:
    return ResolutionResult(product, confidence, method, "RESOLVED")


def resolve_product_result(
    db: Session,
    product_name: Optional[str],
    brand_id,
    *,
    sku: Optional[str] = None,
    barcode: Optional[str] = None,
    pack_size: Optional[str] = None,
) -> ResolutionResult:
    """Resolve a product only within a resolved brand; never create silently.

    Explicit aliases are honored only when they point to a product belonging to
    the already-resolved brand. Identifier/name matches are downgraded to review
    when an explicit source pack size contradicts canonical product data.
    """
    if not product_name:
        return ResolutionResult(None, 0.0, "NONE", "UNRESOLVED", reason="Product name is missing")
    if brand_id is None:
        return ResolutionResult(
            None, 0.0, "DEPENDENT", "REVIEW",
            reason="Product cannot be resolved without a canonical brand",
        )

    # Product aliases are useful for retailer-specific naming, but the resolved
    # product must remain inside the brand boundary supplied by the caller.
    mapped = EntityResolver(db)._mapping_lookup("PRODUCT", product_name)
    if mapped and mapped.entity is not None:
        if mapped.entity.brand_id != brand_id:
            return ResolutionResult(
                None,
                mapped.confidence,
                "MAPPING",
                "REVIEW",
                mapped.entity.id,
                "Product alias points to a product outside the resolved brand",
            )
        if _pack_size_conflicts(mapped.entity, pack_size):
            return ResolutionResult(
                None,
                mapped.confidence,
                "MAPPING",
                "REVIEW",
                mapped.entity.id,
                "Product alias matches but explicit pack size conflicts",
            )
        return _resolved_product(mapped.entity, mapped.method or "MAPPING", mapped.confidence)

    if barcode:
        product = (
            db.query(Product)
            .filter(Product.brand_id == brand_id, Product.barcode == str(barcode).strip())
            .first()
        )
        if product:
            if _pack_size_conflicts(product, pack_size):
                return ResolutionResult(
                    None, 1.0, "BARCODE", "REVIEW", product.id,
                    "Barcode matches but explicit pack size conflicts",
                )
            return _resolved_product(product, "BARCODE")

    if sku:
        product = (
            db.query(Product)
            .filter(Product.brand_id == brand_id, Product.sku == str(sku).strip())
            .first()
        )
        if product:
            if _pack_size_conflicts(product, pack_size):
                return ResolutionResult(
                    None, 1.0, "SKU", "REVIEW", product.id,
                    "SKU matches but explicit pack size conflicts",
                )
            return _resolved_product(product, "SKU")

    norm = normalize_str(product_name)
    product = (
        db.query(Product)
        .filter(Product.brand_id == brand_id, Product.normalized_name == norm)
        .first()
    )
    if product:
        if _pack_size_conflicts(product, pack_size):
            return ResolutionResult(
                None, 1.0, "NORMALIZED", "REVIEW", product.id,
                "Product name matches but explicit pack size conflicts",
            )
        return _resolved_product(product, "NORMALIZED")

    rows = db.execute(
        text("""
            SELECT id, name, sku, barcode, pack_size_value, pack_size_unit,
                   similarity(normalized_name, :norm) AS sim
            FROM competitor_intel.products
            WHERE brand_id = :brand_id
              AND similarity(normalized_name, :norm) >= :threshold
            ORDER BY sim DESC
            LIMIT 2
        """),
        {"brand_id": brand_id, "norm": norm, "threshold": FUZZY_REVIEW_THRESHOLD},
    ).fetchall()
    if not rows:
        return ResolutionResult(
            None, 0.0, "NONE", "UNRESOLVED",
            reason="No sufficiently similar canonical product found within resolved brand",
        )

    best = float(rows[0].sim)
    second = float(rows[1].sim) if len(rows) > 1 else 0.0
    candidate = db.query(Product).filter(Product.id == rows[0].id).first()
    if candidate and best >= FUZZY_AUTO_THRESHOLD and best - second >= FUZZY_DOMINANCE_MARGIN:
        if _pack_size_conflicts(candidate, pack_size):
            return ResolutionResult(
                None, best, "FUZZY", "REVIEW", candidate.id,
                "Product name matches but explicit pack size conflicts",
            )
        return _resolved_product(candidate, "FUZZY", best)

    return ResolutionResult(
        None,
        best,
        "FUZZY",
        "REVIEW",
        rows[0].id,
        f"Ambiguous/insufficient product match within brand (best={best:.3f}, second={second:.3f})",
    )
