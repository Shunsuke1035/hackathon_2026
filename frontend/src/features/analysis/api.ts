import { API_BASE_URL } from "@/lib/api";
import { FacilityInput, HeatPoint, RecommendationItem, SimulationScenario } from "@/features/analysis/types";

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

export async function fetchDependencyPoints(
  prefecture: string,
  month: number,
  token: string,
  year?: number
): Promise<DependencyResult> {
  const params = new URLSearchParams({ prefecture, month: String(month) });
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
