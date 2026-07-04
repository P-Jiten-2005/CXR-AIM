"use client";

import React, { useState, useEffect } from "react";
import { useStore, Shot } from "@/store/useStore";
import { Target, AlertCircle, Crosshair, Award, Clock, Shield, Camera } from "lucide-react";

interface OverviewCardsProps {
  isMonitoringShooter?: boolean;
  selectedShooter?: any | null;
}

export default function OverviewCards({ 
  isMonitoringShooter = false,
  selectedShooter = null 
}: OverviewCardsProps = {}) {
  const { shots, activeSession, userRole, statistics } = useStore();
  
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

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return "N/A";
    const date = new Date(timeStr);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  // Grouping (max distance between any two shots)
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

  // Missed shots calculation
  const missedShots = validShots.filter(
    (s) => s.score === 0 || s.score === null || s.score === undefined
  ).length;

  // Custom point allocations loading from localStorage
  const [pointAllocations, setPointAllocations] = useState<{ [key: number]: number }>({
    10: 10, 9: 9, 8: 8, 7: 7, 6: 6, 5: 5, 4: 4, 3: 3, 2: 2, 1: 1, 0: 0
  });
  const [scoreMultiplier, setScoreMultiplier] = useState<number>(1.0);

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
  }, [shots]);

  const getAllocatedPoints = (zoneScore: number | null | undefined): number => {
    if (zoneScore === null || zoneScore === undefined) return 0;
    const basePoints = pointAllocations[zoneScore] !== undefined ? pointAllocations[zoneScore] : zoneScore;
    return parseFloat((basePoints * scoreMultiplier).toFixed(2));
  };

  const totalScore = validShots.reduce(
    (sum, s) => sum + getAllocatedPoints(s.score),
    0
  );

  const shooterCards = [
    {
      title: "Shots",
      value: activeSession ? `${validShots.length}/${activeSession.bullets_per_drill || 0}` : "0",
      description: "Confirmed bullet impacts",
      icon: Target,
      colorClass: "text-emerald-400",
      glowColor: "rgba(16, 185, 129, 0.2)"
    },
    {
      title: "Missed Shots",
      value: missedShots,
      description: "Impacts outside scoring applications",
      icon: AlertCircle,
      colorClass: "text-red-400",
      glowColor: "rgba(239, 68, 68, 0.2)"
    },
    {
      title: "Grouping",
      value: groupingMm > 0 ? `${groupingInches.toFixed(2)}"` : "N/A",
      description: groupingMm > 0 ? `${groupingMm.toFixed(1)} mm spread` : "Requires >= 2 shots",
      icon: Crosshair,
      colorClass: "text-blue-400",
      glowColor: "rgba(59, 130, 246, 0.2)"
    },
    {
      title: "Total Score",
      value: `${totalScore.toFixed(1)} pts`,
      description: "Accumulated application points",
      icon: Award,
      colorClass: "text-amber-400",
      glowColor: "rgba(245, 158, 11, 0.2)"
    }
  ];

  const originalCards = [
    {
      title: "Shots",
      value: activeSession ? `${statistics.total_shots}/${activeSession.bullets_per_drill || 0}` : "0",
      description: "Validated bullet impacts",
      icon: Target,
      colorClass: "text-emerald-400",
      glowColor: "rgba(16, 185, 129, 0.2)"
    },
    {
      title: "Last Detection Time",
      value: formatTime(statistics.last_shot_time),
      description: activeSession ? "Live session timeline" : "No active recordings",
      icon: Clock,
      colorClass: "text-blue-400",
      glowColor: "rgba(59, 130, 246, 0.2)"
    },
    {
      title: "Current Session",
      value: activeSession ? activeSession.name : "None Active",
      description: activeSession 
        ? `${activeSession.target_type.split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")}${activeSession.session_range ? ` • ${activeSession.session_range}` : ""}${activeSession.drill_type ? ` • ${activeSession.drill_type.charAt(0).toUpperCase() + activeSession.drill_type.slice(1)}` : ""}`
        : "Start a session to capture",
      icon: Shield,
      colorClass: "text-amber-400",
      glowColor: "rgba(245, 158, 11, 0.2)"
    },
    {
      title: "Optical Sensor",
      value: statistics.camera_status.toUpperCase(),
      description: "Fixed mounted camera feed",
      icon: Camera,
      colorClass: statistics.camera_status === "online" ? "text-emerald-400" : "text-red-400",
      glowColor: statistics.camera_status === "online" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)"
    }
  ];

  const cards = (userRole === "shooter" || userRole === "instructor")
    ? shooterCards 
    : originalCards;

  return (
    <div className={`grid grid-cols-1 md:grid-cols-2 ${cards.length === 4 ? "lg:grid-cols-4" : "lg:grid-cols-2"} gap-4`}>
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div
            key={idx}
            className="glass-panel p-5 relative overflow-hidden group transition-all duration-300 hover:-translate-y-1 hover:border-white/15 cursor-pointer"
            style={{
              boxShadow: `0 8px 32px 0 rgba(0, 0, 0, 0.25), 0 0 10px ${card.glowColor}`
            }}
          >
            {/* Hover reflection */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-white/2 rounded-full blur-2xl -mr-8 -mt-8 transition-transform group-hover:scale-125 duration-500" />
            
            <div className="flex justify-between items-start">
              <div>
                <p className="text-xs text-gray-400 font-medium tracking-wide uppercase">{card.title}</p>
                <h3 className="text-2xl font-bold font-mono tracking-tight mt-1.5">{card.value}</h3>
              </div>
              <div className={`p-2.5 rounded-lg bg-white/3 border border-white/5 ${card.colorClass}`}>
                <Icon className="w-5 h-5" />
              </div>
            </div>
            
            <p className="text-xs text-gray-500 mt-3 font-medium">{card.description}</p>
          </div>
        );
      })}
    </div>
  );
}
