#!/usr/bin/env python
"""Build dependency metrics from monthly hotel allocation files.

Outputs:
1) facility x month metrics (within-facility composition metrics)
2) region x month metrics (within-region composition metrics)
3) market x month metrics (across-facility distribution metrics)
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_CANDIDATES = (
    PROJECT_ROOT / "data" / "hotel_allocation_biased" / "hotel_allocation_biased",
    PROJECT_ROOT / "data" / "hotel_allocation_biased 1" / "hotel_allocation_biased",
)
FILE_RE = re.compile(r"KCTA_(?P<year>\d{4})_(?P<month>\d{2})_hotel_allocation\.csv$")

# Expected monthly CSV columns after Unnamed column cleanup
# 0: facility_id, 1: facility_name, 2: address, 3: ward, 4: hotel_license_type,
# 5: license_date, 6: latitude, 7: longitude, 8: europe, 9: china, 10: north_america,
# 11: domestic, 12: southeast_asia, 13: overseas, 14: korea
COL_IDX = {
    "facility_id": 0,
    "ward": 3,
    "latitude": 6,
    "longitude": 7,
    "count_europe": 8,
    "count_china": 9,
    "count_north_america": 10,
    "count_domestic": 11,
    "count_southeast_asia": 12,
    "count_overseas": 13,
    "count_korea": 14,
}

FOREIGN_MARKETS = [
    "count_china",
    "count_korea",
    "count_north_america",
    "count_southeast_asia",
    "count_europe",
]
ALL_MARKETS = FOREIGN_MARKETS + ["count_domestic"]

MARKET_LABEL_MAP = {
    "count_china": "china",
    "count_korea": "korea",
    "count_north_america": "north_america",
    "count_southeast_asia": "southeast_asia",
    "count_europe": "europe",
    "count_domestic": "japan",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build dependency metrics (HHI/Entropy/Top1).")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    return parser.parse_args()


def resolve_input_dir(custom: Path | None) -> Path:
    if custom is not None:
        return custom
    for candidate in INPUT_DIR_CANDIDATES:
        if candidate.exists() and candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "No allocation input directory found. Expected one of: "
        + ", ".join(str(path) for path in INPUT_DIR_CANDIDATES)
    )


def read_csv_with_fallback(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def normalize_shares(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    totals = matrix.sum(axis=1)
    shares = np.divide(
        matrix,
        totals[:, None],
        out=np.zeros_like(matrix, dtype=float),
        where=totals[:, None] > 0,
    )
    return shares, totals


def entropy_from_shares(shares: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        log_p = np.where(shares > 0, np.log(shares), 0.0)
    return -(shares * log_p).sum(axis=1)


def build_metric_frame(base: pd.DataFrame, market_cols: list[str], prefix: str) -> pd.DataFrame:
    matrix = base[market_cols].to_numpy(dtype=float)
    shares, totals = normalize_shares(matrix)
    hhi = (shares**2).sum(axis=1)
    entropy = entropy_from_shares(shares)
    entropy_norm = entropy / np.log(len(market_cols)) if len(market_cols) > 1 else np.nan
    top1_idx = shares.argmax(axis=1)
    top1_share = shares.max(axis=1)
    active_count = (matrix > 0).sum(axis=1)

    out = pd.DataFrame(
        {
            f"{prefix}_total": totals,
            f"{prefix}_hhi": hhi,
            f"{prefix}_entropy": entropy,
            f"{prefix}_entropy_norm": entropy_norm,
            f"{prefix}_top1_share": top1_share,
            f"{prefix}_top1_market": [MARKET_LABEL_MAP[market_cols[idx]] for idx in top1_idx],
            f"{prefix}_active_market_count": active_count,
        }
    )
    for idx, market_col in enumerate(market_cols):
        out[f"{prefix}_share_{MARKET_LABEL_MAP[market_col]}"] = shares[:, idx]
    return out


def parse_monthly_file(path: Path) -> pd.DataFrame:
    match = FILE_RE.search(path.name)
    if not match:
        raise ValueError(f"Unexpected file name format: {path.name}")
    year = int(match.group("year"))
    month = int(match.group("month"))

    raw = read_csv_with_fallback(path)
    raw = raw.loc[:, [col for col in raw.columns if not str(col).startswith("Unnamed:")]]

    if len(raw.columns) < 15:
        raise ValueError(f"Expected at least 15 columns in {path.name}, got {len(raw.columns)}")

    frame = pd.DataFrame(
        {
            "facility_id": raw.iloc[:, COL_IDX["facility_id"]].fillna("").astype(str),
            "ward": raw.iloc[:, COL_IDX["ward"]].fillna("").astype(str),
            "latitude": to_num(raw.iloc[:, COL_IDX["latitude"]]),
            "longitude": to_num(raw.iloc[:, COL_IDX["longitude"]]),
            "count_europe": to_num(raw.iloc[:, COL_IDX["count_europe"]]),
            "count_china": to_num(raw.iloc[:, COL_IDX["count_china"]]),
            "count_north_america": to_num(raw.iloc[:, COL_IDX["count_north_america"]]),
            "count_domestic": to_num(raw.iloc[:, COL_IDX["count_domestic"]]),
            "count_southeast_asia": to_num(raw.iloc[:, COL_IDX["count_southeast_asia"]]),
            "count_overseas": to_num(raw.iloc[:, COL_IDX["count_overseas"]]),
            "count_korea": to_num(raw.iloc[:, COL_IDX["count_korea"]]),
        }
    )
    frame["year"] = year
    frame["month"] = month
    frame["month_date"] = pd.Timestamp(year=year, month=month, day=1)

    foreign_metrics = build_metric_frame(frame, FOREIGN_MARKETS, prefix="foreign")
    all_metrics = build_metric_frame(frame, ALL_MARKETS, prefix="all")
    out = pd.concat([frame.reset_index(drop=True), foreign_metrics, all_metrics], axis=1)

    out["known_foreign_to_overseas_ratio"] = np.where(
        out["count_overseas"] > 0,
        out["foreign_total"] / out["count_overseas"],
        np.nan,
    )
    out["data_quality_known_foreign_le_overseas"] = out["foreign_total"] <= out["count_overseas"]
    return out


def build_facility_month_table(files: Iterable[Path]) -> pd.DataFrame:
    parts = [parse_monthly_file(path) for path in sorted(files)]
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def build_region_month_table(facility_month: pd.DataFrame) -> pd.DataFrame:
    group_keys = ["year", "month", "month_date", "ward"]
    sum_cols = FOREIGN_MARKETS + ["count_domestic", "count_overseas"]

    grouped = facility_month.groupby(group_keys, as_index=False)[sum_cols].sum()
    grouped = grouped.rename(columns={"ward": "region_code"})

    foreign_metrics = build_metric_frame(grouped, FOREIGN_MARKETS, prefix="foreign")
    all_metrics = build_metric_frame(grouped, ALL_MARKETS, prefix="all")
    out = pd.concat([grouped.reset_index(drop=True), foreign_metrics, all_metrics], axis=1)

    out["known_foreign_to_overseas_ratio"] = np.where(
        out["count_overseas"] > 0,
        out["foreign_total"] / out["count_overseas"],
        np.nan,
    )
    out["data_quality_known_foreign_le_overseas"] = out["foreign_total"] <= out["count_overseas"]
    return out


def build_market_facility_entropy_table(facility_month: pd.DataFrame) -> pd.DataFrame:
    markets = ALL_MARKETS
    records: list[dict[str, object]] = []

    for (year, month, month_date), chunk in facility_month.groupby(["year", "month", "month_date"], sort=True):
        total_facilities = int(len(chunk))
        for market_col in markets:
            values = chunk[market_col].to_numpy(dtype=float)
            total = float(values.sum())
            active_mask = values > 0
            active_count = int(active_mask.sum())

            if total <= 0:
                records.append(
                    {
                        "year": int(year),
                        "month": int(month),
                        "month_date": month_date,
                        "market": MARKET_LABEL_MAP[market_col],
                        "market_total": 0.0,
                        "facility_count_total": total_facilities,
                        "facility_count_active": active_count,
                        "facility_hhi": np.nan,
                        "facility_entropy": np.nan,
                        "facility_entropy_norm_active": np.nan,
                        "facility_top1_share": np.nan,
                        "facility_top1_id": None,
                    }
                )
                continue

            shares = values / total
            hhi = float((shares**2).sum())
            entropy = float(entropy_from_shares(shares.reshape(1, -1))[0])
            top1_idx = int(shares.argmax())
            top1_share = float(shares[top1_idx])
            top1_id = str(chunk.iloc[top1_idx]["facility_id"])

            if active_count > 1:
                entropy_norm_active = entropy / float(np.log(active_count))
            else:
                entropy_norm_active = 0.0

            records.append(
                {
                    "year": int(year),
                    "month": int(month),
                    "month_date": month_date,
                    "market": MARKET_LABEL_MAP[market_col],
                    "market_total": total,
                    "facility_count_total": total_facilities,
                    "facility_count_active": active_count,
                    "facility_hhi": hhi,
                    "facility_entropy": entropy,
                    "facility_entropy_norm_active": entropy_norm_active,
                    "facility_top1_share": top1_share,
                    "facility_top1_id": top1_id,
                }
            )

    return pd.DataFrame(records)


def write_df(df: pd.DataFrame, out_base: Path) -> None:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_base.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    try:
        df.to_parquet(out_base.with_suffix(".parquet"), index=False)
    except Exception:
        pass


def main() -> None:
    args = parse_args()
    input_dir = resolve_input_dir(args.input_dir)
    files = sorted(input_dir.glob("KCTA_*_hotel_allocation.csv"))
    if not files:
        raise FileNotFoundError(f"No monthly allocation files found in: {input_dir}")

    facility_month = build_facility_month_table(files)
    region_month = build_region_month_table(facility_month)
    market_facility = build_market_facility_entropy_table(facility_month)

    write_df(facility_month, args.output_dir / "fact_dependency_metrics_facility_monthly")
    write_df(region_month, args.output_dir / "fact_dependency_metrics_region_monthly")
    write_df(market_facility, args.output_dir / "fact_dependency_metrics_market_facility_monthly")

    print("generated:")
    print(f"- {args.output_dir / 'fact_dependency_metrics_facility_monthly.csv'}")
    print(f"- {args.output_dir / 'fact_dependency_metrics_region_monthly.csv'}")
    print(f"- {args.output_dir / 'fact_dependency_metrics_market_facility_monthly.csv'}")


if __name__ == "__main__":
    main()
