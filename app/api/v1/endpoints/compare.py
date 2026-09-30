"""Own-product price list and comparison against competitor promotions."""
import csv
import io
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.deps import Principal, client_ip, require_role
from app.db.session import get_db
from app.models.own_product import OwnProduct
from app.services import auth as auth_service
from app.services.comparison import build_comparison, parse_pack_grams, parse_price

router = APIRouter()
CATEGORIES = ("BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK")
MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 1000


class OwnProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brand: Optional[str] = Field(default=None, max_length=120)
    sku: Optional[str] = Field(default=None, max_length=64)
    category: str = "BISCUIT"
    pack_size: Optional[str] = Field(default=None, max_length=50)
    regular_price: float = Field(gt=0, lt=10_000_000)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
        return v


class OwnProductPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    brand: Optional[str] = Field(default=None, max_length=120)
    sku: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = None
    pack_size: Optional[str] = Field(default=None, max_length=50)
    regular_price: Optional[float] = Field(default=None, gt=0, lt=10_000_000)
    notes: Optional[str] = Field(default=None, max_length=1000)
    is_active: Optional[bool] = None

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
        return v


class OwnProductOut(BaseModel):
    id: UUID
    sku: Optional[str]
    name: str
    brand: Optional[str]
    category: str
    pack_size: Optional[str]
    pack_grams: Optional[float]
    regular_price: float
    notes: Optional[str]
    is_active: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


analyst = Depends(require_role("ANALYST"))


@router.get("/")
def compare(days: int = Query(90, ge=1, le=365), category: Optional[str] = Query(None, max_length=50),
            _: Principal = analyst, db: Session = Depends(get_db)):
    """Our shelf price per 100 g vs live competitor promotions, biggest undercuts first."""
    return build_comparison(db, days=days, category=category)


@router.get("/products", response_model=List[OwnProductOut])
def list_products(_: Principal = analyst, db: Session = Depends(get_db)):
    return db.query(OwnProduct).order_by(OwnProduct.category, OwnProduct.name).all()


@router.post("/products", response_model=OwnProductOut, status_code=201)
def create_product(body: OwnProductIn, request: Request, principal: Principal = analyst, db: Session = Depends(get_db)):
    product = OwnProduct(**body.model_dump(), pack_grams=parse_pack_grams(body.pack_size))
    db.add(product)
    auth_service.audit(db, "own_product_created", username=principal.user.username, ip=client_ip(request),
                       detail={"name": body.name})
    db.commit()
    return product


def _get(db: Session, product_id: UUID) -> OwnProduct:
    product = db.get(OwnProduct, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@router.patch("/products/{product_id}", response_model=OwnProductOut)
def update_product(product_id: UUID, body: OwnProductPatch, request: Request,
                   principal: Principal = analyst, db: Session = Depends(get_db)):
    product = _get(db, product_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(product, key, value)
    if "pack_size" in changes:
        product.pack_grams = parse_pack_grams(product.pack_size)
    auth_service.audit(db, "own_product_updated", username=principal.user.username, ip=client_ip(request),
                       detail={"id": str(product.id), "fields": sorted(changes)})
    db.commit()
    return product


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: UUID, request: Request, principal: Principal = analyst, db: Session = Depends(get_db)):
    product = _get(db, product_id)
    auth_service.audit(db, "own_product_deleted", username=principal.user.username, ip=client_ip(request),
                       detail={"name": product.name})
    db.delete(product)
    db.commit()


@router.post("/products/import")
async def import_products(request: Request, file: UploadFile = File(...),
                          principal: Principal = analyst, db: Session = Depends(get_db)):
    """CSV columns: name, regular_price (required); brand, category, pack_size, sku, notes (optional).
    All-or-nothing: if any row is invalid nothing is saved and every problem is listed."""
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 1 MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded CSV.")
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
    if not {"name", "regular_price"} <= fields:
        raise HTTPException(status_code=422, detail="CSV must have at least the columns: name, regular_price.")

    parsed, errors = [], []
    for line, row in enumerate(reader, start=2):
        if line - 1 > MAX_IMPORT_ROWS:
            raise HTTPException(status_code=422, detail=f"Too many rows (max {MAX_IMPORT_ROWS}).")
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if not any(r.values()):
            continue
        try:
            price = parse_price(r.get("regular_price"))
            item = OwnProductIn(name=r.get("name", ""), brand=r.get("brand") or None, sku=r.get("sku") or None,
                                category=r.get("category") or "BISCUIT", pack_size=r.get("pack_size") or None,
                                regular_price=price, notes=r.get("notes") or None)
            parsed.append(item)
        except Exception as exc:  # includes pydantic validation errors
            msg = str(exc).splitlines()[-1] if str(exc) else "invalid row"
            errors.append({"line": line, "error": msg[:200]})
    if errors:
        raise HTTPException(status_code=422, detail={"message": "No products were imported. Fix these rows and retry.",
                                                      "errors": errors[:50]})
    created = updated = 0
    for item in parsed:
        existing = db.query(OwnProduct).filter(OwnProduct.sku == item.sku).first() if item.sku else None
        data = item.model_dump()
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
            existing.pack_grams = parse_pack_grams(item.pack_size)
            updated += 1
        else:
            db.add(OwnProduct(**data, pack_grams=parse_pack_grams(item.pack_size)))
            created += 1
    auth_service.audit(db, "own_products_imported", username=principal.user.username, ip=client_ip(request),
                       detail={"created": created, "updated": updated})
    db.commit()
    return {"created": created, "updated": updated}
