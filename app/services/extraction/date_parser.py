"""Indonesian retail promotional date and banner date parsing utilities.

Handles common Modern Trade flyer date patterns:
- Indonesian month names and abbreviations (e.g. '12 - 14 Mei 2026', '1-15 Okt')
- Banner dates with header noise (e.g. 'Periode: 12 - 14 Mei 2026', 'Berlaku 24 - 26 Juli 2026')
- Cross-month validity ranges (e.g. '28 Oktober - 3 November 2026')
- Cross-year validity ranges (e.g. '28 Des 2025 - 05 Jan 2026', '28 Des - 3 Jan 2026')
- Multi-week validity ranges (e.g. 'Minggu ke-1: 1 - 7 Juni 2026', 'Week 1: 1 - 7 Nov 2026')
- S/d or s.d. / sampai / hingga delimiters (e.g. '01 s/d 15 Maret 2026', 's/d 15 Mei 2026')
- Numeric slash, dash, and dot formats (e.g. '12/05/2026 - 14/05/2026', '12.05.2026')
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

INDONESIAN_MONTH_MAP: Dict[str, int] = {
    "januari": 1, "jan": 1, "january": 1,
    "februari": 2, "feb": 2, "febuari": 2, "february": 2, "pebruari": 2,
    "maret": 3, "mar": 3, "march": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "agustus": 8, "ags": 8, "agt": 8, "agu": 8, "aug": 8, "august": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "oct": 10, "october": 10,
    "november": 11, "nov": 11, "nopember": 11, "nop": 11,
    "desember": 12, "des": 12, "dec": 12, "december": 12,
}

_MONTH_REGEX = r"(?:januari|februari|febuari|pebruari|maret|april|mei|juni|juli|agustus|september|oktober|november|nopember|desember|jan|feb|mar|apr|may|jun|jul|ags|agt|agu|aug|sep|sept|okt|oct|nov|nop|des|dec)"

_PREFIX_CLEAN_RE = re.compile(
    r"(?i)^(?:periode\s*promosi|periode\s*promo|periode|promo\s*jsm|berlaku|valid|katalog\s*super\s*hemat|promo\s*koran|promo\s*mingguan|edisi\s*ke-?\d+|minggu\s*ke-?\d+|minggu\s*\d+|week\s*\d+|promo\s*\d+\s*(?:minggu|pekan)|periode\s*\d+\s*(?:minggu|pekan))\s*[:\-–—]?\s*",
)

_PACK_SIZE_RE = re.compile(
    r"(?:(\d+(?:[.,]\d+)?\s*[x\u00d7]\s*\d+(?:[.,]\d+)?\s*(?:kg|kilogram|gram|gr|g|ml|l|liter|pcs|buah|sachet|pack))\b|"
    r"(\d+(?:[.,]\d+)?\s*(?:kg|kilogram|gram|gr|g|ml|l|liter|pcs|buah|sachet|pack))\b)",
    re.IGNORECASE,
)

_THOUSANDS_DOT = re.compile(r"\d{1,3}(\.\d{3})+(,\d+)?")


def extract_pack_size_from_name(product_name: Optional[str]) -> Optional[str]:
    """Extract pack size (e.g. '133g', '250 gr', '1.6 kg', '12 x 25g') from product name."""
    if not product_name:
        return None
    m = _PACK_SIZE_RE.search(str(product_name))
    if m:
        return (m.group(1) or m.group(2)).strip()
    return None


def sanitize_price(value: Any) -> Optional[float]:
    """Parse string/numeric prices in Indonesian currency format into a valid float.

    Handles 'Rp 14.500', '14.500', '8200', '14500.0', etc.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return round(num, 2) if 0 <= num < 100_000_000 else None

    text = re.sub(r"(?i)rp\.?|idr|\s", "", str(value).strip())
    if not text:
        return None

    if _THOUSANDS_DOT.fullmatch(text):
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")

    try:
        num = float(text)
        return round(num, 2) if 0 <= num < 100_000_000 else None
    except (ValueError, TypeError):
        return None


def _clean_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"[\t\r\n]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _resolve_year(year_val: Optional[int], default_year: Optional[int] = None) -> int:
    if year_val is not None:
        if year_val < 100:
            return 2000 + year_val
        return year_val
    return default_year or date.today().year


def parse_indonesian_date(text: Optional[str], default_year: Optional[int] = None) -> Optional[date]:
    """Parse a single Indonesian or ISO date string into a datetime.date object."""
    if not text or not str(text).strip():
        return None

    raw = _clean_text(str(text))
    # Strip common prefixes like 's/d', 'sd', 'sampai', 'hingga', 'maks'
    raw = re.sub(r"(?i)^(?:s/?d\.?|sampai|hingga|maks\.?|tgl\.?|tanggal)\s+", "", raw).strip()

    # 1. ISO format: YYYY-MM-DD
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw[:10])
    except ValueError:
        pass

    # 2. Text with month name: e.g. "12 Mei 2026", "12-Mei-2026", "12 Mei '26", "12 Mei"
    m = re.match(rf"^(\d{{1,2}})[\s\-_]+({_MONTH_REGEX})(?:[\s\-_]+(?:'?(\d{{2,4}})))?$", raw, re.I)
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower()
        month = INDONESIAN_MONTH_MAP.get(month_str)
        year_str = m.group(3)
        year = _resolve_year(int(year_str) if year_str else None, default_year)
        if month and 1 <= day <= 31:
            try:
                return date(year, month, day)
            except ValueError:
                return None

    # 3. Numeric slash/dash/dot: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](?:'?(\d{2,4}))?$", raw)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year_str = m.group(3)
        year = _resolve_year(int(year_str) if year_str else None, default_year)
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return date(year, month, day)
            except ValueError:
                return None

    # 4. YYYY/MM/DD
    m = re.match(r"^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})$", raw)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return date(year, month, day)
            except ValueError:
                return None

    return None


def parse_indonesian_date_range(
    text: Optional[str],
    default_year: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Parse a date range string into (start_date_iso, end_date_iso).

    Supports:
    - Same month: "12 - 14 Mei 2026", "1 - 15 Oktober 2026", "01 s/d 15 Maret 2026"
    - Cross month: "28 Oktober - 3 November 2026", "28 Okt - 03 Nov 2026"
    - Cross year: "28 Des 2025 - 5 Jan 2026", "28 Des - 3 Jan 2026"
    - Numeric ranges: "12/05/2026 - 14/05/2026", "12.05.2026 s/d 14.05.2026"
    - Single end date: "s/d 15 Mei 2026", "sampai 15 Mei 2026"
    - Banner prefixes: "Periode: 12 - 14 Mei 2026", "Promo JSM 24 - 26 Juli 2026"
    - Multi-week prefixes: "Minggu ke-1: 1 - 7 Juni 2026", "Week 1 (1 - 7 Nov 2026)"
    """
    if not text or not str(text).strip():
        return None, None

    raw = _clean_text(str(text))

    # Strip surrounding parenthesis if entire string is parenthesized e.g. "(12 - 14 Mei 2026)"
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1].strip()

    # Strip banner / header prefixes
    raw = _PREFIX_CLEAN_RE.sub("", raw).strip()

    # Check parenthesized or colon sub-ranges inside multi-week / banner expressions:
    # e.g., "Periode 2 Minggu (1 - 14 Mei 2026)" or "Promo 2 Pekan: 1 - 14 Mei 2026"
    sub_range = re.search(r"[\(:]\s*([^)]+)\s*\)?", raw)
    if sub_range and sub_range.group(1).strip() != raw:
        candidate_s, candidate_e = parse_indonesian_date_range(sub_range.group(1), default_year=default_year)
        if candidate_s or candidate_e:
            return candidate_s, candidate_e

    # Multi-week / multi-day duration expressions:
    # e.g., "Berlaku 2 minggu mulai 1 Mei 2026" or "Berlaku 3 hari sejak 12 Mei 2026"
    duration_match = re.search(r"(?:berlaku\s+)?(\d+)\s*(minggu|pekan|hari)", raw, re.IGNORECASE)
    start_match = re.search(rf"(?:mulai|sejak)(?:\s+tanggal)?\s+(\d{{1,2}})[\s\-_]+({_MONTH_REGEX})(?:[\s\-_]+(?:'?(\d{{2,4}})))?", raw, re.IGNORECASE)
    if duration_match and start_match:
        qty, unit = int(duration_match.group(1)), duration_match.group(2).lower()
        d_val, m_str, y_str = start_match.groups()
        m = INDONESIAN_MONTH_MAP.get(m_str.lower())
        y = _resolve_year(int(y_str) if y_str else None, default_year)
        if m:
            try:
                start_dt = date(y, m, int(d_val))
                days = (qty * 7 - 1) if unit in ("minggu", "pekan") else (qty - 1)
                end_dt = start_dt + timedelta(days=max(0, days))
                return start_dt.isoformat(), end_dt.isoformat()
            except ValueError:
                pass

    # If starts with s/d or sampai (end date only)
    if re.match(r"(?i)^(?:s/?d\.?|sampai|hingga|maks\.?)\s+", raw):
        end_d = parse_indonesian_date(raw, default_year=default_year)
        return None, end_d.isoformat() if end_d else None

    # Normalise delimiter tokens: ' s/d ', ' s.d. ', ' sd ', ' sampai ', ' hingga ', ' to ', ' - ', ' – ', ' — '
    # Replace them with standard ' - '
    norm_range = re.sub(
        r"(?i)\s+(?:s/?d\.?|sd|s\.d\.|sampai|hingga|to|s/d)\s+",
        " - ",
        raw,
    )
    # Also handle dashes with spaces around them or between digits/months
    norm_range = re.sub(r"\s*[–—]\s*", " - ", norm_range)

    # 1. Cross-month or cross-year text pattern:
    # "28 Oktober 2025 - 3 November 2026" or "28 Oktober - 3 November 2026"
    m_cross = re.search(
        rf"(\d{{1,2}})[\s\-_]+({_MONTH_REGEX})(?:[\s\-_]+(?:'?(\d{{2,4}})))?\s*[-]\s*(\d{{1,2}})[\s\-_]+({_MONTH_REGEX})(?:[\s\-_]+(?:'?(\d{{2,4}})))?",
        norm_range,
        re.I,
    )
    if m_cross:
        d1 = int(m_cross.group(1))
        m1_str = m_cross.group(2).lower()
        m1 = INDONESIAN_MONTH_MAP.get(m1_str)
        y1_str = m_cross.group(3)

        d2 = int(m_cross.group(4))
        m2_str = m_cross.group(5).lower()
        m2 = INDONESIAN_MONTH_MAP.get(m2_str)
        y2_str = m_cross.group(6)

        if y2_str:
            y2 = _resolve_year(int(y2_str), default_year)
            if y1_str:
                y1 = _resolve_year(int(y1_str), default_year)
            else:
                y1 = y2 - 1 if (m1 and m2 and m1 > m2) else y2
        else:
            y1 = _resolve_year(int(y1_str) if y1_str else None, default_year)
            y2 = y1 + 1 if (m1 and m2 and m1 > m2) else y1

        if m1 and m2:
            try:
                start_dt = date(y1, m1, d1)
                end_dt = date(y2, m2, d2)
                return start_dt.isoformat(), end_dt.isoformat()
            except ValueError:
                pass

    # 2. Same-month text pattern:
    # "12 - 14 Mei 2026" or "12-14 Mei 2026" or "12 - 14 Mei"
    m_same = re.search(
        rf"(\d{{1,2}})\s*[-]\s*(\d{{1,2}})[\s\-_]+({_MONTH_REGEX})(?:[\s\-_]+(?:'?(\d{{2,4}})))?",
        norm_range,
        re.I,
    )
    if m_same:
        d1 = int(m_same.group(1))
        d2 = int(m_same.group(2))
        month_str = m_same.group(3).lower()
        month = INDONESIAN_MONTH_MAP.get(month_str)
        year_str = m_same.group(4)
        year = _resolve_year(int(year_str) if year_str else None, default_year)

        if month and 1 <= d1 <= 31 and 1 <= d2 <= 31:
            try:
                start_dt = date(year, month, d1)
                end_dt = date(year, month, d2)
                return start_dt.isoformat(), end_dt.isoformat()
            except ValueError:
                pass

    # 3. Numeric slash/dash range:
    # "12/05/2026 - 14/05/2026" or "12.05.2026 - 14.05.2026" or "2026-05-12 - 2026-05-14"
    if " - " in norm_range:
        parts = [p.strip() for p in norm_range.split(" - ", 1)]
        if len(parts) == 2:
            d1_res = parse_indonesian_date(parts[0], default_year=default_year)
            d2_res = parse_indonesian_date(parts[1], default_year=default_year)
            if d1_res and d2_res:
                return d1_res.isoformat(), d2_res.isoformat()
            if d2_res and not d1_res:
                return None, d2_res.isoformat()

    # 4. Single date check
    single_d = parse_indonesian_date(raw, default_year=default_year)
    if single_d:
        return single_d.isoformat(), single_d.isoformat()

    return None, None


def extract_banner_validity(
    payload: Dict[str, Any],
    default_year: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Extract and parse banner validity dates from top-level flyer payload.

    Checks keys: 'banner_date', 'validity_period', 'valid_period', 'period', 'periode',
    'flyer_period', 'flyer_date', 'header_date', 'catalog_period', 'dates', 'start_date', 'end_date'.
    """
    banner_keys = (
        "banner_date", "validity_period", "valid_period", "period", "periode",
        "flyer_period", "flyer_date", "header_date", "catalog_period", "dates",
        "date_banner", "promo_period",
    )

    for k in banner_keys:
        val = payload.get(k)
        if isinstance(val, str) and val.strip():
            start_iso, end_iso = parse_indonesian_date_range(val, default_year=default_year)
            if start_iso or end_iso:
                return start_iso, end_iso

    # Also check if top-level has start_date / end_date
    top_start = payload.get("start_date")
    top_end = payload.get("end_date")
    start_iso = None
    end_iso = None

    if isinstance(top_start, str) and top_start.strip():
        # Check if top_start itself contains a range
        if any(sep in top_start for sep in (" - ", " s/d ", " sd ", " sampai ")):
            s_iso, e_iso = parse_indonesian_date_range(top_start, default_year=default_year)
            if s_iso or e_iso:
                start_iso, end_iso = s_iso, e_iso
        else:
            s_dt = parse_indonesian_date(top_start, default_year=default_year)
            if s_dt:
                start_iso = s_dt.isoformat()

    if isinstance(top_end, str) and top_end.strip() and not end_iso:
        e_dt = parse_indonesian_date(top_end, default_year=default_year)
        if e_dt:
            end_iso = e_dt.isoformat()

    return start_iso, end_iso
