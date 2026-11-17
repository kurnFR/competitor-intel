import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app.api.v1.endpoints.compare import OwnProductIn, OwnProductOut, OwnProductPatch
from app.db.session import SessionLocal
from app.main import app
from app.models.auth import AuditLog, User
from app.models.own_product import OwnProduct
from app.services import auth as auth_service

PASSWORD = "Correct-Horse-Battery-9"


# ---------------------------------------------------------------------------
# Unit tests for Model Validation & Pydantic Schemas
# ---------------------------------------------------------------------------

def test_own_product_model_defaults_and_attributes():
    p = OwnProduct(name="Test Biscuit", regular_price=10000.0)
    assert p.promo_type == "REGULAR"
    assert p.promo_price is None
    assert p.promo_start_date is None
    assert p.promo_end_date is None
    assert p.promo_mechanic is None
    assert p.buy_quantity is None
    assert p.free_quantity is None
    assert p.buy_x is None
    assert p.get_y is None
    assert p.has_active_promo is False


def test_own_product_model_quantity_sync():
    # buy_x / get_y -> buy_quantity / free_quantity
    p1 = OwnProduct(name="BOGO", regular_price=10000.0, buy_x=2, get_y=1)
    assert p1.buy_x == 2
    assert p1.buy_quantity == 2
    assert p1.get_y == 1
    assert p1.free_quantity == 1

    # buy_quantity / free_quantity -> buy_x / get_y
    p2 = OwnProduct(name="BOGO 2", regular_price=10000.0, buy_quantity=3, free_quantity=2)
    assert p2.buy_x == 3
    assert p2.buy_quantity == 3
    assert p2.get_y == 2
    assert p2.free_quantity == 2


def test_own_product_has_active_promo():
    now = datetime.now(timezone.utc)
    # Active promo within window
    p = OwnProduct(
        name="Active Promo",
        regular_price=10000.0,
        promo_price=8000.0,
        promo_start_date=now - timedelta(days=1),
        promo_end_date=now + timedelta(days=1),
    )
    assert p.has_active_promo is True

    # Promo not started yet
    future = OwnProduct(
        name="Future Promo",
        regular_price=10000.0,
        promo_price=8000.0,
        promo_start_date=now + timedelta(days=2),
        promo_end_date=now + timedelta(days=5),
    )
    assert future.has_active_promo is False

    # Promo expired
    expired = OwnProduct(
        name="Expired Promo",
        regular_price=10000.0,
        promo_price=8000.0,
        promo_start_date=now - timedelta(days=5),
        promo_end_date=now - timedelta(days=1),
    )
    assert expired.has_active_promo is False


def test_pydantic_own_product_in_validation():
    now = datetime.now(timezone.utc)
    item = OwnProductIn(
        name="Choco Wafer",
        category="WAFER",
        regular_price=12000.0,
        promo_price=9500.0,
        promo_type="DISCOUNT",
        promo_start_date=now,
        promo_end_date=now + timedelta(days=7),
        promo_mechanic="Direct discount",
        buy_x=2,
        get_y=1,
    )
    assert item.promo_price == 9500.0
    assert item.promo_type == "DISCOUNT"
    assert item.buy_quantity == 2
    assert item.free_quantity == 1

    # Invalid promo price (negative or 0)
    with pytest.raises(ValidationError):
        OwnProductIn(name="Bad Price", regular_price=10000.0, promo_price=-100)

    with pytest.raises(ValidationError):
        OwnProductIn(name="Zero Price", regular_price=10000.0, promo_price=0)

    # Invalid dates: end before start
    with pytest.raises(ValidationError, match="promo_end_date must be on or after promo_start_date"):
        OwnProductIn(
            name="Bad Dates",
            regular_price=10000.0,
            promo_start_date=now,
            promo_end_date=now - timedelta(days=1),
        )

    # Invalid category
    with pytest.raises(ValidationError, match="category must be one of"):
        OwnProductIn(name="Bad Category", category="DRINK", regular_price=10000.0)


def test_pydantic_own_product_patch_validation():
    now = datetime.now(timezone.utc)
    patch = OwnProductPatch(
        promo_price=7500.0,
        promo_type="BUY_X_GET_Y",
        promo_start_date=now,
        promo_end_date=now + timedelta(days=3),
        buy_quantity=1,
        free_quantity=1,
    )
    assert patch.buy_x == 1
    assert patch.get_y == 1

    with pytest.raises(ValidationError, match="promo_end_date must be on or after promo_start_date"):
        OwnProductPatch(promo_start_date=now, promo_end_date=now - timedelta(hours=1))


def test_pydantic_own_product_out_serialization():
    now = datetime.now(timezone.utc)
    product = OwnProduct(
        name="Serialization Test",
        category="BISCUIT",
        regular_price=15000.0,
        promo_price=12000.0,
        promo_type="DISCOUNT",
        promo_start_date=now,
        promo_end_date=now + timedelta(days=10),
        promo_mechanic="Promo 20%",
        buy_x=2,
        get_y=1,
    )
    out = OwnProductOut.model_validate(product)
    assert out.name == "Serialization Test"
    assert out.promo_price == 12000.0
    assert out.promo_type == "DISCOUNT"
    assert out.promo_mechanic == "Promo 20%"
    assert out.buy_x == 2
    assert out.get_y == 1
    assert out.buy_quantity == 2
    assert out.free_quantity == 1


# ---------------------------------------------------------------------------
# API CRUD & CSV Import/Export Tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_env():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    auth_service.ip_throttle.clear()
    tag = uuid.uuid4().hex[:8]
    user_name = f"opt_{tag}"
    auth_service.create_user(db, username=user_name, password=PASSWORD, role="ANALYST")
    db.commit()

    c = TestClient(app, follow_redirects=False)
    login_res = c.post("/api/v1/auth/login", json={"username": user_name, "password": PASSWORD})
    assert login_res.status_code == 200
    csrf_token = login_res.json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}

    yield type("Env", (), dict(client=c, headers=headers, db=db, tag=tag))

    db.rollback()
    db.query(OwnProduct).filter(OwnProduct.name.like(f"Opt{tag}%")).delete(synchronize_session=False)
    db.query(OwnProduct).filter(OwnProduct.sku.like(f"SKU-OPT-{tag}%")).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.username == user_name).delete(synchronize_session=False)
    db.query(User).filter(User.username == user_name).delete(synchronize_session=False)
    db.commit()
    db.close()


def test_api_crud_own_product_with_promotions(client_env):
    c = client_env.client
    hdr = client_env.headers
    tag = client_env.tag

    # 1. CREATE with active promotional pricing
    now = datetime.now(timezone.utc).replace(microsecond=0)
    end = now + timedelta(days=14)
    payload = {
        "name": f"Opt{tag} Promo Cookie",
        "brand": "BrandOpt",
        "sku": f"SKU-OPT-{tag}-1",
        "category": "COOKIE",
        "pack_size": "200g",
        "regular_price": 15000.0,
        "promo_price": 12000.0,
        "promo_type": "DISCOUNT",
        "promo_start_date": now.isoformat(),
        "promo_end_date": end.isoformat(),
        "promo_mechanic": "Hemat 3000",
        "buy_x": 1,
        "get_y": 1,
        "notes": "Created in unit test",
    }
    r = c.post("/api/v1/compare/products", json=payload, headers=hdr)
    assert r.status_code == 201, r.text
    created = r.json()
    product_id = created["id"]
    assert created["name"] == payload["name"]
    assert created["promo_price"] == 12000.0
    assert created["promo_type"] == "DISCOUNT"
    assert created["promo_mechanic"] == "Hemat 3000"
    assert created["buy_x"] == 1
    assert created["get_y"] == 1
    assert created["buy_quantity"] == 1
    assert created["free_quantity"] == 1

    # 2. FETCH products and verify promo fields
    r_list = c.get("/api/v1/compare/products", headers=hdr)
    assert r_list.status_code == 200
    products = r_list.json()
    match = next((p for p in products if p["id"] == product_id), None)
    assert match is not None
    assert match["promo_price"] == 12000.0
    assert match["promo_type"] == "DISCOUNT"

    # 3. UPDATE product promotional pricing
    new_end = end + timedelta(days=7)
    patch_payload = {
        "regular_price": 16000.0,
        "promo_price": 11000.0,
        "promo_type": "BUY_X_GET_Y",
        "promo_end_date": new_end.isoformat(),
        "buy_quantity": 2,
        "free_quantity": 1,
    }
    r_patch = c.patch(f"/api/v1/compare/products/{product_id}", json=patch_payload, headers=hdr)
    assert r_patch.status_code == 200, r_patch.text
    patched = r_patch.json()
    assert patched["regular_price"] == 16000.0
    assert patched["promo_price"] == 11000.0
    assert patched["promo_type"] == "BUY_X_GET_Y"
    assert patched["buy_x"] == 2
    assert patched["get_y"] == 1

    # 4. DELETE product
    r_del = c.delete(f"/api/v1/compare/products/{product_id}", headers=hdr)
    assert r_del.status_code == 204

    # Verify deleted
    r_del_again = c.delete(f"/api/v1/compare/products/{product_id}", headers=hdr)
    assert r_del_again.status_code == 404


def test_api_csv_export_includes_promotions(client_env):
    c = client_env.client
    hdr = client_env.headers
    tag = client_env.tag

    # Create a product with promo details
    payload = {
        "name": f"Opt{tag} Export Item",
        "category": "CRACKER",
        "regular_price": 8000.0,
        "promo_price": 6500.0,
        "promo_type": "SPECIAL",
        "promo_mechanic": "Special weekend price",
        "sku": f"SKU-OPT-{tag}-EXP",
    }
    r_create = c.post("/api/v1/compare/products", json=payload, headers=hdr)
    assert r_create.status_code == 201

    r_exp = c.get("/api/v1/compare/products/export", headers=hdr)
    assert r_exp.status_code == 200
    assert "text/csv" in r_exp.headers.get("content-type", "")

    csv_text = r_exp.text
    import csv
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames or []
    for col in ("promo_price", "promo_type", "promo_start_date", "promo_end_date", "promo_mechanic"):
        assert col in fieldnames

    rows = list(reader)
    item_row = next((r for r in rows if r.get("sku") == f"SKU-OPT-{tag}-EXP"), None)
    assert item_row is not None
    assert float(item_row["promo_price"]) == 6500.0
    assert item_row["promo_type"] == "SPECIAL"
    assert item_row["promo_mechanic"] == "Special weekend price"


def test_api_csv_import_with_promotional_columns(client_env):
    c = client_env.client
    hdr = client_env.headers
    tag = client_env.tag

    csv_data = (
        f"name,brand,category,pack_size,regular_price,sku,promo_price,promo_type,promo_start_date,promo_end_date,promo_mechanic,buy_x,get_y\n"
        f"Opt{tag} Wafer Roll,SweetCo,WAFER,100g,10000,SKU-OPT-{tag}-IMP1,8000,DISCOUNT,2026-11-01,2026-11-30,Promo November,,\n"
        f"Opt{tag} B2G1 Snack,Crunchy,SNACK,50g,5000,SKU-OPT-{tag}-IMP2,5000,BUY_X_GET_Y,2026-11-10,2026-11-20,Beli 2 Gratis 1,2,1\n"
    )
    files = {"file": ("promos.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    r_imp = c.post("/api/v1/compare/products/import", files=files, headers=hdr)
    assert r_imp.status_code == 200, r_imp.text
    assert r_imp.json() == {"created": 2, "updated": 0}

    # Verify created records in DB
    p1 = client_env.db.query(OwnProduct).filter(OwnProduct.sku == f"SKU-OPT-{tag}-IMP1").one()
    assert p1.promo_price == 8000.0
    assert p1.promo_type == "DISCOUNT"
    assert p1.promo_start_date is not None
    assert p1.promo_end_date is not None
    assert p1.promo_mechanic == "Promo November"

    p2 = client_env.db.query(OwnProduct).filter(OwnProduct.sku == f"SKU-OPT-{tag}-IMP2").one()
    assert p2.promo_type == "BUY_X_GET_Y"
    assert p2.buy_x == 2
    assert p2.get_y == 1
    assert p2.buy_quantity == 2
    assert p2.free_quantity == 1

    # Update existing record via CSV import by SKU
    csv_update = (
        f"name,regular_price,sku,promo_price,promo_type\n"
        f"Opt{tag} Wafer Roll,11000,SKU-OPT-{tag}-IMP1,7500,FLASH_SALE\n"
    )
    files_upd = {"file": ("promos_upd.csv", io.BytesIO(csv_update.encode("utf-8")), "text/csv")}
    r_upd = c.post("/api/v1/compare/products/import", files=files_upd, headers=hdr)
    assert r_upd.status_code == 200
    assert r_upd.json() == {"created": 0, "updated": 1}

    client_env.db.refresh(p1)
    assert p1.regular_price == 11000.0
    assert p1.promo_price == 7500.0
    assert p1.promo_type == "FLASH_SALE"


def test_api_csv_import_validation_failures(client_env):
    c = client_env.client
    hdr = client_env.headers
    tag = client_env.tag

    bad_csv = (
        f"name,regular_price,promo_price,promo_start_date,promo_end_date\n"
        f"Opt{tag} Bad Row 1,10000,-500,2026-11-01,2026-11-10\n"
        f"Opt{tag} Bad Row 2,10000,8000,2026-11-20,2026-11-10\n"
        f"Opt{tag} Bad Row 3,10000,8000,not-a-date,2026-11-10\n"
    )
    files = {"file": ("bad.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")}
    r = c.post("/api/v1/compare/products/import", files=files, headers=hdr)
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    lines = {e["line"] for e in errors}
    assert 2 in lines  # negative promo price
    assert 3 in lines  # end date before start date
    assert 4 in lines  # invalid date format
