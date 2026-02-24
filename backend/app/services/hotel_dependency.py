from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "hotel_allocation_biased"
    / "hotel_allocation_biased"
)

LAT_CANDIDATES = ("latitude", "lat", "緯度")
LON_CANDIDATES = ("longitude", "lon", "経度")

MARKET_COLUMNS: dict[str, str] = {
    "china": "中国",
    "north_america": "北米小計",
    "korea": "韓国",
    "europe": "ヨーロッパ小計",
    "southeast_asia": "東南アジア小計",
    "japan": "国内合計",
}

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
class HotelRow:
    lat: float
    lng: float
    address: str
    ward: str
    overseas_total: float
    domestic_total: float
    markets: dict[str, float]


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


def _find_col(candidates: tuple[str, ...], fieldnames: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    return None


def _read_dict_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            with path.open("r", encoding=encoding, newline="") as fp:
                reader = csv.DictReader(fp)
                rows = list(reader)
                return list(reader.fieldnames or []), rows
        except Exception as error:  # pragma: no cover - fallback path
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(path)


def _pick_file(month: int, year: int | None) -> tuple[Path, int]:
    candidates: list[tuple[int, Path]] = []
    for file_path in DATA_DIR.glob(f"KCTA_*_{month:02d}_hotel_allocation.csv"):
        match = FILE_RE.search(file_path.name)
        if not match:
            continue
        file_year = int(match.group("year"))
        candidates.append((file_year, file_path))

    if not candidates:
        raise FileNotFoundError(f"No monthly file found for month={month} in {DATA_DIR}")

    candidates.sort(key=lambda item: item[0])
    if year is None:
        selected_year, selected_file = candidates[-1]
        return selected_file, selected_year

    for file_year, file_path in candidates:
        if file_year == year:
            return file_path, file_year

    raise FileNotFoundError(f"No monthly file found for year={year}, month={month}")


@lru_cache(maxsize=32)
def load_rows(month: int, year: int | None = None) -> tuple[int, list[HotelRow]]:
    csv_path, selected_year = _pick_file(month=month, year=year)
    fieldnames, raw_rows = _read_dict_rows(csv_path)

    lat_col = _find_col(LAT_CANDIDATES, fieldnames)
    lon_col = _find_col(LON_CANDIDATES, fieldnames)
    if lat_col is None or lon_col is None:
        raise ValueError(f"latitude/longitude columns are missing in {csv_path.name}")

    parsed: list[HotelRow] = []
    for row in raw_rows:
        lat = _to_float(row.get(lat_col))
        lng = _to_float(row.get(lon_col))
        if lat == 0.0 and lng == 0.0:
            continue

        markets: dict[str, float] = {
            market: _to_float(row.get(column_name))
            for market, column_name in MARKET_COLUMNS.items()
        }

        parsed.append(
            HotelRow(
                lat=lat,
                lng=lng,
                address=(row.get("address") or "").strip(),
                ward=(row.get("ward") or "").strip(),
                overseas_total=_to_float(row.get("海外合計")),
                domestic_total=_to_float(row.get("国内合計")),
                markets=markets,
            )
        )

    return selected_year, parsed


def _filter_prefecture(rows: list[HotelRow], prefecture: str) -> list[HotelRow]:
    keywords = PREFECTURE_KEYWORDS.get(prefecture)
    if not keywords:
        return rows

    filtered = [
        row for row in rows if any(keyword in (row.address + row.ward) for keyword in keywords)
    ]
    return filtered


def build_dependency_points(
    prefecture: str,
    month: int,
    year: int | None = None,
    max_points: int = 2500,
) -> tuple[int, list[dict[str, float | str]]]:
    selected_year, rows = load_rows(month=month, year=year)
    target_rows = _filter_prefecture(rows, prefecture=prefecture)

    points: list[dict[str, float | str]] = []
    for row in target_rows:
        denom_foreign = row.overseas_total
        denom_all = row.overseas_total + row.domestic_total

        for market in MARKET_COLUMNS:
            value = row.markets.get(market, 0.0)
            if value <= 0:
                continue

            denominator = denom_all if market == "japan" else denom_foreign
            if denominator <= 0:
                continue

            score = value / denominator
            if score <= 0:
                continue

            points.append(
                {
                    "lat": row.lat,
                    "lng": row.lng,
                    "dependency_score": min(1.0, max(0.0, score)),
                    "market": market,
                }
            )

    if len(points) > max_points:
        points.sort(key=lambda item: float(item["dependency_score"]), reverse=True)
        points = points[:max_points]

    return selected_year, points
