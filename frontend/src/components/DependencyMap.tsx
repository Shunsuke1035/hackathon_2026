"use client";

import { Circle, CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

import { HeatPoint } from "@/features/analysis/types";

type Props = {
  center: { lat: number; lng: number };
  zoom: number;
  points: HeatPoint[];
  facility: { lat: number; lng: number };
};

function marketLabel(market: string): string {
  if (market === "china") return "中国";
  if (market === "north_america") return "北米";
  if (market === "korea") return "韓国";
  if (market === "europe") return "ヨーロッパ";
  if (market === "southeast_asia") return "東南アジア";
  if (market === "japan") return "国内";
  return market;
}

function scoreColor(score: number): string {
  if (score >= 0.8) return "#b91c1c";
  if (score >= 0.6) return "#ea580c";
  if (score >= 0.4) return "#ca8a04";
  if (score >= 0.2) return "#65a30d";
  return "#0d9488";
}

export default function DependencyMap({ center, zoom, points, facility }: Props) {
  return (
    <div className="map-card">
      <MapContainer center={[center.lat, center.lng]} zoom={zoom} className="map-container">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {points.map((point, index) => (
          <CircleMarker
            key={`${point.lat}-${point.lng}-${index}`}
            center={[point.lat, point.lng]}
            radius={6 + point.dependency_score * 10}
            pathOptions={{
              color: scoreColor(point.dependency_score),
              fillColor: scoreColor(point.dependency_score),
              fillOpacity: 0.45
            }}
          >
            <Popup>
              市場カテゴリ: {marketLabel(point.market)}
              <br />
              依存度スコア: {point.dependency_score.toFixed(2)}
            </Popup>
          </CircleMarker>
        ))}
        <Circle
          center={[facility.lat, facility.lng]}
          radius={450}
          pathOptions={{ color: "#111827", fillColor: "#f97316", fillOpacity: 0.35, weight: 2.5 }}
        >
          <Popup>自施設位置（強調表示）</Popup>
        </Circle>
      </MapContainer>
    </div>
  );
}
