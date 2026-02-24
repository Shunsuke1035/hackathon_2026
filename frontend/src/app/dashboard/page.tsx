"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import ResultsPanel from "@/components/ResultsPanel";
import { fetchDependencyPoints, fetchRecommendations, fetchSimulation } from "@/features/analysis/api";
import { MONTH_OPTIONS, PREFECTURES } from "@/features/analysis/constants";
import { FacilityInput, HeatPoint, RecommendationItem, SimulationScenario } from "@/features/analysis/types";
import { API_BASE_URL } from "@/lib/api";

const DependencyMap = dynamic(() => import("@/components/DependencyMap"), { ssr: false });

type MeResponse = {
  id: number;
  username: string;
  email: string;
};

export default function DashboardPage() {
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState("Loading account...");
  const [isError, setIsError] = useState(false);
  const [loadingMap, setLoadingMap] = useState(false);
  const [loadingInsights, setLoadingInsights] = useState(false);

  const [selectedPrefecture, setSelectedPrefecture] = useState("kyoto");
  const [selectedMonth, setSelectedMonth] = useState(1);

  const selectedPrefectureData = useMemo(
    () => PREFECTURES.find((prefecture) => prefecture.code === selectedPrefecture) ?? PREFECTURES[0],
    [selectedPrefecture]
  );

  const [facilityInput, setFacilityInput] = useState<FacilityInput>({
    lat: selectedPrefectureData.center.lat,
    lng: selectedPrefectureData.center.lng,
    address: ""
  });
  const [heatPoints, setHeatPoints] = useState<HeatPoint[]>([]);
  const [simulations, setSimulations] = useState<SimulationScenario[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);

  useEffect(() => {
    const token = window.localStorage.getItem("access_token");
    if (!token) {
      setIsError(true);
      setStatusMessage("Not logged in. Please login first.");
      return;
    }

    const fetchCurrentUser = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        if (!response.ok) throw new Error("Authentication failed.");
        const data = (await response.json()) as MeResponse;
        setCurrentUser(data);
        setStatusMessage("Ready. Select region and month.");
        setIsError(false);
      } catch (error) {
        setIsError(true);
        setStatusMessage(error instanceof Error ? error.message : "Unknown error");
      }
    };
    fetchCurrentUser();
  }, []);

  useEffect(() => {
    setFacilityInput((previous) => ({
      ...previous,
      lat: selectedPrefectureData.center.lat,
      lng: selectedPrefectureData.center.lng
    }));
  }, [selectedPrefectureData.center.lat, selectedPrefectureData.center.lng]);

  useEffect(() => {
    const token = window.localStorage.getItem("access_token");
    if (!token) return;

    const loadDependencyMap = async () => {
      setLoadingMap(true);
      setIsError(false);
      try {
        const points = await fetchDependencyPoints(selectedPrefecture, selectedMonth, token);
        setHeatPoints(points);
      } catch (error) {
        setIsError(true);
        setStatusMessage(error instanceof Error ? error.message : "Failed to load map.");
      } finally {
        setLoadingMap(false);
      }
    };
    loadDependencyMap();
  }, [selectedPrefecture, selectedMonth]);

  const handleFacilityApply = () => {
    if (Number.isNaN(facilityInput.lat) || Number.isNaN(facilityInput.lng)) {
      setIsError(true);
      setStatusMessage("Latitude and longitude must be numbers.");
      return;
    }
    setIsError(false);
    setStatusMessage("Facility location updated.");
  };

  const handleAddressAssist = () => {
    const addressText = facilityInput.address ?? "";
    const hash = Array.from(addressText).reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const latOffset = ((hash % 13) - 6) * 0.003;
    const lngOffset = ((hash % 17) - 8) * 0.003;
    setFacilityInput((previous) => ({
      ...previous,
      lat: Number((selectedPrefectureData.center.lat + latOffset).toFixed(6)),
      lng: Number((selectedPrefectureData.center.lng + lngOffset).toFixed(6))
    }));
    setIsError(false);
    setStatusMessage("Address-based assist applied (MVP approximation).");
  };

  const handleLoadInsights = async () => {
    const token = window.localStorage.getItem("access_token");
    if (!token) {
      setIsError(true);
      setStatusMessage("Login token is missing.");
      return;
    }
    setLoadingInsights(true);
    setIsError(false);
    try {
      const [simData, recommendationData] = await Promise.all([
        fetchSimulation(selectedPrefecture, selectedMonth, facilityInput, token),
        fetchRecommendations(selectedPrefecture, selectedMonth, facilityInput, token)
      ]);
      setSimulations(simData);
      setRecommendations(recommendationData);
      setStatusMessage("Simulation and recommendations loaded.");
    } catch (error) {
      setIsError(true);
      setStatusMessage(error instanceof Error ? error.message : "Failed to load insights.");
    } finally {
      setLoadingInsights(false);
    }
  };

  return (
    <main className="container wide">
      <h1 className="title">Tourism Dependency Dashboard</h1>
      <p className={`message ${isError ? "error" : "ok"}`}>{statusMessage}</p>

      {currentUser ? (
        <div className="panel">
          <div className="panel-title">User</div>
          <div className="meta-row">
            <span>ID: {currentUser.id}</span>
            <span>User: {currentUser.username}</span>
            <span>Email: {currentUser.email}</span>
          </div>
        </div>
      ) : null}

      <section className="panel">
        <h2 className="panel-title">Controls</h2>
        <div className="controls-grid">
          <label>
            Prefecture
            <select
              className="input"
              value={selectedPrefecture}
              onChange={(event) => setSelectedPrefecture(event.target.value)}
            >
              {PREFECTURES.map((prefecture) => (
                <option key={prefecture.code} value={prefecture.code}>
                  {prefecture.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Month
            <select
              className="input"
              value={selectedMonth}
              onChange={(event) => setSelectedMonth(Number(event.target.value))}
            >
              {MONTH_OPTIONS.map((month) => (
                <option key={month.value} value={month.value}>
                  {month.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="panel">
        <h2 className="panel-title">Facility Input</h2>
        <div className="controls-grid">
          <label>
            Latitude
            <input
              className="input"
              type="number"
              step="0.000001"
              value={facilityInput.lat}
              onChange={(event) =>
                setFacilityInput((previous) => ({ ...previous, lat: Number(event.target.value) }))
              }
            />
          </label>
          <label>
            Longitude
            <input
              className="input"
              type="number"
              step="0.000001"
              value={facilityInput.lng}
              onChange={(event) =>
                setFacilityInput((previous) => ({ ...previous, lng: Number(event.target.value) }))
              }
            />
          </label>
          <label className="full-width">
            Address (optional)
            <input
              className="input"
              value={facilityInput.address ?? ""}
              placeholder="e.g. Kyoto Station area"
              onChange={(event) =>
                setFacilityInput((previous) => ({ ...previous, address: event.target.value }))
              }
            />
          </label>
        </div>
        <div className="button-row">
          <button className="button secondary" onClick={handleAddressAssist} type="button">
            Apply Address Assist
          </button>
          <button className="button" onClick={handleFacilityApply} type="button">
            Update Facility Pin
          </button>
          <button className="button" disabled={loadingInsights} onClick={handleLoadInsights} type="button">
            {loadingInsights ? "Loading..." : "Load Suggestions & Simulation"}
          </button>
        </div>
      </section>

      <section>
        <h2 className="panel-title">Dependency Heatmap</h2>
        {loadingMap ? (
          <div className="panel">
            <p className="muted">Loading map data...</p>
          </div>
        ) : (
          <DependencyMap
            center={selectedPrefectureData.center}
            facility={{ lat: facilityInput.lat, lng: facilityInput.lng }}
            points={heatPoints}
            zoom={selectedPrefectureData.zoom}
          />
        )}
      </section>

      <ResultsPanel recommendations={recommendations} simulations={simulations} />

      <p>
        <Link href="/login">Back to login</Link>
      </p>
    </main>
  );
}
