import { API_BASE_URL } from "@/lib/api";
import { FacilityInput, HeatPoint, RecommendationItem, SimulationScenario } from "@/features/analysis/types";

type DependencyResponse = {
  prefecture: string;
  month: number;
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
  token: string
): Promise<HeatPoint[]> {
  const params = new URLSearchParams({ prefecture, month: String(month) });
  const response = await fetch(`${API_BASE_URL}/api/analysis/dependency?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!response.ok) {
    throw new Error("Failed to load dependency map data");
  }
  const payload = (await response.json()) as DependencyResponse;
  return payload.points;
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
    throw new Error("Failed to load simulation result");
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
    throw new Error("Failed to load recommendations");
  }
  const payload = (await response.json()) as RecommendationResponse;
  return payload.recommendations;
}
