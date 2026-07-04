"use client";
import { BACKEND_URL } from "@/config";

import React, { useState, useEffect } from "react";
import { useStore, Shot, Candidate } from "@/store/useStore";
import { Eye, EyeOff, HelpCircle, AlertTriangle } from "lucide-react";

interface ShotTableProps {
  forceMode?: "shots" | "candidates";
  selectedShooter?: any | null;
}

export default function ShotTable({ forceMode, selectedShooter = null }: ShotTableProps = {}) {
  const { 
    shots, 
    candidates, 
    selectedShotId, 
    setSelectedShotId, 
    setShots, 
    userRole,
    minCaliber,
    maxCaliber,
    minScore,
    minConfidence,
    searchQuery,
    setMinCaliber,
    setMaxCaliber,
    setMinScore,
    setMinConfidence,
    setSearchQuery,
    clearFilters,
    activeSession
  } = useStore();
  const [localSubTab, setLocalSubTab] = useState<"shots" | "candidates">("shots");
  const activeSubTab = forceMode || localSubTab;
  const setActiveSubTab = (tab: "shots" | "candidates") => {
    if (!forceMode) {
      setLocalSubTab(tab);
    }
  };

  useEffect(() => {
    if (userRole === "shooter" || selectedShooter !== null) {
      setLocalSubTab("shots");
    }
  }, [userRole, selectedShooter]);

  const getMockShooterShots = (sessionId: string, caliber: number = 5.56): Shot[] => [
    {
      id: "mock-shot-1",
      session_id: sessionId,
      image_id: null,
      shot_number: 1,
      x_raw: 679.53,
      y_raw: 470.11,
      x_calibrated: 312.58,
      y_calibrated: 535.92,
      x_warped: 679.53,
      y_warped: 470.11,
      diameter_px: 11.34,
      diameter_mm: 9.07,
      confidence: 0.59,
      is_valid: true,
      score: 4,
      decimal_score: 4.0,
      nearest_ring_value: 5,
      distance_to_nearest_ring_mm: 7.4,
      bullseye_id: 1,
      distance_to_center_mm: 7.4,
      boundary_status: "certain",
      localization_error_mm: 0.57,
      created_at: "2026-06-22T09:20:45.743988"
    },
    {
      id: "mock-shot-2",
      session_id: sessionId,
      image_id: null,
      shot_number: 2,
      x_raw: 402.05,
      y_raw: 451.95,
      x_calibrated: 184.94,
      y_calibrated: 515.22,
      x_warped: 402.05,
      y_warped: 451.95,
      diameter_px: 8.63,
      diameter_mm: 6.9,
      confidence: 0.75,
      is_valid: true,
      score: 5,
      decimal_score: 5.0,
      nearest_ring_value: 5,
      distance_to_nearest_ring_mm: -21.02,
      bullseye_id: 1,
      distance_to_center_mm: -21.02,
      boundary_status: "certain",
      localization_error_mm: 0.57,
      created_at: "2026-06-22T09:20:45.744694"
    },
    {
      id: "mock-shot-3",
      session_id: sessionId,
      image_id: null,
      shot_number: 3,
      x_raw: 319.57,
      y_raw: 441.07,
      x_calibrated: 147.0,
      y_calibrated: 502.82,
      x_warped: 319.57,
      y_warped: 441.07,
      diameter_px: 11.28,
      diameter_mm: 9.03,
      confidence: 0.62,
      is_valid: true,
      score: 4,
      decimal_score: 4.0,
      nearest_ring_value: 5,
      distance_to_nearest_ring_mm: 16.92,
      bullseye_id: 1,
      distance_to_center_mm: 16.92,
      boundary_status: "certain",
      localization_error_mm: 0.57,
      created_at: "2026-06-22T09:20:45.758013"
    },
    {
      id: "mock-shot-4",
      session_id: sessionId,
      image_id: null,
      shot_number: 4,
      x_raw: 760.71,
      y_raw: 413.75,
      x_calibrated: 349.93,
      y_calibrated: 471.67,
      x_warped: 760.71,
      y_warped: 413.75,
      diameter_px: 14.3,
      diameter_mm: 11.44,
      confidence: 0.77,
      is_valid: true,
      score: 3,
      decimal_score: 3.0,
      nearest_ring_value: 4,
      distance_to_nearest_ring_mm: 6.75,
      bullseye_id: 2,
      distance_to_center_mm: 6.75,
      boundary_status: "certain",
      localization_error_mm: 0.57,
      created_at: "2026-06-22T09:20:45.763925"
    },
    {
      id: "mock-shot-5",
      session_id: sessionId,
      image_id: null,
      shot_number: 5,
      x_raw: 289.21,
      y_raw: 160.43,
      x_calibrated: 133.04,
      y_calibrated: 182.9,
      x_warped: 289.21,
      y_warped: 160.43,
      diameter_px: 4.58,
      diameter_mm: 3.67,
      confidence: 0.42,
      is_valid: true,
      score: 0,
      decimal_score: 0.0,
      nearest_ring_value: 3,
      distance_to_nearest_ring_mm: 159.42,
      bullseye_id: 3,
      distance_to_center_mm: 159.42,
      boundary_status: "certain",
      localization_error_mm: 0.57,
      created_at: "2026-06-22T09:20:45.773725"
    }
  ];

  const getShooterShots = () => {
    if (!activeSession) return [];
    
    let targetShooter = null;
    if (userRole === "shooter") {
      targetShooter = selectedShooter || "shooter";
    } else if (userRole === "instructor") {
      targetShooter = selectedShooter;
    }
    
    if (userRole === "instructor" && !targetShooter) {
      return [];
    }
    
    const actualShots = (() => {
      if (targetShooter) {
        const shooterId = typeof targetShooter === "object" ? targetShooter.id : "";
        if (shooterId.endsWith("-01") || shooterId.endsWith("-A")) {
          return shots.filter(s => s.shot_number % 3 === 1);
        } else if (shooterId.endsWith("-02") || shooterId.endsWith("-B")) {
          return shots.filter(s => s.shot_number % 3 === 2);
        } else if (shooterId.endsWith("-03") || shooterId.endsWith("-C")) {
          return shots.filter(s => s.shot_number % 3 === 0);
        }
      }
      return shots;
    })();

    if (actualShots.length === 0 && (userRole === "shooter" || selectedShooter !== null)) {
      return getMockShooterShots(activeSession.id, activeSession.bullet_caliber);
    }
    return actualShots;
  };

  const currentShots = getShooterShots();

  const filteredShots = currentShots.filter((shot) => {
    if (searchQuery !== "") {
      const numStr = shot.shot_number.toString();
      const queryClean = searchQuery.trim().toLowerCase().replace("#", "");
      if (!numStr.toLowerCase().includes(queryClean)) return false;
    }

    const caliber = shot.diameter_mm !== null && shot.diameter_mm !== undefined ? shot.diameter_mm : shot.diameter_px;
    if (minCaliber !== "" && caliber < parseFloat(minCaliber)) return false;
    if (maxCaliber !== "" && caliber > parseFloat(maxCaliber)) return false;

    if (minScore !== "") {
      const scoreVal = shot.score !== null && shot.score !== undefined ? shot.score : 0;
      if (scoreVal < parseInt(minScore)) return false;
    }
    return true;
  });

  const filteredCandidates = (candidates || []).filter((candidate, idx) => {
    if (searchQuery !== "") {
      const numStr = (idx + 1).toString();
      const candNumStr = `c${numStr}`;
      const queryClean = searchQuery.trim().toLowerCase().replace("#", "");
      if (!numStr.includes(queryClean) && !candNumStr.includes(queryClean)) return false;
    }

    const caliber = candidate.diameter_px;
    if (minCaliber !== "" && caliber < parseFloat(minCaliber)) return false;
    if (maxCaliber !== "" && caliber > parseFloat(maxCaliber)) return false;

    if (minConfidence !== "") {
      const confPercent = candidate.confidence * 100;
      if (confPercent < parseFloat(minConfidence)) return false;
    }
    return true;
  });

  const handleRowHover = (id: string | null) => {
    setSelectedShotId(id);
  };

  const toggleShotValidity = async (shot: Shot, e: React.MouseEvent) => {
    e.stopPropagation();
    
    const nextValid = !shot.is_valid;
    // Update Zustand store locally to simulate the toggle
    const updatedShots = shots.map((s) => 
      s.id === shot.id ? { ...s, is_valid: nextValid } : s
    );
    setShots(updatedShots);

    try {
      await fetch(`${BACKEND_URL}/api/v1/shots/${shot.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_valid: nextValid })
      });
    } catch (err) {
      console.error("Failed to update shot validity:", err);
    }
  };

  const handleMarkForReview = async (shot: Shot, e: React.MouseEvent) => {
    e.stopPropagation();
    
    const nextStatus = shot.boundary_status === "review_required" ? "certain" : "review_required";
    const updatedShots = shots.map((s) => 
      s.id === shot.id ? { ...s, boundary_status: nextStatus } : s
    );
    setShots(updatedShots);

    try {
      await fetch(`${BACKEND_URL}/api/v1/shots/${shot.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ boundary_status: nextStatus })
      });
    } catch (err) {
      console.error("Failed to update shot boundary status:", err);
    }
  };

  const formatTime = (timeStr: string) => {
    const d = new Date(timeStr);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  const getBoundaryBadge = (status: string | null | undefined) => {
    if (!status) return <span className="text-gray-600">-</span>;
    switch (status) {
      case "certain":
        return <span className="px-1.5 py-0.5 rounded text-[9px] bg-emerald-950/40 text-emerald-400 border border-emerald-500/20 font-bold uppercase tracking-wider">Certain</span>;
      case "probable":
        return <span className="px-1.5 py-0.5 rounded text-[9px] bg-blue-950/40 text-blue-400 border border-blue-500/20 font-bold uppercase tracking-wider">Probable</span>;
      case "review_required":
        return <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-950/40 text-amber-400 border border-amber-500/20 font-bold uppercase tracking-wider animate-pulse">Review</span>;
      default:
        return <span className="text-gray-500">{status}</span>;
    }
  };

  return (
    <div className={forceMode ? "flex flex-col h-fit" : "glass-panel p-6 flex flex-col h-fit"}>
      {/* Sub-tab selection */}
      {!forceMode && (
        <div className="flex w-full border-b border-white/5 mb-4 gap-2">
          <button
            type="button"
            onClick={() => setActiveSubTab("shots")}
            className={`pb-2 text-xs font-mono uppercase font-bold tracking-wider transition-all border-b-2 px-1 ${
              activeSubTab === "shots"
                ? "text-neon border-neon font-extrabold"
                : "text-gray-500 hover:text-gray-300 border-transparent"
            }`}
          >
            Confirmed Shots ({filteredShots.length}{filteredShots.length !== currentShots.length ? ` / ${currentShots.length}` : ""})
          </button>
          {userRole !== "shooter" && !selectedShooter && (
            <button
              type="button"
              onClick={() => setActiveSubTab("candidates")}
              className={`pb-2 text-xs font-mono uppercase font-bold tracking-wider transition-all border-b-2 px-1 ${
                activeSubTab === "candidates"
                  ? "text-neon border-neon font-extrabold"
                  : "text-gray-500 hover:text-gray-300 border-transparent"
              }`}
            >
              Candidates Detected ({filteredCandidates.length}{(candidates && filteredCandidates.length !== candidates.length) ? ` / ${candidates.length}` : ""})
            </button>
          )}
        </div>
      )}

      {/* Filter Bar */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4 p-3 bg-white/2 border border-white/5 rounded-lg text-xs font-mono">
        <div className="space-y-1">
          <label className="text-[9px] uppercase text-gray-500">Search Number</label>
          <input
            type="text"
            placeholder={activeSubTab === "shots" ? "e.g. 1 or #2" : "e.g. C1 or 2"}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-neon transition"
          />
        </div>
        <div className="space-y-1">
          <label className="text-[9px] uppercase text-gray-500">Min Caliber (mm/px)</label>
          <input
            type="number"
            step="0.1"
            placeholder="Min size"
            value={minCaliber}
            onChange={(e) => setMinCaliber(e.target.value)}
            className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-neon transition"
          />
        </div>
        <div className="space-y-1">
          <label className="text-[9px] uppercase text-gray-500">Max Caliber (mm/px)</label>
          <input
            type="number"
            step="0.1"
            placeholder="Max size"
            value={maxCaliber}
            onChange={(e) => setMaxCaliber(e.target.value)}
            className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-neon transition"
          />
        </div>
        <div className="space-y-1">
          <label className="text-[9px] uppercase text-gray-500">
            {activeSubTab === "shots" ? "Min Score" : "Min Confidence (%)"}
          </label>
          <div className="flex gap-2 items-center">
            {activeSubTab === "shots" ? (
              <input
                type="number"
                min="0"
                max="10"
                step="1"
                placeholder="e.g. 8"
                value={minScore}
                onChange={(e) => setMinScore(e.target.value)}
                className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-neon transition"
              />
            ) : (
              <input
                type="number"
                min="0"
                max="100"
                step="5"
                placeholder="e.g. 50"
                value={minConfidence}
                onChange={(e) => setMinConfidence(e.target.value)}
                className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1 text-xs text-white focus:outline-none focus:border-neon transition"
              />
            )}
            {(minCaliber || maxCaliber || minScore || minConfidence || searchQuery) && (
              <button
                onClick={clearFilters}
                className="px-2.5 py-1 bg-red-950/40 border border-red-500/20 hover:bg-red-900/40 text-red-400 rounded transition text-[10px] uppercase font-bold"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[450px] pr-2 scrollbar-thin">
        {activeSubTab === "shots" ? (
          filteredShots.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 border border-dashed border-white/5 rounded-lg text-center">
              <HelpCircle className="w-8 h-8 text-gray-600 mb-2" />
              <p className="text-xs text-gray-500 font-mono">
                {currentShots.length === 0 ? "No bullet holes detected yet" : "No shots match the active filters"}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto w-full scrollbar-thin">
              <table className="w-full text-left text-xs font-mono whitespace-nowrap">
                <thead>
                  <tr className="border-b border-white/5 text-gray-400 uppercase text-[10px] pb-2">
                    <th className="py-2 px-1">Shot</th>
                    <th className="py-2 px-2">Position (mm)</th>
                    <th className="py-2 px-2">Caliber</th>
                    <th className="py-2 px-2">Score (Dec)</th>
                    <th className="py-2 px-2">Boundary</th>
                    <th className="py-2 px-2">Timestamp</th>
                    <th className="py-2 px-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredShots.map((shot) => {
                    const isSelected = shot.id === selectedShotId;
                    return (
                      <tr
                        key={shot.id}
                        onMouseEnter={() => handleRowHover(shot.id)}
                        onMouseLeave={() => handleRowHover(null)}
                        onClick={() => handleRowHover(shot.id)}
                        className={`border-b border-white/5 cursor-pointer transition-colors ${
                          !shot.is_valid 
                            ? "opacity-45 hover:bg-white/2" 
                            : isSelected 
                              ? "bg-white/5 text-neon" 
                              : "hover:bg-white/3"
                        }`}
                      >
                        <td className="py-3 px-1 font-bold">
                          #{shot.shot_number}
                        </td>
                        <td className="py-3 px-2">
                          {shot.x_calibrated !== null && shot.x_calibrated !== undefined && shot.y_calibrated !== null && shot.y_calibrated !== undefined ? (
                            <span>{shot.x_calibrated.toFixed(1)}, {shot.y_calibrated.toFixed(1)}</span>
                          ) : (
                            <span className="text-gray-500">Uncalibrated</span>
                          )}
                        </td>
                        <td className="py-3 px-2">
                          {shot.diameter_mm !== null && shot.diameter_mm !== undefined ? (
                            <span>{shot.diameter_mm.toFixed(1)} mm</span>
                          ) : (
                            <span>{shot.diameter_px.toFixed(0)} px</span>
                          )}
                        </td>
                        <td className="py-3 px-2 font-bold text-white">
                          {shot.score !== null && shot.score !== undefined ? (
                            <span>{shot.score} <span className="text-[10px] font-normal text-gray-400">({shot.decimal_score?.toFixed(1) || "0.0"})</span></span>
                          ) : (
                            <span className="text-gray-500">-</span>
                          )}
                        </td>
                        <td className="py-3 px-2">
                          {getBoundaryBadge(shot.boundary_status)}
                        </td>
                        <td className="py-3 px-2 text-gray-400">
                          {formatTime(shot.created_at)}
                        </td>
                        <td className="py-3 px-2 text-right">
                          {userRole === "shooter" ? (
                            <button
                              onClick={(e) => handleMarkForReview(shot, e)}
                              className={`p-1.5 rounded border transition-colors ${
                                shot.boundary_status === "review_required"
                                  ? "border-amber-500 bg-amber-950/40 text-amber-400 hover:bg-amber-900/40"
                                  : "border-white/10 hover:bg-white/10 text-gray-400 hover:text-white"
                              }`}
                              title={shot.boundary_status === "review_required" ? "Marked for Review" : "Mark for Review"}
                            >
                              <AlertTriangle className="w-3.5 h-3.5" />
                            </button>
                          ) : (
                            <button
                              onClick={(e) => toggleShotValidity(shot, e)}
                              className={`p-1.5 rounded border transition-colors ${
                                shot.is_valid 
                                  ? "border-emerald-500/10 text-emerald-400 hover:bg-emerald-400/10" 
                                  : "border-red-500/10 text-red-400 hover:bg-red-400/10"
                              }`}
                              title={shot.is_valid ? "Exclude Shot" : "Include Shot"}
                            >
                              {shot.is_valid ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        ) : (
          filteredCandidates.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 border border-dashed border-white/5 rounded-lg text-center">
              <HelpCircle className="w-8 h-8 text-gray-600 mb-2" />
              <p className="text-xs text-gray-500 font-mono">
                {!candidates || candidates.length === 0 ? "No candidate proposals detected yet" : "No candidates match the active filters"}
              </p>
              {!candidates || candidates.length === 0 ? (
                <p className="text-[10px] text-gray-600 font-mono mt-1 max-w-[200px]">
                  Run target detection/fire capture to view intermediate CV proposal metrics.
                </p>
              ) : null}
            </div>
          ) : (
            <div className="overflow-x-auto w-full scrollbar-thin">
              <table className="w-full text-left text-xs font-mono whitespace-nowrap">
                <thead>
                  <tr className="border-b border-white/5 text-gray-400 uppercase text-[10px] pb-2">
                    <th className="py-2 px-1">Candidate</th>
                    <th className="py-2 px-2">Raw Pos (px)</th>
                    <th className="py-2 px-2">Size (px)</th>
                    <th className="py-2 px-2">CV Conf</th>
                    <th className="py-2 px-2">Verifier</th>
                    <th className="py-2 px-2 text-right">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCandidates.map((candidate, idx) => {
                    return (
                      <tr
                        key={idx}
                        className={`border-b border-white/5 transition-colors hover:bg-white/3`}
                      >
                        <td className="py-3 px-1 font-bold text-gray-400">
                          #C{idx + 1}
                        </td>
                        <td className="py-3 px-2 text-gray-300">
                          {candidate.x_raw.toFixed(1)}, {candidate.y_raw.toFixed(1)}
                        </td>
                        <td className="py-3 px-2 text-gray-300">
                          {candidate.diameter_px.toFixed(1)} px
                        </td>
                        <td className="py-3 px-2 font-bold text-white">
                          {(candidate.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="py-3 px-2 text-gray-400">
                          <span className="font-mono bg-white/5 px-1.5 py-0.5 rounded border border-white/10 text-[10px]">
                            {candidate.verification_method}
                          </span>
                        </td>
                        <td className="py-3 px-2 text-right">
                          {candidate.is_verified ? (
                            <span className="px-1.5 py-0.5 rounded text-[9px] bg-emerald-950/40 text-emerald-400 border border-emerald-500/20 font-bold uppercase tracking-wider">
                              Confirmed
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 rounded text-[9px] bg-red-950/40 text-red-400 border border-red-500/20 font-bold uppercase tracking-wider">
                              Rejected
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  );
}
