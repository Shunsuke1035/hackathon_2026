from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MART_PATH_DEFAULT = PROJECT_ROOT / "data" / "mart" / "mart_country_profile_for_llm.jsonl"

MARKET_TO_PROFILE_KEY = {
    "china": "china",
    "korea": "korea",
    "north_america": "north_america",
    "southeast_asia": "southeast_asia",
    "europe": "europe",
    "japan": "japan",
}

ALLOWED_TYPES = {"risk_leverage", "risk_diversification"}
METRIC_HINT_KEYWORDS = ("hhi", "エントロピー", "top1", "top10", "シェア", "集中")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?\s*%?")


class LLMRecommendationError(RuntimeError):
    pass


class RecommendationOutputItem(BaseModel):
    type: Literal["risk_leverage", "risk_diversification"]
    title: str = Field(min_length=1, max_length=25)
    description: str = Field(min_length=20, max_length=320)
    evidence_scenario_id: str | None = Field(default=None, max_length=64)
    evidence_metric_key: str | None = Field(default=None, max_length=64)


class RecommendationOutputEnvelope(BaseModel):
    recommendations: list[RecommendationOutputItem] = Field(min_length=2, max_length=3)


def _extract_json_object(text: str) -> str | None:
    value = text.strip()
    if not value:
        return None

    fenced = re.search(r"```json\s*(\{.*?\})\s*```", value, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1)

    start = value.find("{")
    end = value.rfind("}")
    if start != -1 and end != -1 and end > start:
        return value[start : end + 1]
    return None


def _is_likely_mojibake(text: str) -> bool:
    if not text:
        return False
    markers = ("縺", "繧", "譛", "鬆", "蜀", "�")
    score = sum(text.count(marker) for marker in markers)
    return score >= 2


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round3(value: Any) -> float:
    return round(_to_float(value), 3)


def _first_number_list(values: list[Any], limit: int = 3) -> list[float]:
    out: list[float] = []
    for item in values:
        if len(out) >= limit:
            break
        out.append(_round3(item))
    return out


def _build_forecast_excerpt(forecast_payload: dict[str, Any]) -> dict[str, Any]:
    scenario_rows: list[dict[str, Any]] = []
    for scenario in forecast_payload.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        points = scenario.get("points", [])
        growth_rates = [
            _to_float(point.get("predicted_growth_rate"), 0.0)
            for point in points
            if isinstance(point, dict)
        ]
        avg_pct = round(sum(growth_rates) / len(growth_rates) * 100.0, 3) if growth_rates else 0.0
        scenario_rows.append(
            {
                "scenario_id": str(scenario.get("scenario_id", "")).strip(),
                "scenario_name_ja": str(scenario.get("scenario_name_ja", "")).strip(),
                "avg_growth_rate_pct": avg_pct,
                "note": str(scenario.get("note", "")).strip(),
            }
        )

    best = max(scenario_rows, key=lambda row: row["avg_growth_rate_pct"], default=None)
    worst = min(scenario_rows, key=lambda row: row["avg_growth_rate_pct"], default=None)

    return {
        "model_version": str(forecast_payload.get("model_version", "")),
        "baseline_growth_rate_pct": _round3(_to_float(forecast_payload.get("baseline_growth_rate"), 0.0) * 100.0),
        "scenario_count": len(scenario_rows),
        "best_scenario": best,
        "worst_scenario": worst,
        "scenarios": scenario_rows[:6],
    }


def _build_metrics_excerpt(metrics_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metrics_payload, dict):
        return {}

    current = metrics_payload.get("current", {})
    if not isinstance(current, dict):
        current = {}

    current_excerpt = {
        "market_total": _round3(current.get("market_total")),
        "facility_hhi_norm_active": _round3(current.get("facility_hhi_norm_active")),
        "facility_entropy_norm_active": _round3(current.get("facility_entropy_norm_active")),
        "facility_top1_share": _round3(current.get("facility_top1_share")),
        "facility_top10_share": _round3(current.get("facility_top10_share")),
        "all_hhi": _round3(current.get("all_hhi")),
        "all_entropy_norm": _round3(current.get("all_entropy_norm")),
    }

    series = metrics_payload.get("series", [])
    recent_series = series[-3:] if isinstance(series, list) else []
    recent_market_total = [
        _to_float(item.get("market_total"), 0.0) for item in recent_series if isinstance(item, dict)
    ]

    growth_1m_pct = None
    if len(recent_market_total) >= 2 and recent_market_total[-2] > 0:
        growth_1m_pct = round((recent_market_total[-1] / recent_market_total[-2] - 1.0) * 100.0, 3)

    return {
        "current": current_excerpt,
        "recent_market_total": _first_number_list(recent_market_total, limit=3),
        "recent_market_total_1m_growth_pct": growth_1m_pct,
    }


@lru_cache(maxsize=1)
def load_country_profile_map() -> dict[str, dict[str, Any]]:
    path = MART_PATH_DEFAULT
    if not path.exists():
        return {}

    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            key = str(item.get("country_profile_key", "")).strip()
            if key:
                rows[key] = item
    return rows


def _build_profile_excerpt(profile_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(profile_payload, dict):
        return {"available": False}

    summary_ja = str(profile_payload.get("summary_ja", "")).strip()
    if _is_likely_mojibake(summary_ja):
        summary_ja = ""

    evidence = profile_payload.get("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}

    top_spending_raw = evidence.get("top_spending_categories", [])
    stay_raw = evidence.get("stay_distribution", [])
    top_spending = top_spending_raw if isinstance(top_spending_raw, list) else []
    stay_distribution = stay_raw if isinstance(stay_raw, list) else []

    purchase_rate_values: list[float] = []
    for row in top_spending:
        if not isinstance(row, dict):
            continue
        if str(row.get("metric_name", "")).strip() != "purchase_rate_pct":
            continue
        purchase_rate_values.append(_to_float(row.get("metric_value"), 0.0))

    traveler_counts = [
        _to_float(row.get("traveler_count"), 0.0) for row in stay_distribution if isinstance(row, dict)
    ]
    unit_spends = [
        _to_float(row.get("unit_spend_jpy"), 0.0) for row in stay_distribution if isinstance(row, dict)
    ]

    return {
        "available": True,
        "profile_version": str(profile_payload.get("profile_version", "")),
        "summary_ja": summary_ja,
        "top_purchase_rate_pct": _first_number_list(sorted(purchase_rate_values, reverse=True), limit=3),
        "top_traveler_count": _first_number_list(sorted(traveler_counts, reverse=True), limit=3),
        "top_unit_spend_jpy": _first_number_list(sorted(unit_spends, reverse=True), limit=3),
    }


def _build_prompt(
    *,
    prefecture: str,
    month: int,
    market: str,
    forecast_payload: dict[str, Any],
    metrics_payload: dict[str, Any] | None,
    profile_payload: dict[str, Any] | None,
) -> str:
    context = {
        "prefecture": prefecture,
        "month": month,
        "market": market,
        "forecast": _build_forecast_excerpt(forecast_payload),
        "dependency_metrics": _build_metrics_excerpt(metrics_payload),
        "country_profile": _build_profile_excerpt(profile_payload),
    }

    return (
        "あなたは宿泊施設向けの観光リスク戦略アドバイザーです。"
        "入力データのみを根拠に、実務で使える提案を作成してください。"
        "出力は必ずJSONオブジェクトのみで返してください。余計な文章は禁止です。\n\n"
        "出力仕様:\n"
        "{\n"
        '  "recommendations": [\n'
        '    {\n'
        '      "type":"risk_leverage|risk_diversification",\n'
        '      "title":"... (25文字以内)",\n'
        '      "description":"... (80〜160文字)",\n'
        '      "evidence_scenario_id":"...",\n'
        '      "evidence_metric_key":"..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "制約:\n"
        "- 件数は2〜3件\n"
        "- risk_leverageを最低1件、risk_diversificationを最低1件\n"
        "- 同一 evidence_scenario_id を複数提案で使わない\n"
        "- risk_diversification の少なくとも1件に HHI/エントロピー/top1_share のいずれかを数値付きで明記\n"
        "- 数値がある場合は必ず文中に具体値を入れる\n\n"
        f"入力コンテキスト:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def _call_gemini(prompt: str) -> str:
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        raise LLMRecommendationError("GEMINI_API_KEY is not configured")

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as error:
        raise LLMRecommendationError(
            "google-genai is not installed. Run: pip install google-genai"
        ) from error

    model = settings.gemini_model.strip() or "gemini-2.5-flash"
    client = genai.Client(api_key=api_key)

    config_kwargs: dict[str, Any] = {
        "temperature": 0.2,
        "max_output_tokens": 1200,
        "response_mime_type": "application/json",
        "response_schema": RecommendationOutputEnvelope,
    }
    if hasattr(genai_types, "ThinkingConfig"):
        config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)
    config = genai_types.GenerateContentConfig(**config_kwargs)

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
    except Exception as error:
        raise LLMRecommendationError(f"Gemini request failed: {error}") from error

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, RecommendationOutputEnvelope):
            return parsed.model_dump_json()
        if isinstance(parsed, BaseModel):
            return parsed.model_dump_json()
        if isinstance(parsed, dict):
            return json.dumps(parsed, ensure_ascii=False)
        if isinstance(parsed, list):
            return json.dumps({"recommendations": parsed}, ensure_ascii=False)

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(response, "candidates", None)
    if not candidates:
        raise LLMRecommendationError("Gemini response does not contain text candidates")
    try:
        parts = candidates[0].content.parts
        joined = "\n".join(str(part.text) for part in parts if getattr(part, "text", None))
    except Exception as error:
        raise LLMRecommendationError("Gemini response format is invalid") from error
    if not joined.strip():
        raise LLMRecommendationError("Gemini response text is empty")
    return joined


def _metric_sentence(metrics_payload: dict[str, Any] | None) -> str:
    if not isinstance(metrics_payload, dict):
        return "依存度指標を継続監視し、集中リスクに応じて販路配分を調整してください。"

    current = metrics_payload.get("current", {})
    if not isinstance(current, dict):
        current = {}

    hhi = current.get("facility_hhi_norm_active")
    ent = current.get("facility_entropy_norm_active")
    top1 = current.get("facility_top1_share")

    parts: list[str] = []
    if hhi is not None:
        parts.append(f"HHI正規化={_to_float(hhi):.3f}")
    if ent is not None:
        parts.append(f"エントロピー正規化={_to_float(ent):.3f}")
    if top1 is not None:
        top1_value = _to_float(top1)
        if 0.0 <= top1_value <= 1.0:
            parts.append(f"Top1シェア={top1_value * 100:.1f}%")
        else:
            parts.append(f"Top1シェア={top1_value:.3f}")
    if not parts:
        return "依存度指標を継続監視し、集中リスクに応じて販路配分を調整してください。"
    return "依存度指標では" + "、".join(parts) + "です。"


def _scenario_candidates(forecast_payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for scenario in forecast_payload.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        points = scenario.get("points", [])
        values = [
            _to_float(point.get("predicted_growth_rate"), 0.0)
            for point in points
            if isinstance(point, dict)
        ]
        avg_pct = (sum(values) / len(values) * 100.0) if values else 0.0
        candidates.append(
            {
                "scenario_id": str(scenario.get("scenario_id", "")).strip(),
                "scenario_name_ja": str(scenario.get("scenario_name_ja", "")).strip() or "シナリオ",
                "avg_growth_rate_pct": round(avg_pct, 3),
            }
        )
    return candidates


def _infer_scenario_id(description: str, forecast_payload: dict[str, Any]) -> str | None:
    text = description.lower()
    for row in _scenario_candidates(forecast_payload):
        scenario_id = row["scenario_id"]
        scenario_name = str(row.get("scenario_name_ja", ""))
        if scenario_id and scenario_id.lower() in text:
            return scenario_id
        if scenario_name and scenario_name in description:
            return scenario_id or scenario_name
    return None


def _contains_metric_hint(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in METRIC_HINT_KEYWORDS) and bool(NUMBER_RE.search(text))


def _synthesize_item(
    *,
    item_type: Literal["risk_leverage", "risk_diversification"],
    forecast_payload: dict[str, Any],
    metrics_payload: dict[str, Any] | None,
    used_scenarios: set[str],
) -> dict[str, str]:
    scenarios = _scenario_candidates(forecast_payload)
    metric_sentence = _metric_sentence(metrics_payload)

    if item_type == "risk_leverage":
        target = min(scenarios, key=lambda row: row["avg_growth_rate_pct"], default=None)
        if target and target.get("scenario_id") not in used_scenarios:
            scenario_id = str(target["scenario_id"])
            scenario_name = str(target["scenario_name_ja"])
            avg_pct = _to_float(target["avg_growth_rate_pct"])
            description = (
                f"{scenario_name}シナリオの平均成長率は{avg_pct:.3f}%です。"
                "主力市場向けの価格・在庫・キャンセル条件を機動調整し、下振れ局面でも収益と稼働を維持してください。"
            )
            return {"type": "risk_leverage", "title": "主力市場の防衛運用", "description": description}

        description = "主力市場向けに価格帯と販売チャネルを最適化し、繁忙期単価と閑散期稼働の両立を図ってください。"
        return {"type": "risk_leverage", "title": "主力市場の収益最適化", "description": description}

    description = (
        metric_sentence
        + "特定市場への依存を下げるため、異なる訪問目的を持つ市場向けに広告配分と商品構成を段階的に再配分してください。"
    )
    return {"type": "risk_diversification", "title": "依存分散ポートフォリオ", "description": description}


def _normalize_items(
    *,
    raw_items: list[Any],
    forecast_payload: dict[str, Any],
    metrics_payload: dict[str, Any] | None,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    used_titles: set[str] = set()
    used_scenarios: set[str] = set()
    metric_sentence = _metric_sentence(metrics_payload)

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", "")).strip()
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        scenario_id = str(item.get("evidence_scenario_id", "")).strip()

        if item_type not in ALLOWED_TYPES or not title or not description:
            continue
        if title in used_titles:
            continue

        inferred = _infer_scenario_id(description, forecast_payload)
        if not scenario_id and inferred:
            scenario_id = inferred
        if scenario_id and scenario_id in used_scenarios:
            continue

        if item_type == "risk_diversification" and not _contains_metric_hint(description):
            description = description + " " + metric_sentence

        normalized.append(
            {
                "type": item_type,
                "title": title[:25],
                "description": description,
            }
        )
        used_titles.add(title)
        if scenario_id:
            used_scenarios.add(scenario_id)
        if len(normalized) >= 3:
            break

    types = {item["type"] for item in normalized}
    if "risk_leverage" not in types:
        normalized.append(
            _synthesize_item(
                item_type="risk_leverage",
                forecast_payload=forecast_payload,
                metrics_payload=metrics_payload,
                used_scenarios=used_scenarios,
            )
        )
    types = {item["type"] for item in normalized}
    if "risk_diversification" not in types:
        normalized.append(
            _synthesize_item(
                item_type="risk_diversification",
                forecast_payload=forecast_payload,
                metrics_payload=metrics_payload,
                used_scenarios=used_scenarios,
            )
        )

    normalized = normalized[:3]
    if len(normalized) < 2:
        raise LLMRecommendationError("Gemini output has too few valid recommendations after normalization")

    final_types = {item["type"] for item in normalized}
    if "risk_leverage" not in final_types or "risk_diversification" not in final_types:
        raise LLMRecommendationError("Gemini output does not satisfy required recommendation types")
    return normalized


def generate_recommendations_with_llm(
    *,
    prefecture: str,
    month: int,
    market: str,
    forecast_payload: dict[str, Any],
    metrics_payload: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    profile_key = MARKET_TO_PROFILE_KEY.get(market, "china")
    profile_payload = load_country_profile_map().get(profile_key)

    prompt = _build_prompt(
        prefecture=prefecture,
        month=month,
        market=market,
        forecast_payload=forecast_payload,
        metrics_payload=metrics_payload,
        profile_payload=profile_payload,
    )

    raw_text = _call_gemini(prompt)
    json_text = _extract_json_object(raw_text)
    if not json_text:
        raise LLMRecommendationError("Gemini output does not contain JSON object")

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise LLMRecommendationError("Gemini output JSON parse failed") from error

    raw_items = parsed.get("recommendations")
    if not isinstance(raw_items, list):
        raise LLMRecommendationError("Gemini output does not contain recommendations list")

    return _normalize_items(
        raw_items=raw_items,
        forecast_payload=forecast_payload,
        metrics_payload=metrics_payload,
    )
