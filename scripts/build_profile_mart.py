from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

ENCODINGS = ("utf-8-sig", "cp932", "shift_jis")

COUNTRY_MAP = {
    "韓国": "korea",
    "中国": "china",
    "東南アジア": "southeast_asia",
    "ヨーロッパ": "europe",
    "北米": "north_america",
    "日本": "japan",
}

COUNTRY_LABEL_JA = {
    "korea": "韓国",
    "china": "中国",
    "southeast_asia": "東南アジア",
    "europe": "ヨーロッパ",
    "north_america": "北米",
    "japan": "日本",
}


@dataclass
class PipelinePaths:
    raw_dir: Path
    processed_dir: Path
    mart_dir: Path


def read_csv_auto(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for enc in ENCODINGS:
        try:
            return pd.read_csv(path, header=None, encoding=enc)
        except Exception as exc:  # pragma: no cover
            last_error = exc
    raise RuntimeError(f"failed to read {path}: {last_error}")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    return text.replace("\u3000", " ").strip()


def to_number(value: object) -> float | None:
    text = clean_text(value)
    if not text or text in {"***", "-"}:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def find_row_contains(df: pd.DataFrame, token: str) -> int:
    for i in range(len(df)):
        row = [clean_text(v) for v in df.iloc[i].tolist()]
        if any(token in v for v in row):
            return i
    raise RuntimeError(f"row containing token='{token}' was not found")


def normalize_metric_name(metric: str) -> str:
    if "購入率" in metric:
        return "purchase_rate_pct"
    if "購入者単価" in metric:
        return "spender_unit_price_jpy"
    if "人数" in metric:
        return "traveler_count"
    if "消費単価" in metric:
        return "unit_spend_jpy"
    if "旅行単価" in metric:
        return "travel_unit_price_jpy"
    return metric


def build_dim_country_profile_key() -> pd.DataFrame:
    rows = []
    for key, label in COUNTRY_LABEL_JA.items():
        rows.append(
            {
                "country_profile_key": key,
                "country_label_ja": label,
                "source_group": "japan_special" if key == "japan" else "nationality",
                "is_active": True,
            }
        )
    return pd.DataFrame(rows)


def parse_spending_nationality(path: Path) -> pd.DataFrame:
    df = read_csv_auto(path)
    header_idx = find_row_contains(df, "調査項目")
    country_row = [clean_text(v) for v in df.iloc[header_idx].tolist()]
    metric_row = [clean_text(v) for v in df.iloc[header_idx + 1].tolist()]

    country_cols: list[tuple[int, str, str]] = []
    for col in range(3, len(df.columns)):
        country_ja = country_row[col]
        metric = metric_row[col]
        if not country_ja:
            continue
        key = COUNTRY_MAP.get(country_ja)
        if not key:
            continue
        country_cols.append((col, key, normalize_metric_name(metric or "購入率")))

    major = ""
    middle = ""
    records: list[dict[str, object]] = []
    for i in range(header_idx + 2, len(df)):
        r0 = clean_text(df.iat[i, 0])
        r1 = clean_text(df.iat[i, 1])
        r2 = clean_text(df.iat[i, 2]) if len(df.columns) > 2 else ""

        if r0 and r0 not in {"【A1】", "（単一回答）"}:
            major = r0
        if r1:
            middle = r1
        detail = r2

        item_path = " > ".join([x for x in [major, middle, detail] if x])
        if not item_path:
            continue

        metric_category = middle or major
        for col, country_key, metric_name in country_cols:
            value = to_number(df.iat[i, col])
            if value is None:
                continue
            actual_metric_name = metric_name
            # In this source, some rows contain purchaser unit price values in country columns.
            if metric_name == "purchase_rate_pct" and value > 100:
                actual_metric_name = "spender_unit_price_jpy"
            records.append(
                {
                    "country_profile_key": country_key,
                    "profile_scope": "nationality",
                    "metric_category": metric_category,
                    "metric_subcategory": detail if detail else None,
                    "item_path": item_path,
                    "metric_name": actual_metric_name,
                    "metric_value": value,
                    "unit": "%" if actual_metric_name.endswith("_pct") else "JPY_PER_PERSON",
                    "source_year": 2022,
                    "source_file": path.name,
                }
            )
    return pd.DataFrame(records)


def parse_stay_nationality(path: Path) -> pd.DataFrame:
    df = read_csv_auto(path)
    header_idx = find_row_contains(df, "調査項目")
    country_row = [clean_text(v) for v in df.iloc[header_idx].tolist()]
    metric_row = [clean_text(v) for v in df.iloc[header_idx + 1].tolist()]

    pairs: list[tuple[int, int, str]] = []
    col = 3
    while col + 1 < len(df.columns):
        country_ja = clean_text(country_row[col])
        if not country_ja:
            col += 1
            continue
        key = COUNTRY_MAP.get(country_ja)
        if key:
            pairs.append((col, col + 1, key))
        col += 2

    major = ""
    middle = ""
    records: list[dict[str, object]] = []
    for i in range(header_idx + 2, len(df)):
        r0 = clean_text(df.iat[i, 0])
        r1 = clean_text(df.iat[i, 1])
        r2 = clean_text(df.iat[i, 2]) if len(df.columns) > 2 else ""
        if r0 and r0 not in {"【A1】", "（単一回答）"}:
            major = r0
        if r1:
            middle = r1
        detail = r2
        stay_bin = " > ".join([x for x in [major, middle, detail] if x])
        if not stay_bin:
            continue

        for count_col, spend_col, country_key in pairs:
            traveler_count = to_number(df.iat[i, count_col])
            unit_spend_jpy = to_number(df.iat[i, spend_col])
            if traveler_count is None and unit_spend_jpy is None:
                continue
            records.append(
                {
                    "country_profile_key": country_key,
                    "profile_scope": "nationality",
                    "stay_bin": stay_bin,
                    "traveler_count": traveler_count,
                    "unit_spend_jpy": unit_spend_jpy,
                    "source_year": 2022,
                    "source_file": path.name,
                }
            )
    return pd.DataFrame(records)


def parse_spending_japan(path: Path) -> pd.DataFrame:
    df = read_csv_auto(path)
    data_start = find_row_contains(df, "品目（小分類）") + 1
    records: list[dict[str, object]] = []
    for i in range(data_start, len(df)):
        col0 = clean_text(df.iat[i, 0])
        col1 = clean_text(df.iat[i, 1])
        col2 = clean_text(df.iat[i, 2])
        if not any([col0, col1, col2]):
            continue
        item_path = " > ".join([x for x in [col0, col1, col2] if x])
        if not item_path:
            continue

        metrics = [
            ("travel_unit_price_jpy", df.iat[i, 3], "JPY_PER_PERSON_TRIP"),
            ("purchase_rate_pct", df.iat[i, 4], "%"),
            ("spender_unit_price_jpy", df.iat[i, 5], "JPY_PER_PERSON"),
        ]
        for metric_name, raw_value, unit in metrics:
            value = to_number(raw_value)
            if value is None:
                continue
            records.append(
                {
                    "country_profile_key": "japan",
                    "profile_scope": "japan_special",
                    "metric_category": col1 or col0,
                    "metric_subcategory": col2 if col2 else None,
                    "item_path": item_path,
                    "metric_name": metric_name,
                    "metric_value": value,
                    "unit": unit,
                    "source_year": 2022,
                    "source_file": path.name,
                }
            )
    return pd.DataFrame(records)


def parse_stay_japan(path: Path) -> pd.DataFrame:
    df = read_csv_auto(path)
    data_start = find_row_contains(df, "調査期") + 1
    records: list[dict[str, object]] = []
    for i in range(data_start, len(df)):
        period = clean_text(df.iat[i, 0])
        major = clean_text(df.iat[i, 2])
        detail = clean_text(df.iat[i, 3])
        if not any([period, major, detail]):
            continue
        stay_bin = " > ".join([x for x in [major, detail] if x])
        traveler_count = to_number(df.iat[i, 5])  # 宿泊旅行 > 全目的
        if traveler_count is None:
            continue
        records.append(
            {
                "country_profile_key": "japan",
                "profile_scope": "japan_special",
                "stay_bin": stay_bin,
                "traveler_count": traveler_count,
                "unit_spend_jpy": None,
                "source_year": 2022,
                "source_file": path.name,
            }
        )
    return pd.DataFrame(records)


def build_country_profile_mart(
    spending_df: pd.DataFrame,
    stay_df: pd.DataFrame,
    countries: Iterable[str],
) -> list[dict[str, object]]:
    rows = []
    for country_key in countries:
        s = spending_df[spending_df["country_profile_key"] == country_key].copy()
        t = stay_df[stay_df["country_profile_key"] == country_key].copy()

        top_spending = (
            s[s["metric_name"] == "purchase_rate_pct"]
            .sort_values("metric_value", ascending=False)
            .head(5)
        )
        top_stay = t.sort_values("traveler_count", ascending=False).head(5)

        top_spending_names = [str(v) for v in top_spending["item_path"].tolist()]
        top_stay_bins = [str(v) for v in top_stay["stay_bin"].tolist()]
        summary = (
            f"{COUNTRY_LABEL_JA.get(country_key, country_key)}は、"
            f"消費項目では「{top_spending_names[0] if top_spending_names else 'データ不足'}」の寄与が高く、"
            f"滞在傾向では「{top_stay_bins[0] if top_stay_bins else 'データ不足'}」が上位です。"
        )

        rows.append(
            {
                "country_profile_key": country_key,
                "summary_ja": summary,
                "evidence": {
                    "top_spending_categories": [
                        {
                            "item_path": r["item_path"],
                            "metric_name": r["metric_name"],
                            "metric_value": r["metric_value"],
                            "unit": r["unit"],
                            "source_file": r["source_file"],
                        }
                        for _, r in top_spending.iterrows()
                    ],
                    "stay_distribution": [
                        {
                            "stay_bin": r["stay_bin"],
                            "traveler_count": r["traveler_count"],
                            "unit_spend_jpy": r["unit_spend_jpy"],
                            "source_file": r["source_file"],
                        }
                        for _, r in top_stay.iterrows()
                    ],
                },
                "profile_version": "v1.0.0",
            }
        )
    return rows


def write_df(df: pd.DataFrame, out_base: Path) -> None:
    out_base.parent.mkdir(parents=True, exist_ok=True)
    csv_path = out_base.with_suffix(".csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    try:
        df.to_parquet(out_base.with_suffix(".parquet"), index=False)
    except Exception:
        # CSV is always emitted; parquet is optional depending on environment deps.
        pass


def run(paths: PipelinePaths) -> None:
    paths.processed_dir.mkdir(parents=True, exist_ok=True)
    paths.mart_dir.mkdir(parents=True, exist_ok=True)

    dim_country = build_dim_country_profile_key()
    write_df(dim_country, paths.processed_dir / "dim_country_profile_key")

    spending_nationality = parse_spending_nationality(
        paths.raw_dir / "2022_Tourism_Spending_Trends_by_Nationality.csv"
    )
    spending_japan = parse_spending_japan(
        paths.raw_dir / "2022_Tourism_Spending_Trends_by_Japan.csv"
    )
    fact_spending = pd.concat([spending_nationality, spending_japan], ignore_index=True)
    write_df(fact_spending, paths.processed_dir / "fact_spending_profile")

    stay_nationality = parse_stay_nationality(
        paths.raw_dir / "2022_Tourism_Stay_Trends_by_Nationality.csv"
    )
    stay_japan = parse_stay_japan(paths.raw_dir / "2022_Tourism_Stay_Trends_by_Japan.csv")
    fact_stay = pd.concat([stay_nationality, stay_japan], ignore_index=True)
    write_df(fact_stay, paths.processed_dir / "fact_stay_profile")

    mart_rows = build_country_profile_mart(
        fact_spending,
        fact_stay,
        countries=dim_country["country_profile_key"].tolist(),
    )
    mart_path = paths.mart_dir / "mart_country_profile_for_llm.jsonl"
    with mart_path.open("w", encoding="utf-8") as f:
        for row in mart_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("generated:")
    print(f"- {paths.processed_dir / 'dim_country_profile_key.csv'}")
    print(f"- {paths.processed_dir / 'fact_spending_profile.csv'}")
    print(f"- {paths.processed_dir / 'fact_stay_profile.csv'}")
    print(f"- {mart_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build processed profile tables and LLM mart.")
    parser.add_argument("--raw-dir", default="data", type=Path)
    parser.add_argument("--processed-dir", default="data/processed", type=Path)
    parser.add_argument("--mart-dir", default="data/mart", type=Path)
    args = parser.parse_args()

    run(
        PipelinePaths(
            raw_dir=args.raw_dir,
            processed_dir=args.processed_dir,
            mart_dir=args.mart_dir,
        )
    )


if __name__ == "__main__":
    main()
