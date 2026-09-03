import uuid
import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.entity import Competitor, Brand, Product, Retailer
from app.models.source import SourceRegistry


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def seed_reference_data():
    db: Session = SessionLocal()
    try:
        print("Seeding reference data into competitor_intel...")

        # 1. Competitors & Brands
        competitor_data = [
            {
                "name": "Mayora Indah",
                "parent_company": "PT Mayora Indah Tbk",
                "importance_score": 1.0,
                "brands": [
                    {"name": "Roma", "products": ["Roma Malkist Crackers", "Roma Malkist Abon", "Roma Malkist Keju Manis", "Roma Sari Gandum", "Roma Biskuit Kelapa", "Roma Marie Gold"]},
                    {"name": "Slai O'Lai", "products": ["Slai O'Lai Strawberry", "Slai O'Lai Blueberry", "Slai O'Lai Pineapple"]},
                    {"name": "Better", "products": ["Better Sandwich Biscuit"]},
                    {"name": "Coffee Joy", "products": ["Coffee Joy Biscuit"]},
                    {"name": "Superstar", "products": ["Superstar Wafer"]},
                    {"name": "Danisa", "products": ["Danisa Traditional Butter Cookies"]},
                ]
            },
            {
                "name": "Khong Guan Group",
                "parent_company": "PT Khong Guan Biscuit Factory Indonesia",
                "importance_score": 0.95,
                "brands": [
                    {"name": "Khong Guan", "products": ["Khong Guan Red Assorted Biscuit", "Khong Guan Malkist Crackers", "Khong Guan Marie Special"]},
                    {"name": "Nissin", "products": ["Nissin Wafer Chocolate", "Nissin Crispy Crackers", "Nissin Walens Choco Soes"]},
                    {"name": "Monde", "products": ["Monde Butter Cookies", "Monde Serena Egg Roll", "Monde Borobudur"]},
                ]
            },
            {
                "name": "Mondelez Indonesia",
                "parent_company": "Mondelez International",
                "importance_score": 0.95,
                "brands": [
                    {"name": "Oreo", "products": ["Oreo Vanilla Sandwich", "Oreo Chocolate Sandwich", "Oreo Strawberry Cream", "Oreo Red Velvet"]},
                    {"name": "Biskuat", "products": ["Biskuat Energi Gandum", "Biskuat Biskuit Cokelat"]},
                    {"name": "Ritz", "products": ["Ritz Crackers Salted", "Ritz Sandwich Cheese"]},
                    {"name": "Belvita", "products": ["Belvita Breakfast Biscuit Milk & Cereal"]},
                ]
            },
            {
                "name": "Garudafood",
                "parent_company": "PT Garudafood Putra Putri Jaya Tbk",
                "importance_score": 0.90,
                "brands": [
                    {"name": "Gery", "products": ["Gery Saluut Malkist Sweet Cheese", "Gery Saluut Malkist Coconut", "Gery Saluut Wafer Roll"]},
                    {"name": "Chocolatos", "products": ["Chocolatos Wafer Roll", "Chocolatos Wafer Cream"]},
                ]
            },
            {
                "name": "Nabati Group",
                "parent_company": "PT Kaldu Sari Nabati Indonesia",
                "importance_score": 0.90,
                "brands": [
                    {"name": "Richeese", "products": ["Richeese Nabati Wafer Keju", "Richeese Ahh Snack Keju"]},
                    {"name": "Richoco", "products": ["Richoco Nabati Wafer Cokelat"]},
                    {"name": "Nextar", "products": ["Nextar Choco Brownies", "Nextar Strawberry", "Nextar Pineapple"]},
                ]
            },
            {
                "name": "Arnott's Indonesia",
                "parent_company": "The Campbell Soup Company / KKR",
                "importance_score": 0.85,
                "brands": [
                    {"name": "Good Time", "products": ["Good Time Cookies Choco Dip", "Good Time Double Choc", "Good Time Rainbow"]},
                    {"name": "Tim Tam", "products": ["Tim Tam Chocolate Biscuit", "Tim Tam Vanilla"]},
                    {"name": "Nyam Nyam", "products": ["Nyam Nyam Rice Crispy Bubble", "Nyam Nyam Smiley"]},
                ]
            },
            {
                "name": "Wings Group",
                "parent_company": "PT Sayap Mas Utama",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Glico Wings / Olala", "products": ["Olala Jelly Wafer"]},
                    {"name": "Floridina / Wings Food Snack", "products": ["Calbee Wings Potato Chips"]},
                ]
            }
        ]

        for comp_info in competitor_data:
            comp = db.query(Competitor).filter(Competitor.normalized_name == normalize(comp_info["name"])).first()
            if not comp:
                comp = Competitor(
                    name=comp_info["name"],
                    normalized_name=normalize(comp_info["name"]),
                    parent_company=comp_info["parent_company"],
                    importance_score=comp_info["importance_score"],
                    is_active=True
                )
                db.add(comp)
                db.flush()

            for brand_info in comp_info["brands"]:
                brand = db.query(Brand).filter(Brand.normalized_name == normalize(brand_info["name"])).first()
                if not brand:
                    brand = Brand(
                        competitor_id=comp.id,
                        name=brand_info["name"],
                        normalized_name=normalize(brand_info["name"]),
                        manufacturer=comp_info["name"]
                    )
                    db.add(brand)
                    db.flush()

                for prod_name in brand_info["products"]:
                    prod = db.query(Product).filter(Product.normalized_name == normalize(prod_name)).first()
                    if not prod:
                        category = "CRACKER" if "malkist" in prod_name.lower() or "cracker" in prod_name.lower() else (
                            "WAFER" if "wafer" in prod_name.lower() else (
                                "COOKIE" if "cookie" in prod_name.lower() or "brownies" in prod_name.lower() else "BISCUIT"
                            )
                        )
                        prod = Product(
                            brand_id=brand.id,
                            name=prod_name,
                            normalized_name=normalize(prod_name),
                            category=category,
                            pack_size_value=120.0,
                            pack_size_unit="g"
                        )
                        db.add(prod)

        # 2. Retailers
        retailers = [
            {"name": "Indomaret", "channel": "MINIMARKET", "website": "https://www.klikindomaret.com"},
            {"name": "Alfamart", "channel": "MINIMARKET", "website": "https://alfagift.id"},
            {"name": "Superindo", "channel": "SUPERMARKET", "website": "https://www.superindo.co.id"},
            {"name": "Hypermart", "channel": "HYPERMARKET", "website": "https://shop.hypermart.co.id"},
            {"name": "Transmart", "channel": "HYPERMARKET", "website": "https://transmart.co.id"},
            {"name": "Lotte Mart", "channel": "SUPERMARKET", "website": "https://www.lottemart.co.id"},
            {"name": "Yogya Supermarket", "channel": "SUPERMARKET", "website": "https://www.toserbayogya.com"},
            {"name": "Tip Top", "channel": "SUPERMARKET", "website": "https://tiptop.co.id"},
        ]

        for ret in retailers:
            r = db.query(Retailer).filter(Retailer.normalized_name == normalize(ret["name"])).first()
            if not r:
                r = Retailer(
                    name=ret["name"],
                    normalized_name=normalize(ret["name"]),
                    channel_type=ret["channel"],
                    website=ret["website"],
                    country="ID"
                )
                db.add(r)

        # 3. Source Registry
        sources = [
            {
                "name": "Superindo Promo Koran & Mingguan",
                "domain": "superindo.co.id",
                "base_url": "https://www.superindo.co.id/promosi/katalog-super-hemat",
                "source_type": "RETAILER",
                "tier": "TIER_1",
                "reliability_score": 1.0,
                "category": "SUPERMARKET_CATALOG",
                "crawl_frequency_minutes": 60
            },
            {
                "name": "KlikIndomaret Promosi Snack & Biskuit",
                "domain": "klikindomaret.com",
                "base_url": "https://www.klikindomaret.com/page/promosi-mingguan",
                "source_type": "RETAILER",
                "tier": "TIER_1",
                "reliability_score": 1.0,
                "category": "MINIMARKET_ECOMMERCE",
                "crawl_frequency_minutes": 60
            },
            {
                "name": "Alfagift Promo Super Hemat",
                "domain": "alfagift.id",
                "base_url": "https://alfagift.id/c/biskuit-kue",
                "source_type": "RETAILER",
                "tier": "TIER_1",
                "reliability_score": 1.0,
                "category": "MINIMARKET_ECOMMERCE",
                "crawl_frequency_minutes": 60
            },
            {
                "name": "Hemat.id FMCG Biskuit & Wafer",
                "domain": "hemat.id",
                "base_url": "https://www.hemat.id/katalog/biskuit-kraker-wafer/",
                "source_type": "PROMOTION_AGGREGATOR",
                "tier": "TIER_3",
                "reliability_score": 0.85,
                "category": "PROMOTION_AGGREGATOR",
                "crawl_frequency_minutes": 120
            },
            {
                "name": "Katalogpromosi Diskon Biskuit",
                "domain": "katalogpromosi.com",
                "base_url": "https://katalogpromosi.com/tag/promo-biskuit/",
                "source_type": "PROMOTION_AGGREGATOR",
                "tier": "TIER_3",
                "reliability_score": 0.80,
                "category": "PROMOTION_AGGREGATOR",
                "crawl_frequency_minutes": 180
            },
        ]

        for s_data in sources:
            src = db.query(SourceRegistry).filter(SourceRegistry.domain == s_data["domain"]).first()
            if not src:
                src = SourceRegistry(
                    name=s_data["name"],
                    domain=s_data["domain"],
                    base_url=s_data["base_url"],
                    source_type=s_data["source_type"],
                    tier=s_data["tier"],
                    reliability_score=s_data["reliability_score"],
                    category=s_data["category"],
                    crawl_frequency_minutes=s_data["crawl_frequency_minutes"],
                    country="ID",
                    language="id",
                    is_active=True
                )
                db.add(src)

        db.commit()
        print("✅ Seeding completed successfully!")
        
        # Summary counts
        print(f"Competitors: {db.query(Competitor).count()}")
        print(f"Brands: {db.query(Brand).count()}")
        print(f"Products: {db.query(Product).count()}")
        print(f"Retailers: {db.query(Retailer).count()}")
        print(f"Source Registries: {db.query(SourceRegistry).count()}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_reference_data()
