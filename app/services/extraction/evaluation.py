"""Measure extraction quality against hand-labelled examples."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

_TOKEN = re.compile(r"[a-z0-9]+")
NUMERIC_FIELDS = ("promo_price", "regular_price", "discount_percentage")


def _tokens(name: Optional[str]) -> frozenset:
    return frozenset(_TOKEN.findall((name or "").lower()))


def names_match(expected: Optional[str], actual: Optional[str]) -> bool:
    """Same product if one name's words are all contained in the other's (ignores word order and extras)."""
    a, b = _tokens(expected), _tokens(actual)
    return bool(a and b) and (a <= b or b <= a)


def _close(x: Any, y: Any, tolerance: float = 0.01) -> bool:
    try:
        x, y = float(x), float(y)
    except (TypeError, ValueError):
        return False
    return abs(x - y) <= max(tolerance * max(abs(x), abs(y)), 0.01)


@dataclass
class EvalReport:
    expected: int = 0
    extracted: int = 0
    matched: int = 0
    field_checks: Dict[str, List[bool]] = field(default_factory=dict)
    missed: List[str] = field(default_factory=list)
    unexpected: List[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.matched / self.extracted if self.extracted else 0.0

    @property
    def recall(self) -> float:
        return self.matched / self.expected if self.expected else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def field_accuracy(self) -> Dict[str, float]:
        return {k: sum(v) / len(v) for k, v in self.field_checks.items() if v}

    def merge(self, other: "EvalReport") -> None:
        self.expected += other.expected
        self.extracted += other.extracted
        self.matched += other.matched
        self.missed += other.missed
        self.unexpected += other.unexpected
        for k, v in other.field_checks.items():
            self.field_checks.setdefault(k, []).extend(v)


def score_extraction(expected: Iterable[Dict[str, Any]], actual: Iterable[Dict[str, Any]]) -> EvalReport:
    """Greedy one-to-one match of extracted items to labelled items by product name."""
    expected, actual = list(expected), list(actual)
    report = EvalReport(expected=len(expected), extracted=len(actual))
    unused = list(range(len(actual)))
    for exp in expected:
        hit = next((i for i in unused if names_match(exp.get("product_name"), actual[i].get("product_name"))), None)
        if hit is None:
            report.missed.append(str(exp.get("product_name")))
            continue
        unused.remove(hit)
        report.matched += 1
        got = actual[hit]
        for key in NUMERIC_FIELDS:
            if exp.get(key) is not None:
                report.field_checks.setdefault(key, []).append(_close(exp[key], got.get(key)))
        if exp.get("promotion_type"):
            report.field_checks.setdefault("promotion_type", []).append(exp["promotion_type"] == got.get("promotion_type"))
    report.unexpected = [str(actual[i].get("product_name")) for i in unused]
    return report
