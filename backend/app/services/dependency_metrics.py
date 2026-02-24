from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from math import log
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR_CANDIDATES = (
    PROJECT_ROOT / "data" / "hotel_allocation_biased" / "hotel_allocation_biased",
    PROJECT_ROOT / "data" / "hotel_allocation_biased 1" / "hotel_allocation_biased",
)

MARKET_COLUMNS: dict[str, str] = {
    "china": "中国",
    "korea": "韓国",
    "north_america": "北米小計",
    "southeast_asia": "東南アジア小計",
    "europe": "ヨーロッパ小計",
    "japan": "国内合計",
}
FOREIGN_MARKETS = ("china", "korea", "north_america", "southeast_asia", "europe")

PREFECTURE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "kyoto": ("京都",),
    "tokyo": ("東京",),
    "hokkaido": ("北海道",),
    "fukuoka": ("福岡",),
    "okinawa": ("沖縄",),
    "osaka": ("大阪",),
}

FILE_RE = re.compile(r"KCTA_(?P<year>\d{4})_(?P<month>\d{2})_hotel_allocation\.csv$")


@dataclass(frozen=True)
class MonthKey:
    year: int
    month: int

    @property
    def month_date(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-01"


def _to_float(raw: str | None) -> float:
    if raw is None:
        return 0.0
    text = str(raw).strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _entropy_from_shares(shares: list[float]) -> float:
    return -sum(share * log(share) for share in shares if share > 0)


def _hhi_from_shares(shares: list[float]) -> float:
    return sum(share * share for share in shares)


def _normalize_shares(values: list[float]) -> tuple[list[float], float]:
    total = sum(values)
    if total <= 0:
        return [0.0 for _ in values], 0.0
    return [value / total for value in values], total


def _resolve_data_dir() -> Path:
    env_path = os.getenv("HOTEL_ALLOCATION_DATA_DIR")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists() and candidate.is_dir():
            return candidate

    for candidate in DATA_DIR_CANDIDATES:
        if candidate.exists() and candidate.is_dir():
            return candidate

    options = ", ".join(str(path) for path in DATA_DIR_CANDIDATES)
    raise FileNotFoundError(
        "Hotel allocation data directory was not found. "
        f"Set HOTEL_ALLOCATION_DATA_DIR or place files in one of: {options}"
    )


def _read_dict_rows(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            with path.open("r", encoding=encoding, newline="") as fp:
                return list(csv.DictReader(fp))
        except Exception as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


def _iter_monthly_files() -> list[tuple[MonthKey, Path]]:
    data_dir = _resolve_data_dir()
    files: list[tuple[MonthKey, Path]] = []
    for path in data_dir.glob("KCTA_*_hotel_allocation.csv"):
        match = FILE_RE.search(path.name)
        if not match:
            continue
        files.append(
            (
                MonthKey(year=int(match.group("year")), month=int(match.group("month"))),
                path,
            )
        )
    files.sort(key=lambda item: (item[0].year, item[0].month))
    return files


def _is_in_prefecture(row: dict[str, str], prefecture: str) -> bool:
    keywords = PREFECTURE_KEYWORDS.get(prefecture)
    if not keywords:
        return True
    text = f"{row.get('address', '')}{row.get('ward', '')}"
    return any(keyword in text for keyword in keywords)


def _build_market_snapshot(
    market_values: list[float],
    facility_count_total: int,
) -> dict[str, float | int | None]:
    market_total = float(sum(market_values))
    facility_count_active = int(sum(1 for value in market_values if value > 0))
    if market_total <= 0:
        return {
            "market_total": 0.0,
            "facility_count_total": facility_count_total,
            "facility_count_active": facility_count_active,
            "facility_hhi": None,
            "facility_entropy": None,
            "facility_entropy_norm_active": None,
            "facility_top1_share": None,
        }

    shares, _ = _normalize_shares(market_values)
    facility_hhi = _hhi_from_shares(shares)
    facility_entropy = _entropy_from_shares(shares)
    if facility_count_active > 1:
        entropy_norm_active = facility_entropy / log(facility_count_active)
    else:
        entropy_norm_active = 0.0

    return {
        "market_total": market_total,
        "facility_count_total": facility_count_total,
        "facility_count_active": facility_count_active,
        "facility_hhi": facility_hhi,
        "facility_entropy": facility_entropy,
        "facility_entropy_norm_active": entropy_norm_active,
        "facility_top1_share": max(shares) if shares else None,
    }


@lru_cache(maxsize=8)
def _build_prefecture_monthly(prefecture: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for month_key, path in _iter_monthly_files():
        rows = _read_dict_rows(path)
        filtered = [row for row in rows if _is_in_prefecture(row, prefecture)]
        if not filtered:
            continue

        totals_by_market: dict[str, float] = {
            market: sum(_to_float(row.get(column_name)) for row in filtered)
            for market, column_name in MARKET_COLUMNS.items()
        }
        facility_values_by_market: dict[str, list[float]] = {
            market: [_to_float(row.get(column_name)) for row in filtered]
            for market, column_name in MARKET_COLUMNS.items()
        }

        foreign_values = [totals_by_market[market] for market in FOREIGN_MARKETS]
        foreign_shares, _ = _normalize_shares(foreign_values)
        all_values = foreign_values + [totals_by_market["japan"]]
        all_shares, _ = _normalize_shares(all_values)

        foreign_total = sum(foreign_values)
        all_total = sum(all_values)
        foreign_entropy = _entropy_from_shares(foreign_shares) if foreign_total > 0 else 0.0
        all_entropy = _entropy_from_shares(all_shares) if all_total > 0 else 0.0

        foreign_top_idx = (
            max(range(len(foreign_values)), key=lambda idx: foreign_values[idx])
            if foreign_values
            else 0
        )
        all_market_keys = list(FOREIGN_MARKETS) + ["japan"]
        all_top_idx = max(range(len(all_values)), key=lambda idx: all_values[idx]) if all_values else 0

        market_metrics = {
            market: _build_market_snapshot(
                market_values=values,
                facility_count_total=len(filtered),
            )
            for market, values in facility_values_by_market.items()
        }

        out.append(
            {
                "year": month_key.year,
                "month": month_key.month,
                "month_date": month_key.month_date,
                "foreign_hhi": _hhi_from_shares(foreign_shares) if foreign_total > 0 else None,
                "foreign_entropy": foreign_entropy if foreign_total > 0 else None,
                "foreign_entropy_norm": (
                    foreign_entropy / log(len(FOREIGN_MARKETS))
                    if foreign_total > 0 and len(FOREIGN_MARKETS) > 1
                    else None
                ),
                "foreign_top1_market": FOREIGN_MARKETS[foreign_top_idx],
                "foreign_top1_share": max(foreign_shares) if foreign_total > 0 and foreign_shares else None,
                "all_hhi": _hhi_from_shares(all_shares) if all_total > 0 else None,
                "all_entropy": all_entropy if all_total > 0 else None,
                "all_entropy_norm": (
                    all_entropy / log(len(all_values)) if all_total > 0 and len(all_values) > 1 else None
                ),
                "all_top1_market": all_market_keys[all_top_idx],
                "all_top1_share": max(all_shares) if all_total > 0 and all_shares else None,
                "market_metrics": market_metrics,
            }
        )

    return out


def build_dependency_metrics(
    prefecture: str,
    month: int,
    market: str,
    year: int | None = None,
) -> dict[str, Any]:
    monthly = _build_prefecture_monthly(prefecture)
    if not monthly:
        raise FileNotFoundError(f"No rows matched prefecture={prefecture}")

    selected: dict[str, Any] | None = None
    if year is not None:
        selected = next((row for row in monthly if row["year"] == year and row["month"] == month), None)
    else:
        candidates = [row for row in monthly if row["month"] == month]
        if candidates:
            selected = sorted(candidates, key=lambda row: row["year"])[-1]
    if selected is None:
        selected = monthly[-1]

    series: list[dict[str, Any]] = []
    for row in monthly:
        market_metrics = row["market_metrics"][market]
        series.append(
            {
                "year": row["year"],
                "month": row["month"],
                "month_date": row["month_date"],
                "market_total": market_metrics["market_total"],
                "facility_count_total": market_metrics["facility_count_total"],
                "facility_count_active": market_metrics["facility_count_active"],
                "facility_hhi": market_metrics["facility_hhi"],
                "facility_entropy": market_metrics["facility_entropy"],
                "facility_entropy_norm_active": market_metrics["facility_entropy_norm_active"],
                "facility_top1_share": market_metrics["facility_top1_share"],
                "foreign_hhi": row["foreign_hhi"],
                "foreign_entropy": row["foreign_entropy"],
                "foreign_entropy_norm": row["foreign_entropy_norm"],
                "all_hhi": row["all_hhi"],
                "all_entropy": row["all_entropy"],
                "all_entropy_norm": row["all_entropy_norm"],
            }
        )

    current_market_metrics = selected["market_metrics"][market]
    current = {
        "year": selected["year"],
        "month": selected["month"],
        "month_date": selected["month_date"],
        "selected_market": market,
        "market_total": current_market_metrics["market_total"],
        "facility_count_total": current_market_metrics["facility_count_total"],
        "facility_count_active": current_market_metrics["facility_count_active"],
        "facility_hhi": current_market_metrics["facility_hhi"],
        "facility_entropy": current_market_metrics["facility_entropy"],
        "facility_entropy_norm_active": current_market_metrics["facility_entropy_norm_active"],
        "facility_top1_share": current_market_metrics["facility_top1_share"],
        "foreign_hhi": selected["foreign_hhi"],
        "foreign_entropy": selected["foreign_entropy"],
        "foreign_entropy_norm": selected["foreign_entropy_norm"],
        "foreign_top1_market": selected["foreign_top1_market"],
        "foreign_top1_share": selected["foreign_top1_share"],
        "all_hhi": selected["all_hhi"],
        "all_entropy": selected["all_entropy"],
        "all_entropy_norm": selected["all_entropy_norm"],
        "all_top1_market": selected["all_top1_market"],
        "all_top1_share": selected["all_top1_share"],
    }

    return {
        "current_year": int(current["year"]),
        "current": current,
        "series": series,
    }
