"use client";

import React, { useState, useEffect } from "react";
import { useStore, Shot } from "@/store/useStore";
import { BarChart2, Hash, Settings, Sliders, Target, Crosshair } from "lucide-react";

interface StatsPanelProps {
  noBorder?: boolean;
  selectedShooter?: any | null;
}

export default function StatsPanel({ noBorder, selectedShooter = null }: StatsPanelProps = {}) {
  const { shots, userRole, activeSession } = useStore();

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
  const validShots = currentShots.filter((s) => s.is_valid);

  // Load custom point allocations from localStorage, or use defaults (10 points for ring 10, 9 for ring 9, etc.)
  const [pointAllocations, setPointAllocations] = useState<{ [key: number]: number }>({
    10: 10, 9: 9, 8: 8, 7: 7, 6: 6, 5: 5, 4: 4, 3: 3, 2: 2, 1: 1, 0: 0
  });
  const [scoreMultiplier, setScoreMultiplier] = useState<number>(1.0);
  const [showSettings, setShowSettings] = useState<boolean>(false);

  useEffect(() => {
    const savedAllocations = localStorage.getItem("pilss_point_allocations");
    const savedMultiplier = localStorage.getItem("pilss_score_multiplier");
    if (savedAllocations) {
      try {
        setPointAllocations(JSON.parse(savedAllocations));
      } catch (e) {
        console.error("Failed to parse saved allocations", e);
      }
    }
    if (savedMultiplier) {
      setScoreMultiplier(parseFloat(savedMultiplier) || 1.0);
    }
  }, []);

  const saveSettings = (allocs: typeof pointAllocations, mult: number) => {
    localStorage.setItem("pilss_point_allocations", JSON.stringify(allocs));
    localStorage.setItem("pilss_score_multiplier", mult.toString());
  };

  const handlePointChange = (ringValue: number, newVal: number) => {
    const updated = { ...pointAllocations, [ringValue]: newVal };
    setPointAllocations(updated);
    saveSettings(updated, scoreMultiplier);
  };

  const handleMultiplierChange = (newVal: number) => {
    setScoreMultiplier(newVal);
    saveSettings(pointAllocations, newVal);
  };

  // Helper to calculate the allocated points for a shot
  const getAllocatedPoints = (zoneScore: number | null | undefined): number => {
    if (zoneScore === null || zoneScore === undefined) return 0;
    const basePoints = pointAllocations[zoneScore] !== undefined ? pointAllocations[zoneScore] : zoneScore;
    return parseFloat((basePoints * scoreMultiplier).toFixed(2));
  };

  // Calculate Grouping (max distance between any two shots)
  const getGroupingDistanceMm = (): number => {
    if (validShots.length < 2) return 0;
    let maxDist = 0;
    for (let i = 0; i < validShots.length; i++) {
      for (let j = i + 1; j < validShots.length; j++) {
        const dx = (validShots[i].x_calibrated || 0) - (validShots[j].x_calibrated || 0);
        const dy = (validShots[i].y_calibrated || 0) - (validShots[j].y_calibrated || 0);
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > maxDist) {
          maxDist = dist;
        }
      }
    }
    return maxDist;
  };

  const groupingMm = getGroupingDistanceMm();
  const groupingInches = groupingMm / 25.4;

  // Round to 2-inch buckets (0-2, 2-4, 4-6, 6-8, 8-10)
  const getGroupingBucket = (inches: number): string => {
    if (validShots.length < 2) return "N/A (Requires >= 2 shots)";
    if (inches <= 2.0) return "0-2 inches";
    if (inches <= 4.0) return "2-4 inches";
    if (inches <= 6.0) return "4-6 inches";
    if (inches <= 8.0) return "6-8 inches";
    if (inches <= 10.0) return "8-10 inches";
    return ">10 inches";
  };

  const totalAllocatedPoints = validShots.reduce(
    (sum, s) => sum + getAllocatedPoints(s.score),
    0
  );
  return (
    <div className={noBorder ? "flex flex-col h-fit justify-between gap-4" : "glass-panel p-6 flex flex-col h-fit justify-between gap-4"}>
      <div className="flex flex-col flex-1 overflow-y-auto pr-1 scrollbar-thin space-y-3 max-h-[450px]">
        {/* Header */}
        <div className="flex justify-between items-center mb-1">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-neon" />
            <h3 className="text-base font-bold font-mono tracking-wider uppercase">Statistical Metrics</h3>
          </div>
          {userRole !== "shooter" && (
            <button
              onClick={() => setShowSettings(!showSettings)}
              className={`p-1.5 rounded-lg border transition ${
                showSettings 
                  ? "bg-neon/15 border-neon text-neon" 
                  : "bg-white/2 border-white/5 text-gray-400 hover:text-white hover:bg-white/5"
              }`}
              title="Configure Point Allocations"
            >
              <Settings className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Configuration Section (Collapsible Settings) */}
        {showSettings ? (
          <div className="bg-[#090d16] border border-white/5 rounded-lg p-4 mb-1 space-y-3 max-h-[200px] overflow-y-auto scrollbar-thin">
            <div className="flex items-center gap-1.5 pb-2 border-b border-white/5">
              <Sliders className="w-3.5 h-3.5 text-neon" />
              <h4 className="text-xs font-mono font-bold text-white uppercase">Point Allocations Settings</h4>
            </div>

            {/* Score Multiplier */}
            <div className="flex justify-between items-center">
              <label className="text-[10px] font-mono text-gray-400 uppercase">Multiplier</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={scoreMultiplier}
                onChange={(e) => handleMultiplierChange(parseFloat(e.target.value) || 1.0)}
                className="w-20 bg-[#030712] border border-white/10 rounded px-2 py-1 text-xs font-mono text-white text-center focus:outline-none focus:border-neon"
              />
            </div>

            {/* Custom ring weights */}
            <div className="space-y-2 pt-1">
              <p className="text-[9px] font-mono text-gray-500 uppercase tracking-wider">Configure Points Per Ring Application:</p>
              <div className="grid grid-cols-2 gap-2">
                {[10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map((ring) => (
                  <div key={ring} className="flex justify-between items-center gap-1 bg-white/2 p-1.5 rounded border border-white/2">
                    <span className="text-[10px] font-mono text-neon font-bold">Ring {ring}</span>
                    <input
                      type="number"
                      min="0"
                      value={pointAllocations[ring] !== undefined ? pointAllocations[ring] : ring}
                      onChange={(e) => handlePointChange(ring, parseInt(e.target.value) || 0)}
                      className="w-10 bg-[#030712] border border-white/10 rounded py-0.5 text-center text-xs font-mono text-white focus:outline-none"
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        {/* Grouping Card */}
        <div className="bg-white/2 border border-white/5 p-4 rounded-lg flex flex-col gap-1.5 mb-1 font-mono">
          <div className="flex justify-between items-center">
            <span className="text-xs text-gray-400 flex items-center gap-1.5">
              <Crosshair className="w-3.5 h-3.5 text-neon" />
              Grouping (Max Spread)
            </span>
            <span className="text-sm font-bold text-neon">
              {groupingMm > 0 ? `${groupingInches.toFixed(2)}"` : "N/A"}
            </span>
          </div>
          <div className="flex justify-between items-center text-[11px]">
            <span className="text-gray-500">Max Bullet Distance:</span>
            <span className="text-gray-400 font-bold">{groupingMm.toFixed(1)} mm</span>
          </div>
          <div className="mt-1 pt-1.5 border-t border-white/5 flex justify-between items-center text-xs">
            <span className="text-gray-400 font-bold">Grouping Category:</span>
            <span className="px-2 py-0.5 bg-neon/10 border border-neon/30 text-neon rounded font-bold text-[10px]">
              {getGroupingBucket(groupingInches)}
            </span>
          </div>
        </div>

        {/* Shots List (Application Score and Allocated Points) */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-[10px] font-mono uppercase tracking-wider text-gray-500 px-2">
            <span>Shot Number & Application</span>
            <span>Allocated Points</span>
          </div>
          {validShots.length === 0 ? (
            <div className="flex flex-col items-center justify-center text-center p-4 border border-dashed border-white/5 rounded-lg">
              <Target className="w-8 h-8 text-gray-600 mb-1.5" />
              <p className="text-[10px] font-mono text-gray-500">No shots recorded yet.</p>
            </div>
          ) : (
            validShots.map((shot, idx) => (
              <div
                key={shot.id}
                className="flex justify-between items-center bg-white/2 border border-white/5 px-3 py-2 rounded-lg font-mono text-xs hover:border-white/10 transition"
              >
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 font-bold">#{shot.shot_number}</span>
                  <span className="text-white bg-white/5 px-1.5 py-0.5 rounded border border-white/5">
                    Application {shot.score ?? "Out"}
                  </span>
                </div>
                <span className="font-bold text-emerald-400">
                  {getAllocatedPoints(shot.score)} pts
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Bottom Summary Panel */}
      <div className="border-t border-white/5 pt-4 mt-1 bg-white/1 rounded-lg p-3 border border-white/5">
        <div className="flex justify-between items-center font-mono">
          <div className="leading-tight">
            <p className="text-[10px] text-gray-500 uppercase tracking-wider">Total Allocated Points</p>
            <p className="text-[9px] text-gray-600 mt-0.5">Custom configurations applied</p>
          </div>
          <span className="text-xl font-bold font-mono text-emerald-400">
            {totalAllocatedPoints.toFixed(1)} <span className="text-xs text-gray-500">pts</span>
          </span>
        </div>
      </div>
    </div>
  );
}
