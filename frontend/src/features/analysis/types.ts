export type PrefectureOption = {
  code: string;
  name: string;
  center: { lat: number; lng: number };
  zoom: number;
};

export type HeatPoint = {
  lat: number;
  lng: number;
  dependency_score: number;
  market: string;
};

export type FacilityInput = {
  lat: number;
  lng: number;
  address?: string;
};

export type SimulationScenario = {
  name: string;
  expected_growth_rate: number;
  risk_level: string;
  note: string;
};

export type RecommendationItem = {
  type: string;
  title: string;
  description: string;
};
