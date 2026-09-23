from typing import Optional, List
from pydantic import BaseModel, Field


class ExtractedPromotionItem(BaseModel):
    product_name: str = Field(description="Normalized product name, e.g. Nissin Wafer Cokelat 110g")
    brand: Optional[str] = Field(default=None, description="Brand name")
    competitor: Optional[str] = Field(default=None, description="Manufacturer / competitor")
    category: str = Field(default="BISCUIT", description="BISCUIT, CRACKER, COOKIE, WAFER, or SNACK")
    variant: Optional[str] = Field(default=None, description="Flavor or variant")
    pack_size: Optional[str] = Field(default=None, description="Pack size")
    regular_price: Optional[float] = Field(default=None, description="Normal price in IDR")
    promo_price: Optional[float] = Field(default=None, description="Promotional price in IDR")
    discount_percentage: Optional[float] = Field(default=None, description="Stated or calculated discount percent")
    promotion_type: str = Field(default="DISCOUNT", description="DISCOUNT, BUY_X_GET_Y, MULTIBUY, CASHBACK, VOUCHER, MEMBER_PRICE, BUNDLE, or OTHER")
    buy_quantity: Optional[int] = None
    free_quantity: Optional[int] = None
    start_date: Optional[str] = Field(default=None, description="Promotion start date in YYYY-MM-DD or null")
    end_date: Optional[str] = Field(default=None, description="Promotion end date in YYYY-MM-DD or null")
    retailer: Optional[str] = None
    channel: Optional[str] = Field(default=None, description="Retail, Modern Trade, General Trade, E-commerce, Wholesale, Distributor, Foodservice, or N/A")
    geography: Optional[str] = Field(default=None, description="Exact geography wording from source; never infer a geography that is not stated")
    evidence_quote: str = Field(description="Exact snippet from source text supporting this promotion")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class ExtractedPromotionBatch(BaseModel):
    promotions: List[ExtractedPromotionItem] = Field(default_factory=list)
