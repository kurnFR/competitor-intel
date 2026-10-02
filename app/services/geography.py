"""Geography handling (PRD 9-10): keep the source wording, normalise separately, never assume nationwide."""
from __future__ import annotations

import re
from typing import Iterable, Optional, Set

UNKNOWN = "UNKNOWN"            # the source did not say where the promotion is valid
UNMAPPED = "UNMAPPED"          # stated, but not understood well enough to place (kept visible, never guessed)
MULTI_REGION = "MULTI_REGION"  # stated for several regions at once
NATIONAL = "NATIONAL"
ONLINE = "ONLINE"
STORE_SPECIFIC = "STORE_SPECIFIC"

REGION_LABELS = {
    "JAWA": "Jawa", "SUMATERA": "Sumatera", "KALIMANTAN": "Kalimantan", "SULAWESI": "Sulawesi",
    "BALI_NUSRA": "Bali & Nusa Tenggara", "MALUKU": "Maluku", "PAPUA": "Papua", "JABODETABEK": "Jabodetabek",
    NATIONAL: "Nationwide (stated)", ONLINE: "Online only", STORE_SPECIFIC: "Selected stores",
    MULTI_REGION: "Several regions", UNMAPPED: "Stated, not mapped", UNKNOWN: "Not stated",
}

# Words that appear in the source wording -> region. Matched as whole words, case-insensitively.
_KEYWORDS = {
    "JABODETABEK": ["jabodetabek", "jabodetabeka", "jakarta bogor depok tangerang bekasi", "jabotabek", "jakarta", "bogor", "depok", "tangerang", "bekasi"],
    "JAWA": ["jawa", "java", "banten", "jawa barat", "jawa tengah", "jawa timur", "diy", "yogyakarta", "bandung", "semarang",
             "surabaya", "malang", "solo", "surakarta", "cirebon", "serang", "sidoarjo"],
    "SUMATERA": ["sumatera", "sumatra", "aceh", "medan", "sumut", "sumbar", "padang", "riau", "pekanbaru", "jambi", "palembang",
                 "sumsel", "bengkulu", "lampung", "bandar lampung", "batam", "kepulauan riau"],
    "KALIMANTAN": ["kalimantan", "kalbar", "pontianak", "kalteng", "palangkaraya", "kalsel", "banjarmasin", "kaltim", "samarinda",
                   "balikpapan", "kaltara", "tarakan"],
    "SULAWESI": ["sulawesi", "sulsel", "makassar", "sulut", "manado", "sulteng", "palu", "sultra", "kendari", "gorontalo", "sulbar"],
    "BALI_NUSRA": ["bali", "denpasar", "nusa tenggara", "ntb", "ntt", "lombok", "mataram", "kupang", "flores", "sumbawa"],
    "MALUKU": ["maluku", "ambon", "ternate", "halmahera"],
    "PAPUA": ["papua", "jayapura", "sorong", "merauke", "manokwari"],
    ONLINE: ["online", "daring", "e-commerce", "ecommerce", "aplikasi", "app only", "website", "web only"],
    NATIONAL: ["seluruh indonesia", "se-indonesia", "se indonesia", "nasional", "nationwide", "all indonesia", "seluruh gerai", "semua kota"],
}
_STORE = ["toko tertentu", "gerai tertentu", "selected stores", "selected store", "di toko", "store tertentu", "cabang tertentu"]
_EXCEPTION = re.compile(r"\b(kecuali|selain|except|excluding|tidak berlaku)\b", re.I)
_PATTERNS = {code: re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?![a-z0-9])", re.I)
             for code, words in _KEYWORDS.items()}
_STORE_RE = re.compile("|".join(re.escape(w) for w in _STORE), re.I)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def clean_wording(text: Optional[str]) -> Optional[str]:
    """Verbatim source wording (whitespace tidied only). None when nothing was stated."""
    if text is None:
        return None
    text = _squash(str(text))
    return text[:255] if text else None


def normalize_region(text: Optional[str]) -> str:
    """Map source wording to one macro region code. Unknown stays UNKNOWN; ambiguity is never resolved by guessing."""
    wording = clean_wording(text)
    if not wording:
        return UNKNOWN
    if _EXCEPTION.search(wording):
        return UNMAPPED            # "everywhere except X" cannot be reduced to one region without guessing
    found: Set[str] = {code for code, pattern in _PATTERNS.items() if pattern.search(wording)}
    if _STORE_RE.search(wording):
        found.add(STORE_SPECIFIC)
    # Jakarta-area words also match the Jabodetabek bucket on purpose; a plain "Jawa" mention beside them is the same island group
    if found == {"JABODETABEK", "JAWA"}:
        found = {"JABODETABEK"}
    if NATIONAL in found and len(found) > 1:
        found.discard(NATIONAL)    # "Seluruh Indonesia, online" -> the specific channel/region is the more precise statement
    if not found:
        return UNMAPPED
    return next(iter(found)) if len(found) == 1 else MULTI_REGION


def identity_token(text: Optional[str]) -> Optional[str]:
    """What geography contributes to a promotion's identity: different regions are different promotions.

    Unknown -> None (so unknown-vs-unknown promotions still match). Store-specific/unmapped/multi
    wordings keep their normalised wording so different store sets are never merged.
    """
    wording = clean_wording(text)
    region = normalize_region(wording)
    if region == UNKNOWN:
        return None
    if region in (STORE_SPECIFIC, UNMAPPED, MULTI_REGION):
        return f"{region}:{wording.lower()}"
    return region


def appears_in_source(wording: Optional[str], source_text: str) -> bool:
    """Anti-hallucination check: the wording must really occur in the page text."""
    wording = clean_wording(wording)
    if not wording:
        return False
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    return norm(wording) in norm(source_text)


def regions_in(values: Iterable[Optional[str]]) -> Set[str]:
    return {normalize_region(v) for v in values}
