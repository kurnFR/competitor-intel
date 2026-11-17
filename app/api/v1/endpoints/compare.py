"""Own-product price list and comparison against competitor promotions."""
import csv
import io
from datetime import date, datetime, time, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.deps import Principal, client_ip, require_role
from app.db.session import get_db
from app.models.own_product import OwnProduct
from app.services import auth as auth_service
from app.services.comparison import build_comparison, build_comparison_export, parse_pack_grams, parse_price, simulate_price

router = APIRouter()
CATEGORIES = ("BISCUIT", "CRACKER", "COOKIE", "WAFER", "SNACK")
MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 1000


def _parse_csv_datetime(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    val = val.strip()
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    try:
        d = date.fromisoformat(val)
        return datetime.combine(d, time.min, tzinfo=timezone.utc)
    except ValueError:
        pass
    raise ValueError(f"Invalid date format: {val}")


class OwnProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    brand: Optional[str] = Field(default=None, max_length=120)
    sku: Optional[str] = Field(default=None, max_length=64)
    category: str = "BISCUIT"
    pack_size: Optional[str] = Field(default=None, max_length=50)
    regular_price: float = Field(gt=0, lt=10_000_000)
    notes: Optional[str] = Field(default=None, max_length=1000)

    # Promotional pricing & mechanics
    promo_price: Optional[float] = Field(default=None, gt=0, lt=10_000_000)
    promo_type: str = Field(default="REGULAR", max_length=50)
    promo_start_date: Optional[datetime] = None
    promo_end_date: Optional[datetime] = None
    promo_mechanic: Optional[str] = Field(default=None, max_length=100)
    buy_quantity: Optional[int] = Field(default=None, ge=1)
    free_quantity: Optional[int] = Field(default=None, ge=1)
    buy_x: Optional[int] = Field(default=None, ge=1)
    get_y: Optional[int] = Field(default=None, ge=1)

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
        return v

    @model_validator(mode="after")
    def _validate_promotions(self):
        if self.promo_start_date and self.promo_end_date and self.promo_end_date < self.promo_start_date:
            raise ValueError("promo_end_date must be on or after promo_start_date")
        if self.buy_x is not None and self.buy_quantity is None:
            self.buy_quantity = self.buy_x
        elif self.buy_quantity is not None and self.buy_x is None:
            self.buy_x = self.buy_quantity
        if self.get_y is not None and self.free_quantity is None:
            self.free_quantity = self.get_y
        elif self.free_quantity is not None and self.get_y is None:
            self.get_y = self.free_quantity
        return self


class OwnProductPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    brand: Optional[str] = Field(default=None, max_length=120)
    sku: Optional[str] = Field(default=None, max_length=64)
    category: Optional[str] = None
    pack_size: Optional[str] = Field(default=None, max_length=50)
    regular_price: Optional[float] = Field(default=None, gt=0, lt=10_000_000)
    notes: Optional[str] = Field(default=None, max_length=1000)
    is_active: Optional[bool] = None

    # Promotional pricing & mechanics
    promo_price: Optional[float] = Field(default=None, gt=0, lt=10_000_000)
    promo_type: Optional[str] = Field(default=None, max_length=50)
    promo_start_date: Optional[datetime] = None
    promo_end_date: Optional[datetime] = None
    promo_mechanic: Optional[str] = Field(default=None, max_length=100)
    buy_quantity: Optional[int] = Field(default=None, ge=1)
    free_quantity: Optional[int] = Field(default=None, ge=1)
    buy_x: Optional[int] = Field(default=None, ge=1)
    get_y: Optional[int] = Field(default=None, ge=1)

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
        return v

    @model_validator(mode="after")
    def _validate_promotions(self):
        if self.promo_start_date and self.promo_end_date and self.promo_end_date < self.promo_start_date:
            raise ValueError("promo_end_date must be on or after promo_start_date")
        if self.buy_x is not None and self.buy_quantity is None:
            self.buy_quantity = self.buy_x
        elif self.buy_quantity is not None and self.buy_x is None:
            self.buy_x = self.buy_quantity
        if self.get_y is not None and self.free_quantity is None:
            self.free_quantity = self.get_y
        elif self.free_quantity is not None and self.get_y is None:
            self.get_y = self.free_quantity
        return self


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
    promo_price: Optional[float] = None
    promo_type: str = "REGULAR"
    promo_start_date: Optional[datetime] = None
    promo_end_date: Optional[datetime] = None
    promo_mechanic: Optional[str] = None
    buy_quantity: Optional[int] = None
    free_quantity: Optional[int] = None
    buy_x: Optional[int] = None
    get_y: Optional[int] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SimulationIn(BaseModel):
    product_id: Optional[UUID] = None
    sku: Optional[str] = None
    name: Optional[str] = "Simulated Product"
    category: str = "BISCUIT"
    pack_size: Optional[str] = None
    pack_grams: Optional[float] = None
    regular_price: Optional[float] = None
    candidate_price: Optional[float] = Field(default=None, gt=0, lt=10_000_000)
    candidate_promo_price: Optional[float] = Field(default=None, gt=0, lt=10_000_000)
    candidate_regular_price: Optional[float] = Field(default=None, gt=0, lt=10_000_000)
    candidate_promo_type: str = Field(default="DISCOUNT", max_length=50)
    candidate_discount_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    buy_quantity: Optional[int] = Field(default=None, ge=1)
    free_quantity: Optional[int] = Field(default=None, ge=1)
    buy_x: Optional[int] = Field(default=None, ge=1)
    get_y: Optional[int] = Field(default=None, ge=1)
    min_pack_ratio: float = Field(default=0.5, ge=0.1, le=10.0)
    max_pack_ratio: float = Field(default=2.0, ge=0.1, le=10.0)
    days: int = Field(default=90, ge=1, le=365)
    unstated_recency_days: int = Field(default=14, ge=1, le=90)

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
        return v


analyst = Depends(require_role("ANALYST"))


@router.get("/")
def compare(
    days: int = Query(90, ge=1, le=365),
    unstated_recency_days: int = Query(14, ge=1, le=90),
    category: Optional[str] = Query(None, max_length=50),
    brand: Optional[str] = Query(None, max_length=120),
    competitor: Optional[str] = Query(None, max_length=120),
    retailer: Optional[str] = Query(None, max_length=120),
    channel: Optional[str] = Query(None, max_length=50),
    _: Principal = analyst,
    db: Session = Depends(get_db),
):
    """Our shelf price per 100 g vs live competitor promotions, biggest undercuts first."""
    return build_comparison(
        db,
        days=days,
        unstated_recency_days=unstated_recency_days,
        category=category,
        brand=brand,
        competitor=competitor,
        retailer=retailer,
        channel=channel,
    )


@router.get("/export")
def export_comparison(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    days: int = Query(90, ge=1, le=365),
    unstated_recency_days: int = Query(14, ge=1, le=90),
    category: Optional[str] = Query(None, max_length=50),
    brand: Optional[str] = Query(None, max_length=120),
    competitor: Optional[str] = Query(None, max_length=120),
    retailer: Optional[str] = Query(None, max_length=120),
    channel: Optional[str] = Query(None, max_length=50),
    _: Principal = analyst,
    db: Session = Depends(get_db),
):
    """One-click executive export of the price comparison matrix as formatted CSV or Excel."""
    comp = build_comparison(
        db,
        days=days,
        unstated_recency_days=unstated_recency_days,
        category=category,
        brand=brand,
        competitor=competitor,
        retailer=retailer,
        channel=channel,
    )
    content, media_type, ext = build_comparison_export(comp, format)
    filename = f"executive_price_comparison_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/simulate")
def simulate_promotion(
    body: SimulationIn,
    request: Request,
    principal: Principal = analyst,
    db: Session = Depends(get_db),
):
    """Simulate a candidate promotional price and see projected market position and undercut changes in real-time."""
    try:
        return simulate_price(
            db,
            product_id=body.product_id,
            sku=body.sku,
            name=body.name,
            category=body.category,
            pack_size=body.pack_size,
            pack_grams=body.pack_grams,
            regular_price=body.regular_price,
            candidate_price=body.candidate_price,
            candidate_promo_price=body.candidate_promo_price,
            candidate_regular_price=body.candidate_regular_price,
            candidate_promo_type=body.candidate_promo_type,
            candidate_discount_percentage=body.candidate_discount_percentage,
            buy_quantity=body.buy_quantity,
            free_quantity=body.free_quantity,
            buy_x=body.buy_x,
            get_y=body.get_y,
            min_pack_ratio=body.min_pack_ratio,
            max_pack_ratio=body.max_pack_ratio,
            days=body.days,
            unstated_recency_days=body.unstated_recency_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/aggregations")
def get_aggregations(
    days: int = Query(90, ge=1, le=365),
    unstated_recency_days: int = Query(14, ge=1, le=90),
    category: Optional[str] = Query(None, max_length=50),
    brand: Optional[str] = Query(None, max_length=120),
    competitor: Optional[str] = Query(None, max_length=120),
    retailer: Optional[str] = Query(None, max_length=120),
    channel: Optional[str] = Query(None, max_length=50),
    _: Principal = analyst,
    db: Session = Depends(get_db),
):
    """Breakdown of competitor promo activities by brand, category, retailer/channel, and promotional mechanic."""
    res = build_comparison(
        db,
        days=days,
        unstated_recency_days=unstated_recency_days,
        category=category,
        brand=brand,
        competitor=competitor,
        retailer=retailer,
        channel=channel,
    )
    return res.get("aggregations", {})


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
    if "buy_x" in changes and "buy_quantity" not in changes:
        changes["buy_quantity"] = changes["buy_x"]
    elif "buy_quantity" in changes and "buy_x" not in changes:
        changes["buy_x"] = changes["buy_quantity"]
    if "get_y" in changes and "free_quantity" not in changes:
        changes["free_quantity"] = changes["get_y"]
    elif "free_quantity" in changes and "get_y" not in changes:
        changes["get_y"] = changes["free_quantity"]
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


@router.get("/products/export")
def export_products(format: str = Query("csv"), _: Principal = analyst, db: Session = Depends(get_db)):
    """Export own products as CSV including regular and promotional pricing."""
    products = db.query(OwnProduct).order_by(OwnProduct.category, OwnProduct.name).all()
    output = io.StringIO()
    fieldnames = [
        "name", "brand", "sku", "category", "pack_size", "regular_price",
        "promo_price", "promo_type", "promo_start_date", "promo_end_date",
        "promo_mechanic", "buy_quantity", "free_quantity", "buy_x", "get_y",
        "is_active", "notes"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for p in products:
        writer.writerow({
            "name": p.name,
            "brand": p.brand or "",
            "sku": p.sku or "",
            "category": p.category,
            "pack_size": p.pack_size or "",
            "regular_price": p.regular_price,
            "promo_price": p.promo_price if p.promo_price is not None else "",
            "promo_type": p.promo_type or "REGULAR",
            "promo_start_date": p.promo_start_date.isoformat() if p.promo_start_date else "",
            "promo_end_date": p.promo_end_date.isoformat() if p.promo_end_date else "",
            "promo_mechanic": p.promo_mechanic or "",
            "buy_quantity": p.buy_quantity if p.buy_quantity is not None else "",
            "free_quantity": p.free_quantity if p.free_quantity is not None else "",
            "buy_x": p.buy_x if p.buy_x is not None else "",
            "get_y": p.get_y if p.get_y is not None else "",
            "is_active": p.is_active,
            "notes": p.notes or "",
        })
    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="own_products.csv"'}
    )


@router.post("/products/import")
async def import_products(request: Request, file: UploadFile = File(...),
                          principal: Principal = analyst, db: Session = Depends(get_db)):
    """CSV columns: name, regular_price (required);
    brand, category, pack_size, sku, notes, promo_price, promo_type, promo_start_date, promo_end_date,
    promo_mechanic, buy_quantity, free_quantity, buy_x, get_y (optional).
    All-or-nothing: if any row is invalid nothing is saved and every problem is listed."""
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="File is too large (max 1 MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded CSV.") from None
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
            promo_raw = r.get("promo_price")
            promo_price = parse_price(promo_raw) if promo_raw else None
            promo_start = _parse_csv_datetime(r.get("promo_start_date"))
            promo_end = _parse_csv_datetime(r.get("promo_end_date"))

            buy_q_raw = r.get("buy_quantity") or r.get("buy_x")
            buy_q = int(buy_q_raw) if buy_q_raw else None
            free_q_raw = r.get("free_quantity") or r.get("get_y")
            free_q = int(free_q_raw) if free_q_raw else None

            item = OwnProductIn(
                name=r.get("name", ""),
                brand=r.get("brand") or None,
                sku=r.get("sku") or None,
                category=r.get("category") or "BISCUIT",
                pack_size=r.get("pack_size") or None,
                regular_price=price,
                notes=r.get("notes") or None,
                promo_price=promo_price,
                promo_type=r.get("promo_type") or "REGULAR",
                promo_start_date=promo_start,
                promo_end_date=promo_end,
                promo_mechanic=r.get("promo_mechanic") or None,
                buy_quantity=buy_q,
                free_quantity=free_q,
                buy_x=buy_q,
                get_y=free_q,
            )
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
