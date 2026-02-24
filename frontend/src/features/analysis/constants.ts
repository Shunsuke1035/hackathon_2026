import { PrefectureOption } from "@/features/analysis/types";

export const PREFECTURES: PrefectureOption[] = [
  { code: "kyoto", name: "京都", center: { lat: 35.0116, lng: 135.7681 }, zoom: 11 },
  { code: "tokyo", name: "東京", center: { lat: 35.6762, lng: 139.6503 }, zoom: 10 },
  { code: "hokkaido", name: "北海道", center: { lat: 43.0642, lng: 141.3469 }, zoom: 9 },
  { code: "fukuoka", name: "福岡", center: { lat: 33.5902, lng: 130.4017 }, zoom: 10 },
  { code: "okinawa", name: "沖縄", center: { lat: 26.2124, lng: 127.6809 }, zoom: 10 },
  { code: "osaka", name: "大阪", center: { lat: 34.6937, lng: 135.5023 }, zoom: 11 }
];

export const MONTH_OPTIONS = Array.from({ length: 12 }, (_, idx) => ({
  value: idx + 1,
  label: `${idx + 1}月`
}));
