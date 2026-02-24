"use client";

import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { Circle, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";

import { HeatPoint } from "@/features/analysis/types";

type Props = {
  center: { lat: number; lng: number };
  zoom: number;
  points: HeatPoint[];
  facility: { lat: number; lng: number };
};

function HeatLayer({ points }: { points: HeatPoint[] }) {
  const map = useMap();
  const layerRef = useRef<L.Layer | null>(null);

  const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));

  const heatData = useMemo(
    () => {
      if (points.length === 0) return [] as [number, number, number][];

      return points
        .map((point) => {
          const dep = clamp01(Math.max(0, point.dependency_score));
          const depBoost = clamp01(Math.pow(dep, 0.92) * 1.05);

          // 固定スケールで件数重みを加える（市場ごとの再正規化はしない）。
          const countRaw = Math.max(0, point.market_count ?? 0);
          const countBoost = clamp01(Math.log1p(countRaw) / Math.log1p(1600));

          const mixed = clamp01(depBoost * 0.85 + countBoost * 0.15);
          const boosted = clamp01(Math.pow(mixed, 1.08) * 1.02);
          return [point.lat, point.lng, boosted] as [number, number, number];
        })
        .filter((item) => item[2] >= 0.08);
    },
    [points]
  );

  useEffect(() => {
    let cancelled = false;

    const renderLayer = async () => {
      await import("leaflet.heat");
      if (cancelled) return;

      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }

      if (heatData.length === 0) return;

      const layer = (L as unknown as { heatLayer: (data: [number, number, number][], options: Record<string, unknown>) => L.Layer }).heatLayer(
        heatData,
        {
          radius: 17,
          blur: 23,
          maxZoom: 13,
          minOpacity: 0.3,
          gradient: {
            0.2: "#2C7BB6",
            0.4: "#00A6CA",
            0.62: "#F9D057",
            0.78: "#F29E2E",
            0.9: "#E76818",
            1.0: "#D7191C"
          }
        }
      );

      layer.addTo(map);
      layerRef.current = layer;
    };

    renderLayer();

    return () => {
      cancelled = true;
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [map, heatData]);

  return null;
}

export default function DependencyMap({ center, zoom, points, facility }: Props) {
  return (
    <div className="map-card">
      <MapContainer center={[center.lat, center.lng]} zoom={zoom} className="map-container">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <HeatLayer points={points} />
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
