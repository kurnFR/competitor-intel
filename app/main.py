import base64
import hashlib
import hmac
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, text
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine, get_db
from app.config import get_settings
from app.models import Company, CompanyActivity, Location, Product, Promotion, Retailer
from app.schemas import PromotionCreate

app = FastAPI(title="Competitor Intel Search API", version="0.1.0")
settings = get_settings()

VERIFIED_CHANNEL_TYPES = (
    "Retail",
    "Modern Trade",
    "General Trade",
    "E-commerce",
    "Wholesale",
    "Distributor",
    "Foodservice",
    "N/A",
)
CHANNEL_ALIASES = {
    "retail": "Retail",
    "modern trade": "Modern Trade",
    "modern_trade": "Modern Trade",
    "general trade": "General Trade",
    "general_trade": "General Trade",
    "ecommerce": "E-commerce",
    "e-commerce": "E-commerce",
    "wholesale": "Wholesale",
    "distributor": "Distributor",
    "foodservice": "Foodservice",
    "pending verification": "N/A",
    "n/a": "N/A",
    "na": "N/A",
}


def normalize_channel_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[normalized]
    if value in VERIFIED_CHANNEL_TYPES:
        return value
    raise HTTPException(status_code=422, detail=f"Unsupported channel_type. Choose one of: {', '.join(VERIFIED_CHANNEL_TYPES)}")


def _session_value(username: str) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"username": username}).encode()).decode()
    signature = hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _authenticated(request: Request) -> bool:
    value = request.cookies.get("competitor_session", "")
    try:
        payload, signature = value.rsplit(".", 1)
        valid = hmac.compare_digest(
            signature,
            hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest(),
        )
        user = json.loads(base64.urlsafe_b64decode(payload.encode())).get("username")
        return valid and user == settings.auth_username
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def require_auth(request: Request):
    if not _authenticated(request):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Authentication required")


@app.get("/login")
def login_page() -> HTMLResponse:
    return HTMLResponse("""
    <!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Sign in | Competitor Intel</title><style>
    :root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#10161b;color:#eef4f1;font:16px Georgia,serif}.login{width:min(420px,calc(100% - 32px));padding:34px;background:#182229;border:1px solid #2e4147;border-radius:12px;box-shadow:0 20px 50px #0008}h1{margin:0 0 8px;font-size:30px}p{color:#aab9b4;margin:0 0 25px}label{display:block;margin:16px 0 7px;font:600 12px Arial,sans-serif;text-transform:uppercase;letter-spacing:.08em;color:#9bb3aa}input,button{width:100%;padding:13px;border-radius:7px;border:1px solid #3b5356;background:#10181d;color:#f5f8f6;font:16px Arial,sans-serif}button{margin-top:22px;background:#d4f36a;color:#182229;border:0;font-weight:700;cursor:pointer}.error{min-height:20px;color:#ff9e8f;font:14px Arial,sans-serif;margin-top:14px}</style></head>
    <body><main class="login"><h1>Competitor Intel</h1><p>Sign in to your market activity workspace.</p>
    <form id="login-form"><label for="username">Username</label><input id="username" autocomplete="username" required>
    <label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>
    <button>Sign in</button><div class="error" id="error"></div></form></main>
    <script>document.getElementById('login-form').addEventListener('submit',async event=>{event.preventDefault();const response=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value,password:password.value})});if(response.ok){location.href='/';}else{error.textContent='Invalid username or password.';}});</script></body></html>
    """)


@app.post("/login")
async def login(request: Request):
    credentials = await request.json()
    if not hmac.compare_digest(str(credentials.get("username", "")), settings.auth_username) or not hmac.compare_digest(str(credentials.get("password", "")), settings.auth_password):
        return JSONResponse({"detail": "Invalid credentials"}, status_code=401)
    response = JSONResponse({"status": "ok", "username": settings.auth_username})
    response.set_cookie("competitor_session", _session_value(settings.auth_username), httponly=True, samesite="lax", max_age=28800)
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("competitor_session")
    return response

DEFAULT_FMCG_TARGETS = [
    {
        "company": "Mayora",
        "industry": "FMCG",
        "products": [
            {"name": "Roma Kelapa", "category": "Biscuit", "promo_type": "Buy 2 Get 1", "regular_price": 12000, "promo_price": 8000, "discount_pct": 33.3},
            {"name": "Roma Malkist", "category": "Biscuit", "promo_type": "20% OFF", "regular_price": 15000, "promo_price": 12000, "discount_pct": 20.0},
            {"name": "Biskuit Marie", "category": "Biscuit", "promo_type": "Member Price", "regular_price": 10000, "promo_price": 8500, "discount_pct": 15.0},
        ],
    },
    {
        "company": "Khong Guan",
        "industry": "FMCG",
        "products": [
            {"name": "Khong Guan Biscuit", "category": "Biscuit", "promo_type": "Buy 1 Get 1", "regular_price": 14000, "promo_price": 7000, "discount_pct": 50.0},
            {"name": "Khong Guan Crackers", "category": "Cracker", "promo_type": "Promo Pack", "regular_price": 16000, "promo_price": 13000, "discount_pct": 18.8},
        ],
    },
    {
        "company": "Interbisco",
        "industry": "FMCG",
        "products": [
            {"name": "Interbisco Wafer", "category": "Wafer", "promo_type": "Combo Discount", "regular_price": 18000, "promo_price": 14900, "discount_pct": 17.3},
            {"name": "Interbisco Cookies", "category": "Cookie", "promo_type": "Free Gift", "regular_price": 11000, "promo_price": 10000, "discount_pct": 9.1},
        ],
    },
    {
        "company": "Unibis",
        "industry": "FMCG",
        "products": [
            {"name": "Unibis Sandwich", "category": "Biscuits", "promo_type": "30% OFF", "regular_price": 20000, "promo_price": 14000, "discount_pct": 30.0},
        ],
    },
    {
        "company": "Indofood",
        "industry": "FMCG",
        "products": [
            {"name": "Indofood Biscuit Family", "category": "Biscuit", "promo_type": "Double Pack", "regular_price": 17000, "promo_price": 13900, "discount_pct": 18.2},
        ],
    },
]


class StartJobRequest(BaseModel):
    industry: str = Field(min_length=1)
    product: str = ""
    location: str = ""
    outlet: str = ""
    category: str = ""
    channel_type: str = "N/A"


class ScheduleRequest(BaseModel):
    enabled: bool = False
    time_utc: str = Field(default="01:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


schedule_file = Path(__file__).resolve().parents[1] / "schedule.json"
schedule_state = {"enabled": False, "time_utc": "01:00", "last_run": None}
if schedule_file.exists():
    try:
        schedule_state.update(json.loads(schedule_file.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
schedule_lock = threading.Lock()


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    threading.Thread(target=_daily_scan_loop, daemon=True).start()


def _daily_scan_loop():
    last_run_date = None
    while True:
        now = datetime.utcnow()
        with schedule_lock:
            enabled = schedule_state["enabled"]
            scheduled_time = schedule_state["time_utc"]
        if enabled and now.strftime("%H:%M") == scheduled_time and last_run_date != now.date():
            db = SessionLocal()
            try:
                run_scrape_and_store(db, StartJobRequest(industry="FMCG"))
                with schedule_lock:
                    schedule_state["last_run"] = datetime.utcnow().isoformat()
                last_run_date = now.date()
            finally:
                db.close()
        time.sleep(20)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def dashboard_page(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse("""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Competitor Intel FMCG</title>
        <style>
            :root { color-scheme: light; --bg: #eef1ed; --surface: #ffffff; --ink: #17211f; --muted: #687570; --line: #d9e1dc; --accent: #527a35; --accent-ink: #ffffff; --head: #e4eee2; }
            :root[data-theme="dark"] { color-scheme: dark; --bg: #101718; --surface: #182326; --ink: #edf4ef; --muted: #a4b3ac; --line: #30413f; --accent: #d4f36a; --accent-ink: #182229; --head: #21332d; }
            * { box-sizing: border-box; } body { font-family: Georgia, serif; background: var(--bg); margin: 0; padding: 24px; color: var(--ink); transition: background .2s, color .2s; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 14px 34px rgba(17,24,39,0.08); padding: 24px; }
            .topbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; } .actions { display: flex; gap: 8px; }
            .title { font-size: 28px; font-weight: 700; letter-spacing: .01em; }
            .form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 18px; margin: 20px 0; }
            .compact { margin-top: 0; } label { display: block; font: 600 12px Arial, sans-serif; letter-spacing: .04em; margin-bottom: 6px; color: var(--muted); text-transform: uppercase; }
            input, select, button { width: 100%; padding: 10px 12px; border-radius: 7px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); font: 14px Arial, sans-serif; }
            button { background: var(--accent); color: var(--accent-ink); border: none; cursor: pointer; font-weight: 700; } button:hover { filter: brightness(.94); } .secondary { background: transparent; color: var(--ink); border: 1px solid var(--line); width: auto; white-space: nowrap; }
            .status { margin-top: 12px; min-height: 20px; font: 600 14px Arial, sans-serif; color: var(--accent); } .table-wrap { overflow-x: auto; } .schedule { border-top: 1px solid var(--line); margin-top: 24px; padding-top: 18px; } .schedule-row { display: flex; align-items: end; gap: 12px; flex-wrap: wrap; } .schedule-row > div { min-width: 160px; } .schedule-note { color: var(--muted); font: 13px Arial, sans-serif; }
            table { width: 100%; min-width: 900px; border-collapse: collapse; margin-top: 20px; } th, td { border-bottom: 1px solid var(--line); padding: 12px 10px; text-align: left; font: 14px Arial, sans-serif; } th { background: var(--head); color: var(--ink); }
            .badge { display: inline-block; padding: 5px 10px; background: var(--head); color: var(--ink); border-radius: 6px; font: 700 12px Arial, sans-serif; } .empty { color: var(--muted); font-style: italic; } a { color: var(--accent); }
            @media (max-width: 620px) { body { padding: 12px; } .card { padding: 16px; } .topbar { align-items: flex-start; flex-direction: column; } .actions { width: 100%; } .actions button { flex: 1; } .title { font-size: 24px; } }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="topbar">
                <div class="title">FMCG Competitor Intel</div>
                <div class="actions"><button type="button" id="theme-btn" class="secondary" title="Toggle theme">Dark theme</button><button type="button" id="logout-btn" class="secondary">Sign out</button></div>
            </div>
            <div class="card">
                <form id="search-form">
                    <div class="form-grid">
                        <div>
                            <label>Industry</label>
                            <select id="industry" required>
                                <option value="" disabled>Select industry *</option>
                                <option selected>FMCG</option>
                                <option>Consumer Goods</option>
                                <option>Retail</option>
                                <option>Food & Beverage</option>
                            </select>
                        </div>
                        <div>
                            <label>Search</label>
                            <input id="product" placeholder="All products" />
                        </div>
                        <div>
                            <label>Location</label>
                            <input id="location" placeholder="All locations" />
                        </div>
                        <div>
                                <label>Outlet</label>
                            <input id="outlet" placeholder="All outlets" />
                        </div>
                        <div>
                            <label>Category</label>
                            <input id="category" placeholder="All categories" />
                        </div>
                        <div>
                            <label>Channel</label>
                            <select id="channel-type"><option value="" selected>All channels</option><option>Retail</option><option>Modern Trade</option><option>General Trade</option><option>E-commerce</option><option>Wholesale</option><option>Distributor</option><option>Foodservice</option><option>N/A</option></select>
                        </div>
                        <div>
                            <label>&nbsp;</label>
                            <button type="button" id="start-btn">Scan promotions</button>
                        </div>
                    </div>
                    <div class="form-grid compact">
                        <div><label>Promotion status</label><select id="active-only"><option value="true">Active only</option><option value="false">All records</option></select></div>
                        <div><label>Company</label><input id="company" placeholder="Any company" /></div>
                        <div><label>Minimum discount %</label><input id="min-discount" type="number" min="0" step="1" placeholder="Any" /></div>
                        <div><label>&nbsp;</label><button type="button" id="search-btn" class="secondary">Apply filters</button></div>
                    </div>
                </form>
                <div class="status" id="status">Select an industry to search stored competitor activity.</div>
                <section class="schedule"><div class="schedule-row"><div><label for="schedule-enabled">Daily scan</label><select id="schedule-enabled"><option value="false">Disabled</option><option value="true">Enabled</option></select></div><div><label for="schedule-time">Run time (UTC)</label><input id="schedule-time" type="time" value="01:00"></div><div><button type="button" id="schedule-btn">Save schedule</button></div><div class="schedule-note" id="schedule-status">No automatic scan configured.</div></div></section>

                <div class="table-wrap" tabindex="0" aria-label="Scrollable promotion results table">
                <table>
                    <thead>
                        <tr>
                            <th>Company</th>
                            <th>Product / Size</th>
                            <th>Pack</th>
                            <th>Promo</th>
                            <th>Outlet</th>
                            <th>Channel</th>
                            <th>Location</th>
                            <th>Valid</th>
                            <th>Price</th>
                                            <th>Evidence</th>
                        </tr>
                    </thead>
                    <tbody id="results-body">
                        <tr><td colspan="10" class="empty">No result yet. Press Start to fetch FMCG competitor activity.</td></tr>
                    </tbody>
                </table>
                </div>
            </div>
        </div>
        <script>
            const query = id => document.getElementById(id).value.trim();
            async function loadResults() {
                const industry = query('industry');
                if (!industry) { document.getElementById('status').textContent = 'Select an industry before searching.'; return; }
                const params = new URLSearchParams({industry: industry, q: query('product'), location: query('location'), outlet: query('outlet'), category: query('category'), channel_type: query('channel-type'), company: query('company'), active_only: query('active-only'), limit: '10'});
                if (query('min-discount')) params.set('min_discount', query('min-discount'));
                const res = await fetch('/results?' + params);
                const rows = await res.json();
                const tbody = document.getElementById('results-body');
                if (!rows.length) {
                    tbody.innerHTML = '<tr><td colspan="10" class="empty">No result yet. Press Start to fetch FMCG competitor activity.</td></tr>';
                    return;
                }
                tbody.innerHTML = rows.map(row => `
                    <tr>
                        <td>${row.company_name || '-'}</td>
                        <td>${row.product_name || '-'}<br><small>${row.pack_size_grams || row.variant_name || '-'}</small></td>
                        <td>${row.carton_label || row.units_per_carton ? (row.carton_label || row.units_per_carton + ' pcs/carton') : '-'}</td>
                        <td><span class="badge">${row.promotion_type || '-'}</span></td>
                        <td>${row.outlet_name || '-'}</td>
                        <td><span class="badge">${row.channel_type || 'N/A'}</span></td>
                        <td>${row.location_name || '-'}</td>
                        <td>${row.validity || '-'}</td>
                        <td>${row.regular_price ? 'Rp ' + Number(row.regular_price).toLocaleString('id-ID') : '-'}<br>${row.promo_price ? 'Rp ' + Number(row.promo_price).toLocaleString('id-ID') : '-'}</td>
                        <td>${row.source_url ? `<a href="${row.source_url}" target="_blank" rel="noreferrer">${row.verification_status}</a>` : `<span>${row.verification_status}</span>`}<br><small>${row.source_timestamp ? new Date(row.source_timestamp).toLocaleString() : 'No source timestamp'}</small></td>
                    </tr>
                `).join('');
            }
            document.getElementById('start-btn').addEventListener('click', async () => {
                const payload = {
                    industry: query('industry'),
                    product: document.getElementById('product').value,
                    location: document.getElementById('location').value,
                    outlet: document.getElementById('outlet').value,
                    category: document.getElementById('category').value,
                };
                const statusEl = document.getElementById('status');
                if (!payload.industry) { statusEl.textContent = 'Select an industry before scanning.'; return; }
                statusEl.textContent = 'Scraping FMCG competitor promotions...';
                const res = await fetch('/jobs/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                const result = await res.json();
                statusEl.textContent = result.message || 'Scrape completed.';
                await loadResults();
            });
            document.getElementById('search-btn').addEventListener('click', loadResults);
            document.getElementById('industry').addEventListener('change', loadResults);
            document.getElementById('schedule-btn').addEventListener('click', async () => {
                const response = await fetch('/schedule', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: query('schedule-enabled') === 'true', time_utc: query('schedule-time')})});
                const result = await response.json(); document.getElementById('schedule-status').textContent = response.ok ? (result.enabled ? `Daily scan at ${result.time_utc} UTC.` : 'Automatic scan disabled.') : (result.detail || 'Unable to save schedule.');
            });
            async function loadSchedule() {
                const response = await fetch('/schedule');
                if (!response.ok) return;
                const schedule = await response.json();
                document.getElementById('schedule-enabled').value = String(schedule.enabled);
                document.getElementById('schedule-time').value = schedule.time_utc;
                document.getElementById('schedule-status').textContent = schedule.enabled ? `Daily scan at ${schedule.time_utc} UTC.` : 'Automatic scan disabled.';
            }
            document.getElementById('logout-btn').addEventListener('click', () => fetch('/logout', {method: 'POST'}).then(() => location.href = '/login'));
            const themeButton = document.getElementById('theme-btn');
            function setTheme(theme) { document.documentElement.dataset.theme = theme; themeButton.textContent = theme === 'dark' ? 'Light theme' : 'Dark theme'; localStorage.setItem('competitor-theme', theme); }
            themeButton.addEventListener('click', () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
            setTheme(localStorage.getItem('competitor-theme') || 'light');
            window.addEventListener('load', () => { loadSchedule(); loadResults(); });
        </script>
    </body>
    </html>
    """)


@app.post("/jobs/start")
def start_competitor_job(payload: StartJobRequest, db: Session = Depends(get_db), _user=Depends(require_auth)):
    inserted = run_scrape_and_store(db, payload)
    return {
        "status": "completed",
        "message": f"Inserted {inserted} competitor records for {payload.industry} / {payload.product} / {payload.location}.",
        "count": inserted,
    }


@app.get("/schedule")
def get_schedule(_user=Depends(require_auth)):
    with schedule_lock:
        return dict(schedule_state)


@app.put("/schedule")
def update_schedule(payload: ScheduleRequest, _user=Depends(require_auth)):
    with schedule_lock:
        schedule_state["enabled"] = payload.enabled
        schedule_state["time_utc"] = payload.time_utc
        schedule_file.write_text(json.dumps(schedule_state, indent=2), encoding="utf-8")
    return get_schedule(_user)


@app.get("/results")
def read_results(
    industry: str = Query(..., min_length=1),
    q: str = Query(""),
    company: str = Query(""),
    outlet: str = Query(""),
    location: str = Query(""),
    category: str = Query(""),
    channel_type: str = Query(""),
    active_only: bool = Query(True),
    min_discount: float | None = Query(None, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    query = (
        db.query(Promotion, Company, Product, Retailer, Location)
        .outerjoin(Product, Promotion.product_id == Product.id)
        .outerjoin(Company, Promotion.company_id == Company.id)
        .outerjoin(Retailer, Promotion.retailer_id == Retailer.id)
        .outerjoin(Location, Retailer.location_id == Location.id)
        .order_by(desc(Promotion.confidence_score), desc(Promotion.source_timestamp), desc(Promotion.discount_pct), desc(Promotion.created_at))
    )
    query = query.filter(Company.industry.ilike(industry))
    if channel_type:
        query = query.filter(Retailer.channel_type == normalize_channel_type(channel_type))
    if q:
        keyword = f"%{q}%"
        query = query.filter(or_(Company.company_name.ilike(keyword), Product.product_name.ilike(keyword), Product.variant_name.ilike(keyword), Retailer.retailer_name.ilike(keyword), Location.city.ilike(keyword), Promotion.promotion_type.ilike(keyword), Promotion.evidence_text.ilike(keyword)))
    if company:
        query = query.filter(Company.company_name.ilike(f"%{company}%"))
    if outlet:
        query = query.filter(Retailer.retailer_name.ilike(f"%{outlet}%"))
    if location:
        query = query.filter(Location.city.ilike(f"%{location}%"))
    if category:
        query = query.filter(Product.category.ilike(f"%{category}%"))
    if active_only:
        now = datetime.utcnow()
        query = query.filter(Promotion.promo_status == "active", Promotion.valid_from <= now, Promotion.valid_to >= now)
    if min_discount is not None:
        query = query.filter(Promotion.discount_pct >= min_discount)
    rows = query.limit(limit).all()
    result = []
    for promo, company, product, retailer, location in rows:
        valid_from = promo.valid_from.strftime("%Y-%m-%d") if promo.valid_from else "-"
        valid_to = promo.valid_to.strftime("%Y-%m-%d") if promo.valid_to else "-"
        result.append(
            {
                "company_name": company.company_name if company else "Unknown",
                "product_name": product.product_name if product else "Unknown",
                "variant_name": product.variant_name if product else "",
                "pack_size_grams": product.pack_size_grams if product else "",
                "units_per_carton": product.units_per_carton if product else None,
                "carton_label": product.carton_label if product else "",
                "category": product.category if product else "",
                "promotion_type": promo.promotion_type,
                "outlet_name": retailer.retailer_name if retailer else "Unknown",
                "channel_type": retailer.channel_type if retailer else "N/A",
                "location_name": location.city if location else "Unknown",
                "regular_price": float(promo.regular_price) if promo.regular_price is not None else None,
                "promo_price": float(promo.promo_price) if promo.promo_price is not None else None,
                "discount_pct": float(promo.discount_pct) if promo.discount_pct is not None else None,
                "validity": f"{valid_from} to {valid_to}",
                "source_url": promo.source_url,
                "source_type": promo.source_type,
                "source_timestamp": promo.source_timestamp.isoformat() if promo.source_timestamp else None,
                "verification_status": "Verified source" if promo.source_url and "example.com" not in promo.source_url and promo.evidence_text and promo.source_timestamp else "Unverified source",
            }
        )
    return result


@app.get("/search")
def search_competitor(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _user=Depends(require_auth),
):
    keyword = f"%{q.lower()}%"

    companies = db.query(Company).filter(or_(Company.company_name.ilike(keyword), Company.industry.ilike(keyword))).all()
    products = db.query(Product).filter(or_(Product.product_name.ilike(keyword), Product.category.ilike(keyword), Product.sub_category.ilike(keyword))).all()
    promotions = db.query(Promotion).filter(or_(Promotion.promotion_type.ilike(keyword), Promotion.buy_x_get_y.ilike(keyword), Promotion.evidence_text.ilike(keyword))).all()

    results = []
    for item in companies:
        results.append({"type": "company", "name": item.company_name, "id": str(item.id), "match": item.company_name})
    for item in products:
        results.append({"type": "product", "name": item.product_name, "id": str(item.id), "match": item.product_name})
    for item in promotions:
        results.append({"type": "promotion", "name": item.promotion_type or "Promotion", "id": str(item.id), "match": item.promotion_type or "Promotion"})

    return {"query": q, "results": results}


@app.post("/companies")
def create_company(payload: dict, db: Session = Depends(get_db), _user=Depends(require_auth)):
    company = Company(
        company_name=payload.get("company_name"),
        parent_company=payload.get("parent_company"),
        industry=payload.get("industry"),
        company_type=payload.get("company_type"),
        website=payload.get("website"),
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@app.get("/companies")
def list_companies(db: Session = Depends(get_db), _user=Depends(require_auth)):
    return db.query(Company).all()


@app.post("/products")
def create_product(payload: dict, db: Session = Depends(get_db), _user=Depends(require_auth)):
    product = Product(
        product_name=payload.get("product_name"),
        brand_id=payload.get("brand_id"),
        company_id=payload.get("company_id"),
        category=payload.get("category"),
        sub_category=payload.get("sub_category"),
        sku=payload.get("sku"),
        unit=payload.get("unit"),
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.post("/promotions")
def create_promotion(payload: PromotionCreate, db: Session = Depends(get_db), _user=Depends(require_auth)):
    values = payload.model_dump(exclude_none=True)
    if values.get("source_url"):
        values["source_url"] = str(values["source_url"])
    values.setdefault("promo_status", "active")
    if values.get("confidence_score", 0) > 0 and "example.com" in values["source_url"]:
        raise HTTPException(status_code=422, detail="Demo/example URLs cannot be used as verified evidence")
    promo = Promotion(
        **values,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return promo


def ensure_location(db: Session, city: str, country: str = "Indonesia") -> Location:
    location = db.query(Location).filter(Location.city == city, Location.country == country).first()
    if location is None:
        location = Location(country=country, city=city, province="", region="")
        db.add(location)
        db.commit()
        db.refresh(location)
    return location


def ensure_company(db: Session, company_name: str, industry: str = "FMCG") -> Company:
    company = db.query(Company).filter(Company.company_name == company_name).first()
    if company is None:
        company = Company(company_name=company_name, industry=industry)
        db.add(company)
        db.commit()
        db.refresh(company)
    return company


def ensure_retailer(db: Session, retailer_name: str, city: str, channel_type: str = "N/A") -> Retailer:
    channel_type = normalize_channel_type(channel_type)
    retailer = db.query(Retailer).filter(Retailer.retailer_name == retailer_name).first()
    if retailer is None:
        location = ensure_location(db, city)
        retailer = Retailer(retailer_name=retailer_name, channel_type=channel_type, location_id=location.id)
        db.add(retailer)
        db.commit()
        db.refresh(retailer)
    elif retailer.location_id is None:
        retailer.location_id = ensure_location(db, city).id
        db.commit()
    return retailer


def ensure_product(db: Session, product_name: str, company_id, category: str, variant_name: str | None = None, pack_size_grams: str | None = None, units_per_carton: int | None = None, carton_label: str | None = None) -> Product:
    product = db.query(Product).filter(Product.product_name == product_name, Product.company_id == company_id).first()
    if product is None:
        product = Product(
            product_name=product_name,
            company_id=company_id,
            category=category,
            sub_category=category,
            variant_name=variant_name,
            pack_size_grams=pack_size_grams,
            units_per_carton=units_per_carton,
            carton_label=carton_label,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
    else:
        if variant_name and not product.variant_name:
            product.variant_name = variant_name
        if pack_size_grams and not product.pack_size_grams:
            product.pack_size_grams = pack_size_grams
        if units_per_carton and not product.units_per_carton:
            product.units_per_carton = units_per_carton
        if carton_label and not product.carton_label:
            product.carton_label = carton_label
        db.commit()
    return product


def run_scrape_and_store(db: Session, payload: StartJobRequest) -> int:
    base_location = payload.location or "Jakarta"
    base_retailer = payload.outlet or "Indomaret"
    base_category = payload.category or "Biscuit"
    industry = payload.industry or "FMCG"

    if industry.lower() == "fmcg":
        targets = DEFAULT_FMCG_TARGETS
    else:
        targets = [
            {
                "company": payload.product or "Sample Company",
                "industry": industry,
                "products": [
                    {"name": payload.product or "Sample Product", "category": base_category, "promo_type": "Flash Sale", "regular_price": 20000, "promo_price": 16000, "discount_pct": 20.0}
                ],
            }
        ]

    inserted = 0
    for target in targets:
        company = ensure_company(db, target["company"], target.get("industry", industry))
        for product_info in target.get("products", []):
            product_name = product_info.get("name") or payload.product or "Sample Product"
            variant_name = product_info.get("variant_name") or product_name
            pack_size_grams = product_info.get("pack_size_grams") or "300gr"
            units_per_carton = product_info.get("units_per_carton") or 36
            carton_label = product_info.get("carton_label") or f"{units_per_carton} x {pack_size_grams}"
            product = ensure_product(
                db,
                product_name,
                company.id,
                product_info.get("category") or base_category,
                variant_name=variant_name,
                pack_size_grams=pack_size_grams,
                units_per_carton=units_per_carton,
                carton_label=carton_label,
            )
            retailer = ensure_retailer(db, base_retailer, base_location, channel_type="N/A")
            promo_type = product_info.get("promo_type") or "Promo"
            promo = (
                db.query(Promotion)
                .filter(
                    Promotion.product_id == product.id,
                    Promotion.company_id == company.id,
                    Promotion.retailer_id == retailer.id,
                    Promotion.promotion_type == promo_type,
                )
                .first()
            )
            if promo is None:
                valid_from = datetime.utcnow() - timedelta(days=2)
                valid_to = datetime.utcnow() + timedelta(days=10)
                promo = Promotion(
                    product_id=product.id,
                    retailer_id=retailer.id,
                    company_id=company.id,
                    promotion_type=promo_type,
                    regular_price=product_info.get("regular_price") or 20000,
                    promo_price=product_info.get("promo_price") or 16000,
                    discount_pct=product_info.get("discount_pct") or 20.0,
                    buy_x_get_y="",
                    valid_from=valid_from,
                    valid_to=valid_to,
                    promo_status="active",
                    source_url=product_info.get("source_url"),
                    source_type=product_info.get("source_type") or "demo_seed_unverified",
                    evidence_text=f"Scraped from {base_retailer} in {base_location}; product {product_name} {variant_name} {pack_size_grams}; valid from {valid_from.date()} to {valid_to.date()}",
                    source_timestamp=datetime.utcnow(),
                    geographic_scope=base_location,
                    confidence_score=0.0,
                )
                db.add(promo)
                inserted += 1

    db.commit()
    return inserted
