from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session, contains_eager
from sqlalchemy import and_, func, or_, select
from uuid import UUID
from app.db.session import get_db
from app.models.promotion import Promotion, PromotionEvidence
from app.models.promotion_change import PromotionChangeEvent
from app.models.entity import Competitor, Brand, Retailer
from app.schemas.promotion import (
    PromotionChangeEventOut,
    PromotionDetailOut,
    PromotionLookupItem,
    PromotionLookupResponse,
    SourceCoverageItem,
    Top10PromotionItem,
    Top10Response,
)
from fastapi.responses import Response
from app.core.deps import Principal, require_role
from app.services.digest import build_digest
from app.services.ranking.rescore import explain_scores
from app.services.regional import build_regional_prices
from app.services.exporting import build_export
from app.services.geography import REGION_LABELS, UNKNOWN
from app.services.channels import display_channel, normalize_channel, retailer_types_for
from app.services.promotions.visibility import live_promotion_filter
from app.services.source_health import compute_health
from app.services.crawler.manager import ADAPTERS
from app.models.source import CrawlDocument, SourceRegistry

router = APIRouter()


def _like(value: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _ilike(column, value: str):
    return column.ilike(_like(value), escape="\\")


def _channel_condition(channel: str):
    normalized = normalize_channel(channel)
    if normalized is None:
        # Unknown channel names can only match promotions with no known channel.
        return and_(Promotion.channel.is_(None), Retailer.channel_type.is_(None))
    types = retailer_types_for(normalized)
    return or_(
        Promotion.channel == normalized,
        and_(Promotion.channel.is_(None), func.upper(Retailer.channel_type).in_(types)),
    )


def _filtered_query(db: Session, now: datetime, *, days: int, q=None, category=None, outlet=None, channel=None,
                    brand=None, competitor=None, region=None):
    query = (
        db.query(Promotion)
        .outerjoin(Competitor, Promotion.competitor_id == Competitor.id)
        .outerjoin(Brand, Promotion.brand_id == Brand.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .options(contains_eager(Promotion.competitor), contains_eager(Promotion.brand), contains_eager(Promotion.retailer))
        .filter(live_promotion_filter(now, recency_days=days))
    )
    if category:
        query = query.filter(_ilike(Promotion.category, category))
    if outlet:
        query = query.filter(_ilike(Retailer.name, outlet))
    if channel:
        query = query.filter(_channel_condition(channel))
    if q:
        query = query.filter(or_(
            _ilike(Promotion.product_name, q), _ilike(Promotion.promotion_type, q), _ilike(Promotion.category, q),
            _ilike(Promotion.channel, q), _ilike(Promotion.geography, q), _ilike(Retailer.name, q),
            _ilike(Competitor.name, q), _ilike(Brand.name, q),
        ))
    if brand:
        query = query.filter(_ilike(Brand.name, brand))
    if competitor:
        query = query.filter(_ilike(Competitor.name, competitor))
    if region:
        query = query.filter(Promotion.geography_region == region.strip().upper())
    return query


def _latest_evidence(db: Session, promotions) -> dict:
    """Latest evidence per promotion in a single query."""
    if not promotions:
        return {}
    rows = (
        db.query(PromotionEvidence)
        .filter(PromotionEvidence.promotion_id.in_([p.id for p in promotions]))
        .order_by(PromotionEvidence.captured_at.desc())
        .all()
    )
    out = {}
    for e in rows:  # newest first
        out.setdefault(e.promotion_id, e)
    return out


@router.get("/top10", response_model=Top10Response)
def get_top10_promotions(
    industry: str = Query("FMCG", min_length=1, description="Required industry selector; FMCG is the default"),
    q: Optional[str] = Query(None, max_length=100, description="Free-text search across competitor, product, outlet, mechanic, and geography"),
    category: Optional[str] = Query(None, max_length=50, description="Filter by category (e.g. BISCUIT, CRACKER, WAFER)"),
    outlet: Optional[str] = Query(None, max_length=100, description="Filter by outlet name"),
    retailer: Optional[str] = Query(None, max_length=100, description="Backward-compatible outlet filter"),
    channel: Optional[str] = Query(None, max_length=50, description="Filter by channel, e.g. Modern Trade or E-commerce"),
    region: Optional[str] = Query(None, max_length=30, description="Filter by stated region, e.g. JAWA, SUMATERA, ONLINE, NATIONAL, UNKNOWN"),
    brand: Optional[str] = Query(None, max_length=100, description="Filter by brand name"),
    competitor: Optional[str] = Query(None, max_length=100, description="Filter by competitor name"),
    days: int = Query(90, ge=1, le=365, description="Recency window in days (default 90 for 3-month rule)"),
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    query = _filtered_query(db, now, days=days, q=q, category=category, outlet=outlet or retailer,
                            channel=channel, brand=brand, competitor=competitor, region=region)
    results = query.order_by(Promotion.rank_score.desc(), Promotion.last_verified_at.desc()).limit(10).all()

    evidence_by_promo = _latest_evidence(db, results)
    breakdowns = explain_scores(db, results, now=now)

    items = []
    for idx, p in enumerate(results, start=1):
        latest_evidence = evidence_by_promo.get(p.id)
        dates_stated = p.start_date is not None or p.end_date is not None
        if p.end_date:
            valid_until = p.end_date.strftime("%Y-%m-%d")
        else:
            valid_until = "No end date stated" if dates_stated else "Dates not stated"
        items.append(Top10PromotionItem(
            id=p.id, rank=idx, product_name=p.product_name, brand=p.brand.name if p.brand else None,
            competitor=p.competitor.name if p.competitor else None, category=p.category, pack_size=p.pack_size,
            retailer=p.retailer.name if p.retailer else None, outlet=p.retailer.name if p.retailer else None,
            channel=display_channel(p.channel, p.retailer.channel_type if p.retailer else None),
            geography=p.geography or REGION_LABELS[UNKNOWN], geography_region=p.geography_region,
            promotion_type=p.promotion_type,
            buy_quantity=p.buy_quantity, free_quantity=p.free_quantity, regular_price=p.regular_price,
            promo_price=p.promo_price, discount_percentage=p.discount_percentage, effective_discount=p.discount_percentage,
            valid_until=valid_until, score_breakdown=breakdowns.get(p.id),
            valid_from=p.start_date.strftime("%Y-%m-%d") if p.start_date else None,
            dates_stated=dates_stated, rank_score=p.rank_score,
            ai_confidence=p.ai_confidence, source_reliability=p.source_reliability,
            evidence_quote=latest_evidence.evidence_text if latest_evidence else None,
            source_url=latest_evidence.source_url if latest_evidence else None,
            source_status=("Verified source" if latest_evidence and latest_evidence.source_url and latest_evidence.evidence_text else "Unverified source"),
            last_verified=p.last_verified_at,
        ))
    return Top10Response(generated_at=now.isoformat(), count=len(items), promotions=items)

@router.get("/search", response_model=PromotionLookupResponse)
def search_promotions(
    q: str = Query(..., min_length=2, max_length=100, description="Product, brand, or competitor search; every term must match"),
    category: Optional[str] = Query(None, max_length=50),
    outlet: Optional[str] = Query(None, max_length=100),
    source_id: Optional[UUID] = Query(None, description="Restrict results to one configured source"),
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    principal: Principal = Depends(require_role("VIEWER")),
    db: Session = Depends(get_db),
):
    """Search eligible promotions already collected from approved sources; this does not crawl the web."""
    terms = [term for term in q.strip().split() if term]
    if not terms:
        raise HTTPException(status_code=422, detail="Enter a product, brand, or competitor name.")
    if len(terms) > 8:
        raise HTTPException(status_code=422, detail="Search with eight terms or fewer.")

    now = datetime.now(timezone.utc)
    query = _filtered_query(db, now, days=days)
    for term in terms:
        query = query.filter(or_(
            _ilike(Promotion.product_name, term),
            _ilike(Promotion.promotion_title, term),
            _ilike(Promotion.promotion_description, term),
            _ilike(Promotion.promotion_type, term),
            _ilike(Promotion.category, term),
            _ilike(Brand.name, term),
            _ilike(Competitor.name, term),
            _ilike(Retailer.name, term),
        ))
    if category:
        query = query.filter(_ilike(Promotion.category, category))
    if outlet:
        query = query.filter(_ilike(Retailer.name, outlet))
    if source_id:
        evidence_source_id = (
            select(CrawlDocument.source_id)
            .select_from(PromotionEvidence)
            .outerjoin(CrawlDocument, CrawlDocument.id == PromotionEvidence.document_id)
            .where(PromotionEvidence.promotion_id == Promotion.id)
            .order_by(
                PromotionEvidence.captured_at.desc(),
                PromotionEvidence.created_at.desc(),
                PromotionEvidence.id.desc(),
            )
            .limit(1)
            .correlate(Promotion)
            .scalar_subquery()
        )
        query = query.filter(func.coalesce(evidence_source_id, Promotion.source_id) == source_id)

    total = query.order_by(None).count()
    results = query.order_by(Promotion.last_verified_at.desc(), Promotion.rank_score.desc()).offset(offset).limit(limit).all()
    evidence_by_promo = _latest_evidence(db, results)

    document_ids = {e.document_id for e in evidence_by_promo.values() if e.document_id is not None}
    source_id_by_document = {}
    if document_ids:
        source_id_by_document = dict(
            db.query(CrawlDocument.id, CrawlDocument.source_id)
            .filter(CrawlDocument.id.in_(document_ids))
            .all()
        )
    result_source_ids = {
        source_id_by_document.get(evidence_by_promo[p.id].document_id) or p.source_id
        for p in results
        if p.id in evidence_by_promo
    }
    result_source_ids.update(p.source_id for p in results if p.source_id is not None)
    source_names = {
        source.id: source.name
        for source in db.query(SourceRegistry).filter(SourceRegistry.id.in_(result_source_ids)).all()
    } if result_source_ids else {}

    items = []
    for p in results:
        evidence = evidence_by_promo.get(p.id)
        evidence_source_id = source_id_by_document.get(evidence.document_id) if evidence and evidence.document_id else None
        resolved_source_id = evidence_source_id or p.source_id
        dates_stated = p.start_date is not None or p.end_date is not None
        valid_until = p.end_date.strftime("%Y-%m-%d") if p.end_date else (
            "No end date stated" if dates_stated else "Dates not stated"
        )
        items.append(PromotionLookupItem(
            id=p.id,
            product_name=p.product_name,
            brand=p.brand.name if p.brand else None,
            competitor=p.competitor.name if p.competitor else None,
            category=p.category,
            pack_size=p.pack_size,
            outlet=p.retailer.name if p.retailer else None,
            channel=display_channel(p.channel, p.retailer.channel_type if p.retailer else None),
            geography=p.geography or REGION_LABELS[UNKNOWN],
            promotion_type=p.promotion_type,
            regular_price=p.regular_price,
            promo_price=p.promo_price,
            discount_percentage=p.discount_percentage,
            valid_from=p.start_date.strftime("%Y-%m-%d") if p.start_date else None,
            valid_until=valid_until,
            dates_stated=dates_stated,
            last_verified=p.last_verified_at,
            source_id=resolved_source_id,
            source_name=source_names.get(resolved_source_id),
            source_url=evidence.source_url if evidence else None,
            evidence_quote=evidence.evidence_text if evidence else None,
            source_reliability=p.source_reliability,
            ai_confidence=p.ai_confidence,
            rank_score=p.rank_score,
        ))

    source_coverage = None
    if principal.user.role in {"ANALYST", "ADMIN"}:
        active_sources = (
            db.query(SourceRegistry)
            .filter(SourceRegistry.is_active.is_(True), SourceRegistry.approval_status == "APPROVED",
                    SourceRegistry.adapter_key.in_(ADAPTERS.keys()))
            .order_by(SourceRegistry.name)
            .limit(50)
            .all()
        )
        source_coverage = [
            SourceCoverageItem(
                id=source.id,
                name=source.name,
                health=compute_health(source, now),
                last_processed_at=source.last_processed_at,
            )
            for source in active_sources
        ]
    return PromotionLookupResponse(
        query=q,
        generated_at=now.isoformat(),
        count=len(items),
        total=total,
        limit=limit,
        offset=offset,
        source_coverage=source_coverage,
        promotions=items,
    )



def _export_rows(db: Session, promotions) -> list:
    evidence = _latest_evidence(db, promotions)
    rows = []
    for idx, p in enumerate(promotions, start=1):
        ev = evidence.get(p.id)
        dates_stated = p.start_date is not None or p.end_date is not None
        rows.append({
            "rank": idx, "product": p.product_name, "brand": p.brand.name if p.brand else None,
            "competitor": p.competitor.name if p.competitor else None, "category": p.category, "pack_size": p.pack_size,
            "outlet": p.retailer.name if p.retailer else None,
            "channel": display_channel(p.channel, p.retailer.channel_type if p.retailer else None),
            "promotion_type": p.promotion_type, "regular_price": p.regular_price, "promo_price": p.promo_price,
            "discount": p.discount_percentage,
            "valid_from": p.start_date.strftime("%Y-%m-%d") if p.start_date else None,
            "valid_until": p.end_date.strftime("%Y-%m-%d") if p.end_date else None,
            "dates_stated": "Yes" if dates_stated else "No", "score": p.rank_score, "confidence": p.ai_confidence,
            "source_url": ev.source_url if ev else None, "evidence": ev.evidence_text if ev else None,
            "last_verified": p.last_verified_at.strftime("%Y-%m-%d %H:%M") if p.last_verified_at else None,
        })
    return rows


@router.get("/export", dependencies=[Depends(require_role("ANALYST"))])
def export_promotions(
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    q: Optional[str] = Query(None, max_length=100),
    category: Optional[str] = Query(None, max_length=50),
    outlet: Optional[str] = Query(None, max_length=100),
    channel: Optional[str] = Query(None, max_length=50),
    region: Optional[str] = Query(None, max_length=30),
    brand: Optional[str] = Query(None, max_length=100),
    competitor: Optional[str] = Query(None, max_length=100),
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """Download current promotions (same filters as the dashboard) for spreadsheets."""
    now = datetime.now(timezone.utc)
    promotions = (
        _filtered_query(db, now, days=days, q=q, category=category, outlet=outlet, channel=channel,
                        brand=brand, competitor=competitor, region=region)
        .order_by(Promotion.rank_score.desc(), Promotion.last_verified_at.desc()).limit(limit).all()
    )
    content, media_type, ext = build_export(_export_rows(db, promotions), format)
    filename = f"competitor-promotions-{now.strftime('%Y%m%d')}.{ext}"
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/digest")
def promotion_digest(days: int = Query(7, ge=1, le=60), db: Session = Depends(get_db)):
    """What is new, what changed and what ends soon."""
    return build_digest(db, days=days)


@router.get("/regional-prices")
def regional_prices(
    category: Optional[str] = Query(None, max_length=50),
    competitor: Optional[str] = Query(None, max_length=100),
    q: Optional[str] = Query(None, max_length=100),
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Price of each eligible product per stated region. Unstated regions stay separate, never 'nationwide'."""
    now = datetime.now(timezone.utc)
    promotions = _filtered_query(db, now, days=days, q=q, category=category, competitor=competitor).limit(5000).all()
    return build_regional_prices(promotions)


@router.get("/{promotion_id}/changes", response_model=List[PromotionChangeEventOut])
def get_promotion_changes(
    promotion_id: str,
    event_type: Optional[str] = Query(None, description="Filter event type, e.g. PRICE_OR_VALUE_CHANGED"),
    days: int = Query(90, ge=1, le=3650, description="History window in days"),
    limit: int = Query(100, ge=1, le=500, description="Maximum events to return"),
    db: Session = Depends(get_db),
):
    if not db.query(Promotion).filter(Promotion.id == promotion_id).first():
        raise HTTPException(status_code=404, detail="Promotion not found")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(PromotionChangeEvent).filter(
        PromotionChangeEvent.promotion_id == promotion_id,
        PromotionChangeEvent.observed_at >= cutoff,
    )
    if event_type:
        query = query.filter(PromotionChangeEvent.event_type == event_type)
    return query.order_by(PromotionChangeEvent.observed_at.desc()).limit(limit).all()


@router.get("/{promotion_id}", response_model=PromotionDetailOut)
def get_promotion_detail(promotion_id: str, db: Session = Depends(get_db)):
    p = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Promotion not found")
    evidence = db.query(PromotionEvidence).filter(PromotionEvidence.promotion_id == p.id).all()
    changes = db.query(PromotionChangeEvent).filter(PromotionChangeEvent.promotion_id == p.id).order_by(PromotionChangeEvent.observed_at.desc()).limit(50).all()
    return PromotionDetailOut(
        id=p.id, product_name=p.product_name, brand=p.brand.name if p.brand else None,
        competitor=p.competitor.name if p.competitor else None, category=p.category, pack_size=p.pack_size,
        retailer=p.retailer.name if p.retailer else None,
        channel=display_channel(p.channel, p.retailer.channel_type if p.retailer else None), promotion_type=p.promotion_type,
        buy_quantity=p.buy_quantity, free_quantity=p.free_quantity, regular_price=p.regular_price,
        promo_price=p.promo_price, discount_percentage=p.discount_percentage, start_date=p.start_date,
        end_date=p.end_date, status=p.status, supersedes_promotion_id=p.supersedes_promotion_id,
        source_reliability=p.source_reliability, ai_confidence=p.ai_confidence, rank_score=p.rank_score,
        first_seen_at=p.first_seen_at, last_seen_at=p.last_seen_at, evidence_items=evidence, change_events=changes,
    )
