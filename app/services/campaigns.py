"""FMCG Campaign and Seasonal Promotion Tagging Engine.

Identifies Indonesian retail promotional themes and commercial mechanics:
- Ramadhan & Lebaran Festive (biscuits, tins, hampers, berkah)
- JSM Weekend Promos (Jumat-Sabtu-Minggu retailer specials)
- Payday / Gajian Specials (end-of-month and first-week paycheck campaigns)
- Back to School / Bekal Anak
- Buy-X-Get-Y / BOGO mechanics
- Cashback & E-Wallet incentives (Gopay, ShopeePay, OVO, Dana)
- Bundle & Multi-pack offers (twin pack, paket hemat, 2 lebih hemat)
- Member Exclusives (Indomaret Poinku, Alfagift, Club)
- Flash / Clearance Sales
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class CampaignDefinition:
    code: str
    label: str
    color: str  # Tailwind color badge key: emerald, indigo, amber, rose, sky, purple, orange, etc.
    description: str
    keywords_regex: Optional[re.Pattern] = None


CAMPAIGNS: Dict[str, CampaignDefinition] = {
    "RAMADHAN_LEBARAN": CampaignDefinition(
        code="RAMADHAN_LEBARAN",
        label="Ramadhan & Lebaran",
        color="emerald",
        description="Seasonal Ramadhan and Idul Fitri festive packs, biscuit tins, and hampers.",
        keywords_regex=re.compile(
            r"\b(ramadhan|ramadan|lebaran|idul\s*fitri|kurma|berkah|festive|biskuit\s*kaleng|kaleng|hampers|parcel|parsel)\b",
            re.IGNORECASE,
        ),
    ),
    "JSM_WEEKEND": CampaignDefinition(
        code="JSM_WEEKEND",
        label="JSM Weekend",
        color="indigo",
        description="Indonesian Modern Trade weekend promo (Jumat, Sabtu, Minggu).",
        keywords_regex=re.compile(
            r"\b(jsm|jumat\s*sabtu\s*minggu|promo\s*weekend|akhir\s*pekan|weekend\s*promo)\b",
            re.IGNORECASE,
        ),
    ),
    "GAJIAN_PAYDAY": CampaignDefinition(
        code="GAJIAN_PAYDAY",
        label="Payday / Gajian",
        color="purple",
        description="End-of-month or beginning-of-month salary payday specials.",
        keywords_regex=re.compile(
            r"\b(gajian|payday|promo\s*gajian|super\s*hemat\s*gajian|awal\s*bulan|akhir\s*bulan)\b",
            re.IGNORECASE,
        ),
    ),
    "BACK_TO_SCHOOL": CampaignDefinition(
        code="BACK_TO_SCHOOL",
        label="Back to School",
        color="sky",
        description="School season snacks and lunchbox promotions.",
        keywords_regex=re.compile(
            r"\b(back\s*to\s*school|kembali\s*ke\s*sekolah|bekal\s*sekolah|bekal\s*anak|tahun\s*ajaran\s*baru)\b",
            re.IGNORECASE,
        ),
    ),
    "BOGO": CampaignDefinition(
        code="BOGO",
        label="Buy 1 Get 1 / BOGO",
        color="rose",
        description="Buy-X-Get-Y free promotions (e.g. Beli 1 Gratis 1, Beli 2 Gratis 1).",
        keywords_regex=re.compile(
            r"\b(b1g1|b2g1|beli\s*\d+\s*gratis\s*\d+|buy\s*\d+\s*get\s*\d+|gratis\s*1)\b",
            re.IGNORECASE,
        ),
    ),
    "CASHBACK_EWALLET": CampaignDefinition(
        code="CASHBACK_EWALLET",
        label="Cashback & E-Wallet",
        color="amber",
        description="Digital payment or wallet discounts (Gopay, ShopeePay, OVO, AstraPay, QRIS).",
        keywords_regex=re.compile(
            r"\b(cashback|gopay|shopeepay|shopee\s*pay|ovo|dana|astrapay|astra\s*pay|linkaja|qris|e-wallet|ewallet)\b",
            re.IGNORECASE,
        ),
    ),
    "BUNDLE_TWIN": CampaignDefinition(
        code="BUNDLE_TWIN",
        label="Bundle & Multi-pack",
        color="teal",
        description="Bundled products, twin packs, or 2-lebih-hemat volume mechanics.",
        keywords_regex=re.compile(
            r"\b(bundle|bundling|paket\s*hemat|twin\s*pack|multi\s*pack|2\s*lebih\s*hemat|beli\s*2\s*lebih\s*hemat)\b",
            re.IGNORECASE,
        ),
    ),
    "MEMBER_SPECIAL": CampaignDefinition(
        code="MEMBER_SPECIAL",
        label="Member Exclusive",
        color="blue",
        description="Loyalty member pricing or bonus loyalty points.",
        keywords_regex=re.compile(
            r"\b(member|khusus\s*member|poinku|indomaret\s*poinku|alfagift|myalfamart|point|loyalty)\b",
            re.IGNORECASE,
        ),
    ),
    "FLASH_SALE": CampaignDefinition(
        code="FLASH_SALE",
        label="Flash / Clearance",
        color="orange",
        description="Time-limited flash deals, clearance, or super hot prices.",
        keywords_regex=re.compile(
            r"\b(flash\s*sale|promo\s*kilat|cuci\s*gudang|clearance|diskon\s*kilat|harga\s*spesial)\b",
            re.IGNORECASE,
        ),
    ),
}


def _extract_text_corpus(obj: Any) -> str:
    """Consolidate text fields from an ORM Promotion, dictionary, or raw string."""
    if isinstance(obj, str):
        return obj

    parts: List[str] = []
    if isinstance(obj, dict):
        for key in (
            "product_name",
            "promotion_title",
            "promotion_description",
            "evidence_quote",
            "evidence",
            "evidence_text",
            "verbatim_quote",
            "gift_description",
            "category",
            "brand",
            "competitor",
        ):
            val = obj.get(key)
            if val and isinstance(val, str):
                parts.append(val)
        if "evidence_items" in obj and isinstance(obj["evidence_items"], list):
            for ev in obj["evidence_items"]:
                if isinstance(ev, dict):
                    q = (
                        ev.get("evidence_text")
                        or ev.get("verbatim_quote")
                        or ev.get("evidence_quote")
                    )
                    if q and isinstance(q, str):
                        parts.append(q)
                elif hasattr(ev, "evidence_text") or hasattr(ev, "verbatim_quote") or hasattr(ev, "evidence_quote"):
                    q = (
                        getattr(ev, "evidence_text", None)
                        or getattr(ev, "verbatim_quote", None)
                        or getattr(ev, "evidence_quote", None)
                    )
                    if q and isinstance(q, str):
                        parts.append(q)
        return " ".join(parts)

    # Object / ORM model
    for attr in (
        "product_name",
        "promotion_title",
        "promotion_description",
        "gift_description",
        "category",
    ):
        val = getattr(obj, attr, None)
        if val and isinstance(val, str):
            parts.append(val)

    # Relations or nested
    if hasattr(obj, "evidence_items") and obj.evidence_items:
        for ev in obj.evidence_items:
            if isinstance(ev, dict):
                q = (
                    ev.get("evidence_text")
                    or ev.get("verbatim_quote")
                    or ev.get("evidence_quote")
                )
            else:
                q = (
                    getattr(ev, "evidence_text", None)
                    or getattr(ev, "verbatim_quote", None)
                    or getattr(ev, "evidence_quote", None)
                )
            if q and isinstance(q, str):
                parts.append(q)

    return " ".join(parts)


def detect_campaign_tags(promo: Any) -> List[Dict[str, str]]:
    """Return a list of matched campaign tags for a given promotion."""
    corpus = _extract_text_corpus(promo)
    matched_codes: Set[str] = set()

    # Mechanic-driven detection
    promo_type = ""
    cashback = 0.0
    buy_qty = 0
    bundle_qty = 0

    if isinstance(promo, dict):
        promo_type = (promo.get("promotion_type") or "").upper()
        cashback = float(promo.get("cashback_amount") or 0.0)
        buy_qty = int(promo.get("buy_quantity") or 0)
        bundle_qty = int(promo.get("bundle_quantity") or 0)
    else:
        promo_type = (getattr(promo, "promotion_type", "") or "").upper()
        cashback = float(getattr(promo, "cashback_amount", 0.0) or 0.0)
        buy_qty = int(getattr(promo, "buy_quantity", 0) or 0)
        bundle_qty = int(getattr(promo, "bundle_quantity", 0) or 0)

    if promo_type == "BUY_X_GET_Y" or buy_qty > 0:
        matched_codes.add("BOGO")

    if promo_type == "CASHBACK" or cashback > 0:
        matched_codes.add("CASHBACK_EWALLET")

    if promo_type in ("BUNDLE", "MULTIBUY") or bundle_qty > 1:
        matched_codes.add("BUNDLE_TWIN")

    if promo_type == "MEMBER_PRICE":
        matched_codes.add("MEMBER_SPECIAL")

    # Keyword regex matching
    if corpus:
        for code, defn in CAMPAIGNS.items():
            if defn.keywords_regex and defn.keywords_regex.search(corpus):
                matched_codes.add(code)

    # Maintain consistent presentation order based on CAMPAIGNS ordering
    tags = []
    for code, defn in CAMPAIGNS.items():
        if code in matched_codes:
            tags.append({
                "code": defn.code,
                "label": defn.label,
                "color": defn.color,
                "description": defn.description,
            })
    return tags


def get_campaign_tag_codes(promo: Any) -> List[str]:
    """Helper to get only the string codes of matched campaigns."""
    return [t["code"] for t in detect_campaign_tags(promo)]


def get_available_campaigns() -> List[Dict[str, str]]:
    """Return all defined campaigns in the system."""
    return [
        {
            "code": d.code,
            "label": d.label,
            "color": d.color,
            "description": d.description,
        }
        for d in CAMPAIGNS.values()
    ]
