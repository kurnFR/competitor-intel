from typing import Optional, List
from pydantic import BaseModel, Field


class ExtractedPromotionItem(BaseModel):
    product_name: str = Field(description="Normalized product name, e.g. Nissin Wafer Cokelat 110g")
    brand: Optional[str] = Field(default=None, description="Brand name, e.g. Nissin, Roma, Oreo, Beng Beng")
    competitor: Optional[str] = Field(default=None, description="Manufacturer / Competitor, e.g. Mayora, Khong Guan, Mondelez")
    category: str = Field(default="BISCUIT", description="Category: BISCUIT, CRACKER, COOKIE, WAFER, or SNACK")
    variant: Optional[str] = Field(default=None, description="Flavor or variant, e.g. Cokelat, Keju, Strawberry")
    pack_size: Optional[str] = Field(default=None, description="Pack size, e.g. 110 gr, 200g")
    regular_price: Optional[float] = Field(default=None, description="Normal regular price in IDR without symbols")
    promo_price: Optional[float] = Field(default=None, description="Discounted promotional price in IDR")
    discount_percentage: Optional[float] = Field(default=None, description="Stated or calculated discount percent")
    promotion_type: str = Field(default="DISCOUNT", description="DISCOUNT, BUY_X_GET_Y, MULTIBUY, CASHBACK, VOUCHER, MEMBER_PRICE, BUNDLE, or OTHER")
    buy_quantity: Optional[int] = Field(default=None, description="For B1G1 / B2G1: number of items to buy")
    free_quantity: Optional[int] = Field(default=None, description="For B1G1 / B2G1: number of free items")
    start_date: Optional[str] = Field(default=None, description="Promotion start date in YYYY-MM-DD or null")
    end_date: Optional[str] = Field(default=None, description="Promotion valid until date in YYYY-MM-DD or null")
    retailer: Optional[str] = Field(default=None, description="Retailer name: Indomaret, Alfamart, Superindo, Hypermart, etc.")
    evidence_quote: str = Field(description="Exact snippet from source text supporting this promotion")
    confidence: float = Field(default=0.9, description="Confidence score from 0.0 to 1.0")


class ExtractedPromotionBatch(BaseModel):
    promotions: List[ExtractedPromotionItem] = Field(default_factory=list)
