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

  const heatData = useMemo(
    () => points.map((point) => [point.lat, point.lng, Math.max(0.05, point.dependency_score)] as [number, number, number]),
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
          radius: 15,
          blur: 20,
          maxZoom: 13,
          minOpacity: 0.25,
          gradient: {
            0.2: "#2C7BB6",
            0.4: "#00A6CA",
            0.6: "#F9D057",
            0.8: "#F29E2E",
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
