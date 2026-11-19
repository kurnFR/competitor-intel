import re
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.entity import Competitor, Brand, Product, Retailer
from app.models.source import SourceRegistry
from app.models.resolution import EntityMapping
from app.models.own_product import OwnProduct
from app.services.comparison import parse_pack_grams


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def ADAPTER_FOR_DOMAIN(domain: str, source_type: str) -> str:
    """Seed sources get an explicit adapter; at runtime adapters are never guessed from the domain."""
    d = domain.lower()
    if "superindo" in d:
        return "superindo"
    if "indomaret" in d:
        return "indomaret"
    if "alfamart" in d or "alfagift" in d:
        return "alfamart"
    return "generic_catalog"


def seed_reference_data(*, demo_prices=False):
    db: Session = SessionLocal()
    try:
        print("Seeding expanded reference data into competitor_intel...")

        # 1. Competitors & Brands
        competitor_data = [
            {
                "name": "Mayora Indah",
                "parent_company": "PT Mayora Indah Tbk",
                "importance_score": 1.0,
                "brands": [
                    {"name": "Roma", "products": ["Roma Malkist Crackers", "Roma Malkist Abon", "Roma Malkist Keju Manis", "Roma Sari Gandum", "Roma Biskuit Kelapa", "Roma Marie Gold", "Roma Wafer Choco Blast", "Roma Zuperr Keju"]},
                    {"name": "Slai O'Lai", "products": ["Slai O'Lai Strawberry", "Slai O'Lai Blueberry", "Slai O'Lai Pineapple"]},
                    {"name": "Better", "products": ["Better Sandwich Biscuit"]},
                    {"name": "Coffee Joy", "products": ["Coffee Joy Biscuit"]},
                    {"name": "Superstar", "products": ["Superstar Wafer", "Superstar Snaps"]},
                    {"name": "Danisa", "products": ["Danisa Traditional Butter Cookies"]},
                    {"name": "Astor", "products": ["Astor Wafer Stick Double Cokelat", "Astor Wafer Stick Cokelat 40g", "Astor Cokelat 150g"]},
                    {"name": "Beng Beng", "products": ["Beng Beng Wafer Cokelat Original", "Beng Beng Share It", "Beng Beng Maxx"]},
                    {"name": "Malkist", "products": ["Malkist Crackers", "Malkist Cokelat", "Malkist Keju Tabur"]},
                    {"name": "Sari Gandum", "products": ["Sari Gandum Sandwich", "Sari Gandum Biskuit"]},
                    {"name": "Choki Choki", "products": ["Choki Choki Chococashew"]},
                ]
            },
            {
                "name": "OT Group",
                "parent_company": "PT Orang Tua / PT Ultra Prima Abadi",
                "importance_score": 0.95,
                "brands": [
                    {"name": "Tango", "products": ["Tango Wafer Cokelat 100g", "Tango Wafer Vanilla 100g", "Tango Wafer Keju", "Tango Wafer Sassy Strawberry", "Tango Kraffel", "Tango Walut"]},
                    {"name": "Chizmill", "products": ["Chizmill Wafer Keju"]},
                    {"name": "Fullo", "products": ["Fullo Wafer Roll Vanilla", "Fullo Blasto"]},
                    {"name": "Oops", "products": ["Oops Crackers", "Oops Fugu Fugu"]},
                    {"name": "Klop", "products": ["Klop Crackers"]},
                ]
            },
            {
                "name": "Khong Guan Group",
                "parent_company": "PT Khong Guan Biscuit Factory Indonesia",
                "importance_score": 0.95,
                "brands": [
                    {"name": "Khong Guan", "products": ["Khong Guan Red Assorted Biscuit", "Khong Guan Malkist Crackers", "Khong Guan Marie Special", "Khong Guan Super Biscuit"]},
                    {"name": "Nissin", "products": ["Nissin Wafer Chocolate", "Nissin Crispy Crackers", "Nissin Walens Choco Soes", "Nissin Biskuit Kelapa Ijo", "Nissin Lemonia"]},
                    {"name": "Monde", "products": ["Monde Butter Cookies", "Monde Serena Egg Roll", "Monde Boromon Wafer", "Monde Genji Pie"]},
                    {"name": "Serena", "products": ["Serena Togo Chocolate", "Serena Cheese Cookies", "Serena Snack"]},
                ]
            },
            {
                "name": "Mondelez Indonesia",
                "parent_company": "Mondelez International",
                "importance_score": 0.95,
                "brands": [
                    {"name": "Oreo", "products": ["Oreo Vanilla Sandwich", "Oreo Chocolate Sandwich", "Oreo Strawberry Cream", "Oreo Red Velvet", "Oreo Mini Biskuit Sandwich", "Oreo Soft Cake"]},
                    {"name": "Biskuat", "products": ["Biskuat Energi Gandum", "Biskuat Biskuit Cokelat", "Biskuat Original"]},
                    {"name": "Ritz", "products": ["Ritz Crackers Salted", "Ritz Sandwich Cheese"]},
                    {"name": "Belvita", "products": ["Belvita Breakfast Biscuit Milk & Cereal", "Belvita Madu & Cokelat"]},
                    {"name": "Cadbury", "products": ["Cadbury Dairy Milk", "Cadbury Oreo"]},
                ]
            },
            {
                "name": "Garudafood",
                "parent_company": "PT Garudafood Putra Putri Jaya Tbk",
                "importance_score": 0.90,
                "brands": [
                    {"name": "Gery", "products": ["Gery Saluut Malkist Sweet Cheese", "Gery Saluut Malkist Coconut", "Gery Saluut Wafer Roll", "Gery Biskuit dan Wafer", "Gery Pasta"]},
                    {"name": "Chocolatos", "products": ["Chocolatos Wafer Roll", "Chocolatos Wafer Cream", "Chocolatos Drink"]},
                ]
            },
            {
                "name": "Nabati Group",
                "parent_company": "PT Kaldu Sari Nabati Indonesia",
                "importance_score": 0.90,
                "brands": [
                    {"name": "Nabati", "products": ["Nabati Wafer Richeese", "Nabati Wafer Richoco", "Nabati Wafer Klapa Lava", "Nabati Wafer Pink Lava", "Nabati Gatito"]},
                    {"name": "Richeese", "products": ["Richeese Nabati Wafer Keju", "Richeese Ahh Snack Keju", "Richeese Rolls"]},
                    {"name": "Richoco", "products": ["Richoco Nabati Wafer Cokelat", "Richoco Ahh Snack Cokelat"]},
                    {"name": "Nextar", "products": ["Nextar Choco Brownies", "Nextar Strawberry", "Nextar Pineapple", "Nextar Cookies 112g"]},
                ]
            },
            {
                "name": "Arnott's Indonesia",
                "parent_company": "The Campbell Soup Company / KKR",
                "importance_score": 0.85,
                "brands": [
                    {"name": "Good Time", "products": ["Good Time Cookies Choco Dip", "Good Time Double Choc", "Good Time Rainbow", "Good Time Classic"]},
                    {"name": "Tim Tam", "products": ["Tim Tam Chocolate Biscuit", "Tim Tam Vanilla", "Tim Tam Red Velvet"]},
                    {"name": "Nyam Nyam", "products": ["Nyam Nyam Rice Crispy Bubble", "Nyam Nyam Smiley", "Nyam Nyam Fantasy Stick"]},
                ]
            },
            {
                "name": "Kalbe Farma",
                "parent_company": "PT Kalbe Farma Tbk",
                "importance_score": 0.85,
                "brands": [
                    {"name": "Fitbar", "products": ["Fitbar Chocolate 25g", "Fitbar Fruits 25g", "Fitbar Tiramisu 25g", "Fitbar Protein Bar"]},
                    {"name": "Diabetasol", "products": ["Diabetasol Wafer Chocolate 100g", "Diabetasol Nulife Wafer"]},
                ]
            },
            {
                "name": "Konimex",
                "parent_company": "PT Konimex",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Tini Wini Biti", "products": ["Tini Wini Biti Crackers Rainbow", "Tini Wini Biti Manis", "Tini Wini Biti Asin", "Tini Wini Biti Cokelat"]},
                    {"name": "Sobisco", "products": ["Sobisco Choco Pie"]},
                ]
            },
            {
                "name": "CV Jaya Abadi",
                "parent_company": "CV Jaya Abadi",
                "importance_score": 0.85,
                "brands": [
                    {"name": "Regal", "products": ["Regal Marie Biscuit Superior 120g", "Regal Marie Special 230g", "Regal Marie Duo"]},
                ]
            },
            {
                "name": "Delfi / Ceres",
                "parent_company": "Delfi Limited / PT Perusahaan Industri Ceres",
                "importance_score": 0.85,
                "brands": [
                    {"name": "Selamat", "products": ["Selamat Wafer Chocolate", "Selamat Wafer Vanilla", "Selamat Wafer Black & White"]},
                    {"name": "Twister", "products": ["Twister Wafer Roll"]},
                    {"name": "Briko", "products": ["Briko Biskuit Semua Varian", "Briko Chocolate"]},
                ]
            },
            {
                "name": "ASW Foods",
                "parent_company": "PT Asia Sakti Wahid Foods Manufacture",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Hatari", "products": ["Hatari Crackers See Hong Puff", "Hatari Biskuit Kelapa", "Hatari Malkist"]},
                ]
            },
            {
                "name": "URC Indonesia",
                "parent_company": "PT Universal Robina Corporation",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Munchy's", "products": ["Munchy's Biskuit Kraker Krim Original", "Munchy's Muzic Wafer", "Munchy's Lexus"]},
                ]
            },
            {
                "name": "Lotte Indonesia",
                "parent_company": "Lotte Corporation",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Lotte", "products": ["Lotte Choco Pie Original", "Lotte Choco Pie Strawberry", "Koala's March"]},
                ]
            },
            {
                "name": "Glico Indonesia",
                "parent_company": "Ezaki Glico Co., Ltd.",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Pocky", "products": ["Pocky Chocolate Stick", "Pocky Strawberry", "Pocky Cookies & Cream"]},
                    {"name": "Pejoy", "products": ["Pejoy Chocolate", "Pejoy Matcha"]},
                ]
            },
            {
                "name": "Meiji Food Indonesia",
                "parent_company": "Meiji Holdings Co., Ltd.",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Hello Panda", "products": ["Hello Panda Chocolate", "Hello Panda Strawberry", "Hello Panda Double Choco"]},
                    {"name": "Yan Yan", "products": ["Yan Yan Chocolate", "Yan Yan Strawberry"]},
                ]
            },
            {
                "name": "PT Fajar Mataram Sedayu",
                "parent_company": "PT Fajar Mataram Sedayu",
                "importance_score": 0.75,
                "brands": [
                    {"name": "L'Agie", "products": ["L'Agie Chocolate Alpine Full Milk", "L'Agie Wafer Roll"]},
                ]
            },
            {
                "name": "Wings Group",
                "parent_company": "PT Sayap Mas Utama",
                "importance_score": 0.80,
                "brands": [
                    {"name": "Calbee Wings", "products": ["Calbee Wings Potato Chips", "Potabee", "Krisbee"]},
                    {"name": "Olala", "products": ["Olala Jelly Wafer"]},
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
                                "COOKIE" if "cookie" in prod_name.lower() or "brownies" in prod_name.lower() or "pie" in prod_name.lower() else "BISCUIT"
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
            {"name": "Alfamidi", "channel": "MINIMARKET", "website": "https://alfamidiku.com"},
            {"name": "Indogrosir", "channel": "WHOLESALE", "website": "https://klikindogrosir.com"},
            {"name": "Superindo", "channel": "SUPERMARKET", "website": "https://www.superindo.co.id"},
            {"name": "Hypermart", "channel": "HYPERMARKET", "website": "https://shop.hypermart.co.id"},
            {"name": "Transmart", "channel": "HYPERMARKET", "website": "https://transmart.co.id"},
            {"name": "Lotte Mart", "channel": "HYPERMARKET", "website": "https://www.lottemart.co.id"},
            {"name": "Yogya Supermarket", "channel": "SUPERMARKET", "website": "https://www.toserbayogya.com"},
            {"name": "Tip Top", "channel": "SUPERMARKET", "website": "https://tiptop.co.id"},
            {"name": "Hari Hari", "channel": "SUPERMARKET", "website": "https://harihariswalayan.info"},
            {"name": "Watsons", "channel": "RETAIL", "website": "https://www.watsons.co.id"},
            {"name": "Giant", "channel": "SUPERMARKET", "website": "https://giant.co.id"},
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
            else:
                if r.channel_type in ("N/A", None, ""):
                    r.channel_type = ret["channel"]
        db.flush()

        # 3. Entity Mappings (Aliases)
        alias_retailers = [
            ("Yogya", "Yogya Supermarket"),
            ("Toserba Yogya", "Yogya Supermarket"),
            ("Hypermarket", "Hypermart"),
            ("KlikIndomaret", "Indomaret"),
            ("Klik Indomaret", "Indomaret"),
            ("Alfagift", "Alfamart"),
            ("Alfamidi Super", "Alfamidi"),
            ("Hari Hari Swalayan", "Hari Hari"),
            ("Tip Top Supermarket", "Tip Top"),
        ]
        for src_val, target_name in alias_retailers:
            target = db.query(Retailer).filter(Retailer.normalized_name == normalize(target_name)).first()
            if target:
                mapping = db.query(EntityMapping).filter(
                    EntityMapping.entity_type == "RETAILER",
                    EntityMapping.source_value == src_val
                ).first()
                if not mapping:
                    db.add(EntityMapping(
                        entity_type="RETAILER",
                        source_value=src_val,
                        normalized_source_value=normalize(src_val),
                        canonical_entity_id=target.id,
                        match_method="ALIAS",
                        confidence=1.0,
                        resolution_status="APPROVED"
                    ))

        alias_brands = [
            ("BENG BENG", "Beng Beng"),
            ("Beng-Beng", "Beng Beng"),
            ("Bengbeng", "Beng Beng"),
            ("TANGO", "Tango"),
            ("Tango Walut", "Tango"),
            ("NABATI", "Nabati"),
            ("Nabati Wafer", "Nabati"),
            ("Marie Regal", "Regal"),
            ("Serena Togo", "Serena"),
            ("Chocolatos Wafer", "Chocolatos"),
            ("Gery Saluut", "Gery"),
            ("Hatari Crackers", "Hatari"),
            ("Hello Panda", "Hello Panda"),
            ("Lagie", "L'Agie"),
            ("L'AGIE", "L'Agie"),
        ]
        for src_val, target_name in alias_brands:
            target = db.query(Brand).filter(Brand.normalized_name == normalize(target_name)).first()
            if target:
                mapping = db.query(EntityMapping).filter(
                    EntityMapping.entity_type == "BRAND",
                    EntityMapping.source_value == src_val
                ).first()
                if not mapping:
                    db.add(EntityMapping(
                        entity_type="BRAND",
                        source_value=src_val,
                        normalized_source_value=normalize(src_val),
                        canonical_entity_id=target.id,
                        match_method="ALIAS",
                        confidence=1.0,
                        resolution_status="APPROVED"
                    ))

        # 4. Company's Own Products (for Price Comparison)
        own_product_seeds = [
            {"sku": "OWN-BISK-001", "name": "Biskuit Kelapa Tradisional 300g", "brand": "Internal FMCG", "category": "BISCUIT", "pack_size": "300g", "regular_price": 11500.0},
            {"sku": "OWN-WAFR-001", "name": "Wafer Krim Cokelat 100g", "brand": "Internal FMCG", "category": "WAFER", "pack_size": "100g", "regular_price": 7500.0},
            {"sku": "OWN-WAFR-002", "name": "Wafer Krim Keju 100g", "brand": "Internal FMCG", "category": "WAFER", "pack_size": "100g", "regular_price": 7500.0},
            {"sku": "OWN-CRCK-001", "name": "Malkist Crackers Manis 120g", "brand": "Internal FMCG", "category": "CRACKER", "pack_size": "120g", "regular_price": 8200.0},
            {"sku": "OWN-COOK-001", "name": "Sandwich Cookies Vanilla 133g", "brand": "Internal FMCG", "category": "COOKIE", "pack_size": "133g", "regular_price": 9500.0},
            {"sku": "OWN-CRCK-002", "name": "Crispy Crackers Gurih 110g", "brand": "Internal FMCG", "category": "CRACKER", "pack_size": "110g", "regular_price": 7000.0},
            {"sku": "OWN-COOK-002", "name": "Brownies Soft Cookies 112g", "brand": "Internal FMCG", "category": "COOKIE", "pack_size": "112g", "regular_price": 8500.0},
            {"sku": "OWN-WAFR-003", "name": "Wafer Roll Stick Chocolate 100g", "brand": "Internal FMCG", "category": "WAFER", "pack_size": "100g", "regular_price": 9000.0},
        ]
        for p_data in (own_product_seeds if demo_prices else []):
            existing = db.query(OwnProduct).filter(OwnProduct.sku == p_data["sku"]).first()
            if not existing:
                db.add(OwnProduct(
                    sku=p_data["sku"],
                    name=p_data["name"],
                    brand=p_data["brand"],
                    category=p_data["category"],
                    pack_size=p_data["pack_size"],
                    pack_grams=parse_pack_grams(p_data["pack_size"]),
                    regular_price=p_data["regular_price"],
                    is_active=True
                ))

        db.commit()
        print("✅ Seeding completed successfully!")
        
        # Summary counts
        print(f"Competitors: {db.query(Competitor).count()}")
        print(f"Brands: {db.query(Brand).count()}")
        print(f"Products: {db.query(Product).count()}")
        print(f"Retailers: {db.query(Retailer).count()}")
        print(f"Entity Mappings: {db.query(EntityMapping).count()}")
        print(f"Own Products: {db.query(OwnProduct).count()}")
        print(f"Source Registries: {db.query(SourceRegistry).count()}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-prices", action="store_true", help="Populate sample own prices for demos")
    seed_reference_data(demo_prices=parser.parse_args().demo_prices)
