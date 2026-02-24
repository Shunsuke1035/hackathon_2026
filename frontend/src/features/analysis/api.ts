import { API_BASE_URL } from "@/lib/api";
import {
  DependencyMarketKey,
  DependencyMetricsResponse,
  FacilityInput,
  ForecastResponse,
  HeatPoint,
  RecommendationItem,
  SimulationScenario
} from "@/features/analysis/types";

export type DependencyResult = {
  prefecture: string;
  month: number;
  year: number;
  note?: string | null;
  points: HeatPoint[];
};

type SimulationResponse = {
  prefecture: string;
  month: number;
  scenarios: SimulationScenario[];
};

type RecommendationResponse = {
  prefecture: string;
  month: number;
  recommendations: RecommendationItem[];
};

type ForecastRequest = {
  prefecture: string;
  market: DependencyMarketKey;
  month: number;
  horizon_months: number;
  scenario_ids?: string[];
  custom_shock_rate?: number;
  year?: number;
};

export async function fetchDependencyPoints(
  prefecture: string,
  month: number,
  token: string,
  market: DependencyMarketKey | "all" = "all",
  year?: number
): Promise<DependencyResult> {
  const params = new URLSearchParams({ prefecture, month: String(month), market });
  if (year) {
    params.set("year", String(year));
  }

  const response = await fetch(`${API_BASE_URL}/api/analysis/dependency?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!response.ok) {
    throw new Error("依存度ヒートマップデータの取得に失敗しました");
  }
  return (await response.json()) as DependencyResult;
}

export async function fetchDependencyMetrics(
  prefecture: string,
  month: number,
  market: DependencyMarketKey,
  token: string,
  year?: number
): Promise<DependencyMetricsResponse> {
  const params = new URLSearchParams({ prefecture, month: String(month), market });
  if (year) {
    params.set("year", String(year));
  }

  const response = await fetch(`${API_BASE_URL}/api/analysis/dependency-metrics?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!response.ok) {
    throw new Error("依存度メトリクスの取得に失敗しました");
  }
  return (await response.json()) as DependencyMetricsResponse;
}

export async function fetchSimulation(
  prefecture: string,
  month: number,
  facility: FacilityInput,
  token: string
): Promise<SimulationScenario[]> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/simulation`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ prefecture, month, facility })
  });
  if (!response.ok) {
    throw new Error("シミュレーション結果の取得に失敗しました");
  }
  const payload = (await response.json()) as SimulationResponse;
  return payload.scenarios;
}

export async function fetchRecommendations(
  prefecture: string,
  month: number,
  facility: FacilityInput,
  token: string
): Promise<RecommendationItem[]> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/recommendation`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify({ prefecture, month, facility })
  });
  if (!response.ok) {
    throw new Error("提案データの取得に失敗しました");
  }
  const payload = (await response.json()) as RecommendationResponse;
  return payload.recommendations;
}

export async function fetchForecast(
  request: ForecastRequest,
  token: string
): Promise<ForecastResponse> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/forecast`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`
    },
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    throw new Error("予測データの取得に失敗しました");
  }
  return (await response.json()) as ForecastResponse;
}
