import re
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.entity import Competitor, Brand, Product, Retailer
from app.models.resolution import EntityMapping


def normalize_str(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


class EntityResolver:
    def __init__(self, db: Session):
        self.db = db

    def resolve_retailer(self, retailer_name: Optional[str]) -> Optional[Retailer]:
        if not retailer_name:
            return None
        norm = normalize_str(retailer_name)
        
        # 1. Exact or normalized lookup
        retailer = self.db.query(Retailer).filter(
            (Retailer.normalized_name == norm) | (Retailer.name.ilike(f"%{retailer_name}%"))
        ).first()

        if retailer:
            return retailer

        # 2. Fuzzy match via pg_trgm
        query = text("""
            SELECT id, name, similarity(normalized_name, :norm) as sim
            FROM competitor_intel.retailers
            WHERE similarity(normalized_name, :norm) > 0.3
            ORDER BY sim DESC LIMIT 1
        """)
        row = self.db.execute(query, {"norm": norm}).fetchone()
        if row:
            return self.db.query(Retailer).filter(Retailer.id == row[0]).first()

        # 3. Create new Retailer if not found
        new_ret = Retailer(
            name=retailer_name,
            normalized_name=norm,
            channel_type="SUPERMARKET",
            country="ID"
        )
        self.db.add(new_ret)
        self.db.flush()
        return new_ret

    def resolve_brand_and_competitor(self, brand_name: Optional[str], product_name: str) -> Tuple[Optional[Brand], Optional[Competitor]]:
        query_text = brand_name or product_name
        norm = normalize_str(query_text)

        # Look up by brand normalized name
        brand = self.db.query(Brand).filter(
            (Brand.normalized_name == norm) | (Brand.name.ilike(f"%{brand_name}%" if brand_name else "%"))
        ).first()

        if not brand:
            # Check if any known brand name is a substring of product_name
            p_norm = normalize_str(product_name)
            for b in self.db.query(Brand).all():
                if b.normalized_name in p_norm or b.name.lower() in product_name.lower():
                    brand = b
                    break

        if brand:
            competitor = self.db.query(Competitor).filter(Competitor.id == brand.competitor_id).first()
            return brand, competitor

        return None, None
