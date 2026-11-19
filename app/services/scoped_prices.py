from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from app.models.own_product import OwnProduct


def scoped_catalog(db, catalog, retailer: str | None, region: str | None, now: datetime):
    if not retailer or not region:
        return catalog
    rows = db.execute(
        text("""SELECT DISTINCT ON (s.product_id) s.*
                  FROM competitor_intel.scoped_prices s JOIN competitor_intel.retailers r ON r.id=s.retailer_id
                  WHERE lower(r.name)=lower(:retailer) AND s.region=:region AND :day BETWEEN s.starts AND s.ends
                  ORDER BY s.product_id,s.recorded_at DESC,s.id"""),
        {"retailer": retailer, "region": region.upper(), "day": now.astimezone(ZoneInfo("Asia/Jakarta")).date()},
    ).mappings()
    prices = {r["product_id"]: r for r in rows}
    result = []
    for product in catalog:
        price = prices.get(product.id)
        if price is None:
            result.append(product)
            continue
        values = {key: getattr(product, key) for key in ("id", "name", "brand", "sku", "category", "pack_size", "pack_grams")}
        result.append(
            OwnProduct(
                **values,
                regular_price=float(price["regular_price"]),
                promo_price=float(price["promo_price"]) if price["promo_price"] else None,
                promo_type="DISCOUNT" if price["promo_price"] else "REGULAR",
            )
        )
    return result
