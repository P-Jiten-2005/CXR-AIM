"use client";
import { BACKEND_URL } from "@/config";

import React, { useRef, useEffect, useState } from "react";
import { useStore, Shot, Candidate } from "@/store/useStore";
import { Maximize2, ShieldAlert, Crosshair, Trash2, Eye, EyeOff } from "lucide-react";

interface LiveTargetViewProps {
  cameraOnline: boolean;
  isCameraActive: boolean;
  pingCooldown: number;
  handlePingCamera: () => Promise<void>;
  selectedShooter?: any | null;
}

export default function LiveTargetView({
  cameraOnline,
  isCameraActive,
  pingCooldown,
  handlePingCamera,
  selectedShooter = null
}: LiveTargetViewProps) {
  const { 
    shots, 
    candidates, 
    selectedShotId, 
    setSelectedShotId, 
    baselineUrl, 
    currentFrameUrl, 
    activeSession, 
    setShots, 
    setStatistics, 
    setCurrentFrameUrl, 
    targetDefinition,
    userRole,
    minCaliber,
    maxCaliber,
    minScore,
    minConfidence,
    searchQuery
  } = useStore();

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
  
  const [isClearing, setIsClearing] = useState(false);
  const [showCandidates, setShowCandidates] = useState(true);
  const [showMarkings, setShowMarkings] = useState(true);

  const handleClearShots = async () => {
    if (!activeSession) return;
    if (!confirm("Are you sure you want to clear all shot markings from this session?")) return;
    setIsClearing(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/sessions/${activeSession.id}/shots`, { method: "DELETE" });
      if (res.ok) {
        setShots([]);
        setCurrentFrameUrl(null);
        setStatistics({
          total_shots: 0,
          average_diameter_px: 0.0,
          largest_diameter_px: 0.0,
          smallest_diameter_px: 0.0,
          last_shot_time: null,
          session_status: activeSession.status,
          camera_status: "online"
        });
      }
    } catch (err) {
      console.error("Failed to clear shots:", err);
    } finally {
      setIsClearing(false);
    }
  };
  
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [imgLoaded, setImgLoaded] = useState(false);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 600 });
  const scaleRef = useRef(1);
  const offsetRef = useRef({ x: 0, y: 0 });
  const mmScaleXRef = useRef(1);
  const mmScaleYRef = useRef(1);

  // Use currentFrameUrl if available, otherwise fall back to baselineUrl
  const activeImageUrl = currentFrameUrl || baselineUrl;

  const [calibrationAspectRatio, setCalibrationAspectRatio] = useState<number | null>(null);

  // Load baseline/calibration image to determine aspect ratio for consistent scaling
  useEffect(() => {
    const url = baselineUrl || activeImageUrl;
    if (!url) return;
    const img = new Image();
    img.src = url.startsWith("http") ? url : `${BACKEND_URL}${url}`;
    img.onload = () => {
      if (img.naturalWidth && img.naturalHeight) {
        setCalibrationAspectRatio(img.naturalWidth / img.naturalHeight);
      }
    };
  }, [baselineUrl, activeImageUrl]);

  const [activeTab, setActiveTab] = useState<"markings" | "calibration" | "rectified" | "alignment" | "diff" | "virtual">("rectified");
  const [debugRefreshKey, setDebugRefreshKey] = useState(Date.now());
  const [alignmentError, setAlignmentError] = useState(false);
  const [diffError, setDiffError] = useState(false);
  const [calibrationError, setCalibrationError] = useState(false);
  const [rectifiedError, setRectifiedError] = useState(false);
  const [projectedZones, setProjectedZones] = useState<{
    scoring_regions: any[];
    bullseyes: any[];
  } | null>(null);

  // Load target preview image if active tab is virtual target, plain rectified for rectified tab, otherwise load camera frame
  const virtualTargetImageUrl = targetDefinition?.preview_url;
  const rectifiedImageUrl = activeSession ? `/static/uploads/rectified_${activeSession.id}.png?t=${debugRefreshKey}` : null;
  const currentBgUrl = activeTab === "virtual" 
    ? virtualTargetImageUrl 
    : activeTab === "rectified" 
      ? rectifiedImageUrl 
      : activeTab === "markings"
        ? activeImageUrl
        : null;

  useEffect(() => {
    if (!activeSession) {
      setProjectedZones(null);
      return;
    }
    const fetchProjectedZones = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/v1/sessions/${activeSession.id}/projected-zones`);
        if (res.ok) {
          const data = await res.json();
          setProjectedZones(data);
        }
      } catch (err) {
        console.error("Failed to fetch projected zones:", err);
      }
    };
    fetchProjectedZones();
  }, [activeSession?.id, baselineUrl]);

  useEffect(() => {
    setDebugRefreshKey(Date.now());
    setAlignmentError(false);
    setDiffError(false);
    setCalibrationError(false);
    setRectifiedError(false);
  }, [currentShots.length, activeTab]);

  // Reset active tab to markings if role restriction changes and user loses access
  useEffect(() => {
    if (userRole === "shooter" && activeTab !== "markings" && activeTab !== "calibration" && activeTab !== "rectified" && activeTab !== "virtual") {
      setActiveTab("markings");
    } else if (userRole === "instructor" && (activeTab === "alignment" || activeTab === "diff")) {
      setActiveTab("markings");
    }
  }, [userRole, activeTab]);

  // Handle image loading
  useEffect(() => {
    if (!currentBgUrl) {
      setImgLoaded(false);
      imageRef.current = null;
      return;
    }

    const img = new Image();
    img.src = currentBgUrl.startsWith("http") ? currentBgUrl : `${BACKEND_URL}${currentBgUrl}`;
    img.onload = () => {
      imageRef.current = img;
      setImgLoaded(true);
      triggerResize();
    };
    img.onerror = () => {
      // Expected before a baseline/debug image exists (e.g. rectified/aligned/diff aren't
      // produced until after calibration). The per-tab error state shows a friendly
      // placeholder, so this is handled quietly rather than logged as a console error.
      setImgLoaded(false);
      if (activeTab === "rectified") {
        setRectifiedError(true);
      }
    };
  }, [currentBgUrl, activeTab]);

  // Handle responsive resizing
  const triggerResize = () => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const width = Math.max(260, Math.min(rect.width - 66, 600));

    // Determine target aspect ratio to prevent squishing and compute height dynamically
    // We prioritize using the calibration aspect ratio so that all tabs maintain the same scale/dimensions.
    let imgRatio = 1.0;
    if (calibrationAspectRatio !== null && isFinite(calibrationAspectRatio) && calibrationAspectRatio > 0) {
      imgRatio = calibrationAspectRatio;
    } else if (imageRef.current && imageRef.current.naturalWidth && imageRef.current.naturalHeight) {
      imgRatio = imageRef.current.naturalWidth / imageRef.current.naturalHeight;
    } else if (targetDefinition && targetDefinition.width_mm && targetDefinition.height_mm) {
      imgRatio = targetDefinition.width_mm / targetDefinition.height_mm;
    }

    if (!isFinite(imgRatio) || imgRatio <= 0) {
      imgRatio = 1.0;
    }

    const height = Math.round(width / imgRatio);
    setDimensions({ width, height });
  };

  useEffect(() => {
    triggerResize();
    window.addEventListener("resize", triggerResize);
    return () => window.removeEventListener("resize", triggerResize);
  }, [imgLoaded, targetDefinition, activeTab, currentBgUrl, calibrationAspectRatio]);

  // Main Canvas Render loop
  useEffect(() => {
    if (activeTab !== "markings" && activeTab !== "virtual" && activeTab !== "rectified") return;

    let animationFrameId: number;

    const render = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";

      const hasBgImage = imgLoaded && imageRef.current;
      
      if (hasBgImage || (activeTab === "virtual" && targetDefinition)) {
        const img = imageRef.current;
        const targetW = targetDefinition?.width_mm || 500;
        const targetH = targetDefinition?.height_mm || 500;
        let imgRatio = hasBgImage && img
          ? img.naturalWidth / img.naturalHeight
          : targetW / targetH;
        if (!isFinite(imgRatio) || imgRatio <= 0) {
          imgRatio = 1.0;
        }

        const canvasRatio = canvas.width / canvas.height;
        let drawW = canvas.width;
        let drawH = canvas.height;
        let dx = 0;
        let dy = 0;

        if (imgRatio > canvasRatio) {
          drawW = canvas.width;
          drawH = canvas.width / imgRatio;
          dy = (canvas.height - drawH) / 2;
        } else {
          drawH = canvas.height;
          drawW = canvas.height * imgRatio;
          dx = (canvas.width - drawW) / 2;
        }

        // Draw background
        if (hasBgImage && img) {
          ctx.drawImage(img, dx, dy, drawW, drawH);
          if (activeTab === "virtual" && targetDefinition) {
            scaleRef.current = drawW / targetDefinition.width_mm;
          } else if (activeTab === "rectified") {
            scaleRef.current = drawW / 1000.0;
          } else {
            scaleRef.current = drawW / img.naturalWidth;
          }
        } else {
          // Draw fallback digital target paper sheet
          ctx.fillStyle = "#1e293b"; // Slate-800 backdrop
          ctx.fillRect(0, 0, canvas.width, canvas.height);

          ctx.fillStyle = "#f8fafc"; // Slate-50 off-white paper
          ctx.fillRect(dx, dy, drawW, drawH);
          ctx.strokeStyle = "#94a3b8"; // Slate-400 border
          ctx.lineWidth = 2;
          ctx.strokeRect(dx, dy, drawW, drawH);

          if (activeTab === "rectified") {
            scaleRef.current = drawW / 1000.0;
          } else {
            scaleRef.current = drawW / targetW;
          }
        }

        offsetRef.current = { x: dx, y: dy };
        const currentScale = scaleRef.current;
        const mmToCanvasScaleX = drawW / (targetDefinition?.width_mm || 500);
        const mmToCanvasScaleY = drawH / (targetDefinition?.height_mm || 500);
        mmScaleXRef.current = mmToCanvasScaleX;
        mmScaleYRef.current = mmToCanvasScaleY;

        // 1. Draw target definitions (digital/virtual/rectified) or projected overlays
        if ((activeTab === "virtual" || activeTab === "rectified") && showMarkings && targetDefinition) {
          const isRectifiedWithProjected = activeTab === "rectified" && projectedZones;

          // A. Draw Rectangular Scoring Regions
          if (isRectifiedWithProjected && projectedZones.scoring_regions && projectedZones.scoring_regions.length > 0) {
            projectedZones.scoring_regions.forEach((region: any) => {
              if (region.warped_polygon && region.warped_polygon.length === 4) {
                const pts = region.warped_polygon.map((pt: any) => ({
                  x: pt[0] * currentScale + dx,
                  y: pt[1] * currentScale + dy
                }));

                ctx.strokeStyle = "rgba(99, 102, 241, 0.45)"; // Indigo border
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(pts[0].x, pts[0].y);
                ctx.lineTo(pts[1].x, pts[1].y);
                ctx.lineTo(pts[2].x, pts[2].y);
                ctx.lineTo(pts[3].x, pts[3].y);
                ctx.closePath();
                ctx.stroke();

                ctx.fillStyle = "rgba(99, 102, 241, 0.85)";
                ctx.font = "bold 9px monospace";
                ctx.textAlign = "left";
                ctx.textBaseline = "top";
                ctx.fillText(`${region.name || "Application"} (${region.value} pts)`, pts[0].x + 4, pts[0].y + 4);
              }
            });
          } else if (targetDefinition.scoring_regions && targetDefinition.scoring_regions.length > 0) {
            targetDefinition.scoring_regions.forEach((region: any) => {
              const rx_mm = region.x_min_mm;
              const ry_mm = region.y_min_mm;
              const rw_mm = region.x_max_mm - region.x_min_mm;
              const rh_mm = region.y_max_mm - region.y_min_mm;

              const rx = rx_mm * mmToCanvasScaleX + dx;
              const ry = ry_mm * mmToCanvasScaleY + dy;
              const rw = rw_mm * mmToCanvasScaleX;
              const rh = rh_mm * mmToCanvasScaleY;

              ctx.strokeStyle = "rgba(99, 102, 241, 0.45)"; // Indigo border
              ctx.lineWidth = 1.5;
              ctx.strokeRect(rx, ry, rw, rh);

              ctx.fillStyle = "rgba(99, 102, 241, 0.85)";
              ctx.font = "bold 9px monospace";
              ctx.textAlign = "left";
              ctx.textBaseline = "top";
              ctx.fillText(`${region.name || "Application"} (${region.value} pts)`, rx + 4, ry + 4);
            });
          }

          // B. Draw Circular Concentric Bullseye Rings
          if (isRectifiedWithProjected && projectedZones.bullseyes && projectedZones.bullseyes.length > 0) {
            projectedZones.bullseyes.forEach((bullseye: any) => {
              if (bullseye.center_warped) {
                const cx = bullseye.center_warped[0] * currentScale + dx;
                const cy = bullseye.center_warped[1] * currentScale + dy;

                ctx.strokeStyle = "rgba(239, 68, 68, 0.6)";
                ctx.lineWidth = 1.25;
                ctx.beginPath();
                ctx.moveTo(cx - 10, cy);
                ctx.lineTo(cx + 10, cy);
                ctx.moveTo(cx, cy - 10);
                ctx.lineTo(cx, cy + 10);
                ctx.stroke();

                if (bullseye.rings && bullseye.rings.length > 0) {
                  bullseye.rings.forEach((ring: any) => {
                    const r = ring.warped_radius * currentScale;

                    ctx.strokeStyle = "rgba(16, 185, 129, 0.45)";
                    ctx.lineWidth = 1.25;
                    ctx.beginPath();
                    ctx.arc(cx, cy, r, 0, 2 * Math.PI);
                    ctx.stroke();

                    ctx.fillStyle = "rgba(16, 185, 129, 0.75)";
                    ctx.font = "bold 9px monospace";
                    ctx.textAlign = "center";
                    ctx.textBaseline = "bottom";
                    ctx.fillText(ring.value.toString(), cx, cy - r + 2);
                  });
                }
              }
            });
          } else if (targetDefinition.bullseyes && targetDefinition.bullseyes.length > 0) {
            targetDefinition.bullseyes.forEach((bullseye: any) => {
              const cx_mm = bullseye.center_x_mm;
              const cy_mm = bullseye.center_y_mm;

              const cx = cx_mm * mmToCanvasScaleX + dx;
              const cy = cy_mm * mmToCanvasScaleY + dy;

              ctx.strokeStyle = "rgba(239, 68, 68, 0.6)";
              ctx.lineWidth = 1.25;
              ctx.beginPath();
              ctx.moveTo(cx - 10, cy);
              ctx.lineTo(cx + 10, cy);
              ctx.moveTo(cx, cy - 10);
              ctx.lineTo(cx, cy + 10);
              ctx.stroke();

              if (bullseye.rings && bullseye.rings.length > 0) {
                bullseye.rings.forEach((ring: any) => {
                  const r_mm = ring.outer_radius_mm;
                  const r = r_mm * mmToCanvasScaleX;

                  ctx.strokeStyle = "rgba(16, 185, 129, 0.45)";
                  ctx.lineWidth = 1.25;
                  ctx.beginPath();
                  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
                  ctx.stroke();

                  ctx.fillStyle = "rgba(16, 185, 129, 0.75)";
                  ctx.font = "bold 9px monospace";
                  ctx.textAlign = "center";
                  ctx.textBaseline = "bottom";
                  ctx.fillText(ring.value.toString(), cx, cy - r + 2);
                });
              }
            });
          }
        }


        // 2. Draw shots
        filteredShots.forEach((shot) => {
          if (!shot.is_valid) return;

          let canvasX: number;
          let canvasY: number;
          let radius: number;

          if (activeTab === "virtual") {
            if (shot.x_calibrated === null || shot.y_calibrated === null) return;
            canvasX = shot.x_calibrated * mmToCanvasScaleX + dx;
            canvasY = shot.y_calibrated * mmToCanvasScaleY + dy;
            const diameter_mm = shot.diameter_mm || targetDefinition?.bullet_caliber || 4.5;
            radius = (diameter_mm * mmToCanvasScaleX) / 2;
          } else if (activeTab === "rectified") {
            const wx = shot.x_warped !== null && shot.x_warped !== undefined ? shot.x_warped : shot.x_raw;
            const wy = shot.y_warped !== null && shot.y_warped !== undefined ? shot.y_warped : shot.y_raw;
            canvasX = wx * currentScale + dx;
            canvasY = wy * currentScale + dy;
            const diameter_mm = shot.diameter_mm || targetDefinition?.bullet_caliber || 4.5;
            radius = (diameter_mm * mmToCanvasScaleX) / 2;
          } else {
            canvasX = shot.x_raw * currentScale + dx;
            canvasY = shot.y_raw * currentScale + dy;
            radius = (shot.diameter_px * currentScale) / 2;
          }

          const isSelected = shot.id === selectedShotId;

          // Draw detailed contour if available (only in Real Image tab)
          if (activeTab === "markings" && shot.detection && shot.detection.raw_contour) {
            ctx.beginPath();
            shot.detection.raw_contour.forEach((pt, index) => {
              const px = pt[0] * currentScale + dx;
              const py = pt[1] * currentScale + dy;
              if (index === 0) ctx.moveTo(px, py);
              else ctx.lineTo(px, py);
            });
            ctx.closePath();
            ctx.strokeStyle = isSelected ? "#ef4444" : "#10b981";
            ctx.lineWidth = isSelected ? 3 : 1.5;
            ctx.stroke();
            ctx.fillStyle = isSelected ? "rgba(239, 68, 68, 0.2)" : "rgba(16, 185, 129, 0.1)";
            ctx.fill();
          } else {
            // Standard circle rendering
            ctx.beginPath();
            ctx.arc(canvasX, canvasY, Math.max(radius, 4), 0, 2 * Math.PI);
            ctx.fillStyle = isSelected ? "rgba(239, 68, 68, 0.4)" : "rgba(16, 185, 129, 0.35)";
            ctx.fill();
            ctx.strokeStyle = isSelected ? "#ef4444" : "#10b981";
            ctx.lineWidth = isSelected ? 2.5 : 1.5;
            ctx.stroke();
          }

          if (isSelected) {
            ctx.beginPath();
            ctx.arc(canvasX, canvasY, Math.max(radius, 4) + 8, 0, 2 * Math.PI);
            ctx.strokeStyle = "rgba(239, 68, 68, 0.4)";
            ctx.lineWidth = 1;
            ctx.stroke();
          }

          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 10px monospace";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          
          ctx.beginPath();
          ctx.arc(canvasX, canvasY - Math.max(radius, 4) - 10, 8, 0, 2 * Math.PI);
          ctx.fillStyle = isSelected ? "#ef4444" : "#0f172a";
          ctx.fill();
          ctx.strokeStyle = isSelected ? "#ffffff" : "#10b981";
          ctx.lineWidth = 1;
          ctx.stroke();

          ctx.fillStyle = "#ffffff";
          ctx.fillText(shot.shot_number.toString(), canvasX, canvasY - Math.max(radius, 4) - 10);
        });

        // 3. Draw unverified candidates (Only in Real Image and Rectified tabs for non-shooter views)
        if ((activeTab === "markings" || activeTab === "rectified") && showCandidates && filteredCandidates && filteredCandidates.length > 0 && userRole !== "shooter" && !selectedShooter) {
          filteredCandidates.forEach((candidate, idx) => {
            if (candidate.is_verified) return;

            let canvasX: number;
            let canvasY: number;
            let radius: number;

            if (activeTab === "rectified") {
              const cx_warped = candidate.x_warped !== null && candidate.x_warped !== undefined ? candidate.x_warped : candidate.x_raw;
              const cy_warped = candidate.y_warped !== null && candidate.y_warped !== undefined ? candidate.y_warped : candidate.y_raw;
              canvasX = cx_warped * currentScale + dx;
              canvasY = cy_warped * currentScale + dy;
              
              const rawWidth = imageRef.current ? imageRef.current.naturalWidth : 1000;
              radius = (candidate.diameter_px * (1000 / rawWidth) * currentScale) / 2;
            } else {
              canvasX = candidate.x_raw * currentScale + dx;
              canvasY = candidate.y_raw * currentScale + dy;
              radius = (candidate.diameter_px * currentScale) / 2;
            }

            ctx.beginPath();
            ctx.arc(canvasX, canvasY, Math.max(radius, 4), 0, 2 * Math.PI);
            ctx.strokeStyle = "rgba(249, 115, 22, 0.85)";
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 4]);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = "rgba(249, 115, 22, 0.15)";
            ctx.fill();

            ctx.fillStyle = "#f97316";
            ctx.font = "bold 9px monospace";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";

            ctx.beginPath();
            ctx.arc(canvasX, canvasY - Math.max(radius, 4) - 10, 8, 0, 2 * Math.PI);
            ctx.fillStyle = "#f97316";
            ctx.fill();
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1;
            ctx.stroke();

            ctx.fillStyle = "#ffffff";
            ctx.fillText(`C${idx + 1}`, canvasX, canvasY - Math.max(radius, 4) - 10);
          });
        }
      } else {
        scaleRef.current = 1;
        offsetRef.current = { x: 0, y: 0 };

        const cx = canvas.width / 2;
        const cy = canvas.height / 2;

        ctx.strokeStyle = "rgba(255, 255, 255, 0.02)";
        ctx.lineWidth = 1;
        const gridSize = 40;
        for (let x = gridSize; x < canvas.width; x += gridSize) {
          ctx.beginPath();
          ctx.moveTo(x, 0);
          ctx.lineTo(x, canvas.height);
          ctx.stroke();
        }
        for (let y = gridSize; y < canvas.height; y += gridSize) {
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(canvas.width, y);
          ctx.stroke();
        }

        ctx.strokeStyle = "rgba(16, 185, 129, 0.15)";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(0, cy);
        ctx.lineTo(canvas.width, cy);
        ctx.moveTo(cx, 0);
        ctx.lineTo(cx, canvas.height);
        ctx.stroke();

        ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
        ctx.lineWidth = 1;
        ctx.strokeRect(20, 20, canvas.width - 40, canvas.height - 40);

        ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
        ctx.font = "bold 11px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("AWAITING TARGET CALIBRATION BASELINE", cx, cy);
      }
    };

    render();
    animationFrameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [imgLoaded, currentShots, candidates, filteredShots, filteredCandidates, showCandidates, selectedShotId, dimensions, targetDefinition, activeTab, projectedZones, showMarkings, selectedShooter]);

  // Handle hover detection
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || filteredShots.length === 0) return;
    
    // Restrict hover selection to markings (Real Image), virtual target, and rectified tabs
    if (activeTab !== "markings" && activeTab !== "virtual" && activeTab !== "rectified") {
      if (selectedShotId !== null) {
        setSelectedShotId(null);
      }
      return;
    }

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let hoveredShotId: string | null = null;
    let minDistance = 20;

    const mmToCanvasScale = canvas.width / (targetDefinition?.width_mm || 500);

    filteredShots.forEach((shot) => {
      if (!shot.is_valid) return;
      
      let canvasX: number;
      let canvasY: number;
      if (activeTab === "virtual") {
        if (shot.x_calibrated === null || shot.y_calibrated === null) return;
        canvasX = shot.x_calibrated * mmScaleXRef.current + offsetRef.current.x;
        canvasY = shot.y_calibrated * mmScaleYRef.current + offsetRef.current.y;
      } else if (activeTab === "rectified") {
        const wx = shot.x_warped !== null && shot.x_warped !== undefined ? shot.x_warped : shot.x_raw;
        const wy = shot.y_warped !== null && shot.y_warped !== undefined ? shot.y_warped : shot.y_raw;
        canvasX = wx * scaleRef.current + offsetRef.current.x;
        canvasY = wy * scaleRef.current + offsetRef.current.y;
      } else {
        canvasX = shot.x_raw * scaleRef.current + offsetRef.current.x;
        canvasY = shot.y_raw * scaleRef.current + offsetRef.current.y;
      }
      
      const distance = Math.sqrt((mouseX - canvasX) ** 2 + (mouseY - canvasY) ** 2);
      if (distance < minDistance) {
        minDistance = distance;
        hoveredShotId = shot.id;
      }
    });

    if (hoveredShotId !== selectedShotId) {
      setSelectedShotId(hoveredShotId);
    }
  };

  const handleMouseLeave = () => {
    setSelectedShotId(null);
  };

  return (
    <div ref={containerRef} className="glass-panel p-6 flex flex-col items-center justify-between h-fit w-full">
      {userRole === "shooter" ? (
        <>
          {/* Main Tabs row (Segmented layout to match mockup) */}
          <div className="grid grid-cols-3 w-full gap-2 mb-4">
            <button
              type="button"
              onClick={() => setActiveTab("rectified")}
              disabled={!activeSession}
              className={`py-2.5 text-center font-mono text-xs uppercase font-bold tracking-wider rounded-lg transition border ${
                !activeSession ? "opacity-30 cursor-not-allowed border-transparent" : ""
              } ${
                activeTab === "rectified"
                  ? "bg-neon/15 text-neon border-neon shadow-md"
                  : "bg-white/5 text-gray-400 border-white/10 hover:text-white hover:bg-white/10"
              }`}
            >
              Adjusted View
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("virtual")}
              disabled={!activeSession}
              className={`py-2.5 text-center font-mono text-xs uppercase font-bold tracking-wider rounded-lg transition border ${
                !activeSession ? "opacity-30 cursor-not-allowed border-transparent" : ""
              } ${
                activeTab === "virtual"
                  ? "bg-neon/15 text-neon border-neon shadow-md"
                  : "bg-white/5 text-gray-400 border-white/10 hover:text-white hover:bg-white/10"
              }`}
            >
              Virtual Target
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("markings")}
              className={`py-2.5 text-center font-mono text-xs uppercase font-bold tracking-wider rounded-lg transition border ${
                activeTab === "markings"
                  ? "bg-neon/15 text-neon border-neon shadow-md"
                  : "bg-white/5 text-gray-400 border-white/10 hover:text-white hover:bg-white/10"
              }`}
            >
              Real Image
            </button>
          </div>

          {/* Sub-header row with Ping camera and marks controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 w-full mb-3">
            <button
              type="button"
              onClick={handlePingCamera}
              disabled={pingCooldown > 0}
              className={`flex items-center gap-2 px-3 py-1.5 bg-white/3 hover:bg-white/5 border rounded-lg text-xs font-mono font-bold transition duration-150 disabled:opacity-40 disabled:cursor-not-allowed ${
                cameraOnline || isCameraActive
                  ? "text-emerald-400 border-emerald-500/30 hover:border-emerald-500/50"
                  : "text-red-400 border-red-500/30 hover:border-red-500/50"
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${cameraOnline || isCameraActive ? "bg-emerald-400 animate-pulse neon-glow" : "bg-red-400"}`} />
              <span>PING CAMERA {pingCooldown > 0 ? `(${pingCooldown}s)` : ""}</span>
            </button>

            {/* Action Controls (Marks visibility, candidates list, clear) */}
            <div className="flex items-center gap-2">
              {activeTab === "markings" && activeSession && userRole !== "shooter" && !selectedShooter && (
                <button
                  type="button"
                  onClick={() => setShowCandidates(!showCandidates)}
                  className={`flex items-center gap-1 px-2 py-1 rounded border transition text-[10px] font-mono font-bold uppercase ${
                    showCandidates
                      ? "bg-amber-950/40 border-amber-500/30 text-amber-400"
                      : "bg-white/2 border-white/5 text-gray-400 hover:text-white"
                  }`}
                  title="Toggle candidate proposals"
                >
                  <span>{showCandidates ? "Hide Cand." : "Show Cand."}</span>
                </button>
              )}

              
              {(activeTab === "markings" || activeTab === "virtual") && (
                <button
                  type="button"
                  onClick={() => setShowMarkings(!showMarkings)}
                  className={`flex items-center gap-1 px-2 py-1 rounded border transition text-[10px] font-mono font-bold uppercase ${
                    showMarkings
                      ? "bg-emerald-950/40 border-emerald-500/20 text-emerald-400"
                      : "bg-white/2 border-white/5 text-gray-400 hover:text-white"
                  }`}
                  title="Toggle markings overlay"
                >
                  <span>{showMarkings ? "Hide Marks" : "Show Marks"}</span>
                </button>
              )}

              <button
                type="button"
                onClick={triggerResize}
                className="p-1.5 rounded bg-white/2 border border-white/5 text-gray-400 hover:text-white transition"
                title="Recenter View"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="flex justify-between items-center w-full mb-4">
            <div className="flex items-center gap-2">
              <Crosshair className="w-5 h-5 text-neon" />
              <h3 className="text-base font-bold font-mono tracking-wider uppercase">Live Target Visualizer</h3>
            </div>
            <div className="flex gap-2">
              {activeTab === "markings" && activeSession && (
                <button
                  type="button"
                  onClick={() => setShowCandidates(!showCandidates)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded border transition text-xs font-mono ${
                    showCandidates
                      ? "bg-amber-950/40 border-amber-500/30 text-amber-400 hover:bg-amber-900/40"
                      : "bg-white/5 border-white/5 hover:bg-white/10 text-gray-400 hover:text-white"
                  }`}
                  title="Toggle showing candidate proposals (classical CV)"
                >
                  <span>{showCandidates ? "HIDE CANDIDATES" : "SHOW CANDIDATES"}</span>
                </button>
              )}
              {activeSession && shots.length > 0 && userRole === "technician" && (
                <button
                  type="button"
                  onClick={handleClearShots}
                  disabled={isClearing}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-red-950/40 border border-red-500/20 hover:bg-red-900/40 transition text-red-400 hover:text-red-300 text-xs font-mono"
                  title="Clear all shot markings"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>CLEAR MARKS</span>
                </button>
              )}
              {(activeTab === "markings" || activeTab === "virtual") && (
                <button
                  type="button"
                  onClick={() => setShowMarkings(!showMarkings)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded border transition text-xs font-mono ${
                    showMarkings
                      ? "bg-emerald-950/40 border-emerald-500/20 text-emerald-400 hover:bg-emerald-900/40 hover:text-emerald-300"
                      : "bg-white/5 border-white/10 text-gray-400 hover:bg-white/10 hover:text-white"
                  }`}
                  title={showMarkings ? "Hide markings overlay" : "Show markings overlay"}
                >
                  {showMarkings ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                  <span>{showMarkings ? "HIDE MARKS" : "SHOW MARKS"}</span>
                </button>
              )}
              <button type="button" onClick={triggerResize} className="p-1.5 rounded bg-white/5 border border-white/5 hover:bg-white/10 transition text-gray-400 hover:text-white" title="Recenter View">
                <Maximize2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Dev Pipeline Verification Tabs */}
          <div className="flex w-full border-b border-white/5 mb-4 gap-1">
            <button
              type="button"
              onClick={() => setActiveTab("markings")}
              className={`flex-1 py-1.5 text-center font-mono text-[10px] uppercase font-bold tracking-wider transition border-b-2 ${
                activeTab === "markings"
                  ? "text-neon border-neon bg-white/2"
                  : "text-gray-500 hover:text-gray-300 border-transparent"
              }`}
            >
              Real Image
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("calibration")}
              disabled={!activeSession}
              className={`flex-1 py-1.5 text-center font-mono text-[10px] uppercase font-bold tracking-wider transition border-b-2 ${
                !activeSession ? "opacity-30 cursor-not-allowed border-transparent" : ""
              } ${
                activeTab === "calibration"
                  ? "text-neon border-neon bg-white/2"
                  : "text-gray-500 hover:text-gray-300 border-transparent"
              }`}
            >
              Calibration
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("rectified")}
              disabled={!activeSession}
              className={`flex-1 py-1.5 text-center font-mono text-[10px] uppercase font-bold tracking-wider transition border-b-2 ${
                !activeSession ? "opacity-30 cursor-not-allowed border-transparent" : ""
              } ${
                activeTab === "rectified"
                  ? "text-neon border-neon bg-white/2"
                  : "text-gray-500 hover:text-gray-300 border-transparent"
              }`}
            >
              Adjusted View
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("virtual")}
              disabled={!activeSession}
              className={`flex-1 py-1.5 text-center font-mono text-[10px] uppercase font-bold tracking-wider transition border-b-2 ${
                !activeSession ? "opacity-30 cursor-not-allowed border-transparent" : ""
              } ${
                activeTab === "virtual"
                  ? "text-neon border-neon bg-white/2"
                  : "text-gray-500 hover:text-gray-300 border-transparent"
              }`}
            >
              Virtual Target
            </button>
            {userRole === "technician" && (
              <>
                <button
                  type="button"
                  onClick={() => setActiveTab("alignment")}
                  disabled={!activeSession}
                  className={`flex-1 py-1.5 text-center font-mono text-[10px] uppercase font-bold tracking-wider transition border-b-2 ${
                    !activeSession ? "opacity-30 cursor-not-allowed border-transparent" : ""
                  } ${
                    activeTab === "alignment"
                      ? "text-neon border-neon bg-white/2"
                      : "text-gray-500 hover:text-gray-300 border-transparent"
                  }`}
                >
                  ORB Alignment
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("diff")}
                  disabled={!activeSession}
                  className={`flex-1 py-1.5 text-center font-mono text-[10px] uppercase font-bold tracking-wider transition border-b-2 ${
                    !activeSession ? "opacity-30 cursor-not-allowed border-transparent" : ""
                  } ${
                    activeTab === "diff"
                      ? "text-neon border-neon bg-white/2"
                      : "text-gray-500 hover:text-gray-300 border-transparent"
                  }`}
                >
                  Diff Binary Map
                </button>
              </>
            )}
          </div>
        </>
      )}

      <div className="relative border border-white/5 bg-[#030712] rounded-lg overflow-hidden flex items-center justify-center p-2 w-full">
        {/* Real Image, Virtual Target & Rectified View (Canvas) */}
        <div className={(activeTab === "markings" || activeTab === "virtual" || (activeTab === "rectified" && !rectifiedError && imgLoaded)) ? "block" : "hidden"}>
          <canvas
            ref={canvasRef}
            width={dimensions.width}
            height={dimensions.height}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            className="cursor-crosshair max-w-full"
          />
        </div>

        {/* Calibration Tab */}
        <div className={activeTab === "calibration" ? "block w-full h-full" : "hidden"}>
          <div className="relative flex items-center justify-center max-w-full" style={{ width: dimensions.width, height: dimensions.height }}>
            {!calibrationError && activeSession?.id ? (
              <img
                src={`${BACKEND_URL}/static/uploads/debug_calibration_${activeSession.id}.jpg?t=${debugRefreshKey}`}
                alt="Calibration Detections View"
                className="max-w-full max-h-full object-contain"
                onError={() => setCalibrationError(true)}
              />
            ) : (
              <div className="flex flex-col items-center justify-center p-6 text-center">
                <ShieldAlert className="w-8 h-8 text-amber-500 mb-2" />
                <h4 className="font-mono text-xs font-semibold text-white uppercase tracking-wider">No Calibration Bounding Boxes Image</h4>
                <p className="text-[10px] text-gray-400 mt-1 max-w-[240px]">
                  Calibrate the camera or upload a baseline image first to detect target corners and AprilTags.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Rectified View Fallback / Error */}
        {activeTab === "rectified" && (rectifiedError || !imgLoaded) && (
          <div className="flex flex-col items-center justify-center p-6 text-center" style={{ width: dimensions.width, height: dimensions.height }}>
            <ShieldAlert className="w-8 h-8 text-amber-500 mb-2" />
            <h4 className="font-mono text-xs font-semibold text-white uppercase tracking-wider">No Adjusted View</h4>
            <p className="text-[10px] text-gray-400 mt-1 max-w-[240px]">
              Calibrate the target or run detection to generate the flat perspective-rectified view.
            </p>
          </div>
        )}

        {/* Alignment Tab */}
        <div className={activeTab === "alignment" ? "block w-full h-full" : "hidden"}>
          <div className="relative flex items-center justify-center max-w-full" style={{ width: dimensions.width, height: dimensions.height }}>
            {!alignmentError && activeSession?.id ? (
              <img
                src={`${BACKEND_URL}/static/uploads/debug_aligned_${activeSession.id}.png?t=${debugRefreshKey}`}
                alt="ORB Alignment Frame"
                className="max-w-full max-h-full object-contain"
                onError={() => setAlignmentError(true)}
              />
            ) : (
              <div className="flex flex-col items-center justify-center p-6 text-center">
                <ShieldAlert className="w-8 h-8 text-amber-500 mb-2" />
                <h4 className="font-mono text-xs font-semibold text-white uppercase tracking-wider">No Alignment Frame</h4>
                <p className="text-[10px] text-gray-400 mt-1 max-w-[240px]">
                  Trigger a shot or run impact analysis to generate the ORB alignment view.
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Diff Binary Map Tab */}
        <div className={activeTab === "diff" ? "block w-full h-full" : "hidden"}>
          <div className="relative flex items-center justify-center max-w-full" style={{ width: dimensions.width, height: dimensions.height }}>
            {!diffError && activeSession?.id ? (
              <img
                src={`${BACKEND_URL}/static/uploads/debug_diff_${activeSession.id}.png?t=${debugRefreshKey}`}
                alt="Binary Difference Map"
                className="max-w-full max-h-full object-contain"
                onError={() => setDiffError(true)}
              />
            ) : (
              <div className="flex flex-col items-center justify-center p-6 text-center">
                <ShieldAlert className="w-8 h-8 text-amber-500 mb-2" />
                <h4 className="font-mono text-xs font-semibold text-white uppercase tracking-wider">No Difference Map</h4>
                <p className="text-[10px] text-gray-400 mt-1 max-w-[240px]">
                  Trigger a shot or run impact analysis to generate the binary diff view.
                </p>
              </div>
            )}
          </div>
        </div>

        {(activeTab === "markings" || activeTab === "virtual") && !baselineUrl && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm p-6 text-center">
            <ShieldAlert className="w-10 h-10 text-amber-500 mb-3" />
            <h4 className="font-mono text-sm font-semibold text-white uppercase tracking-wider">Baseline Required</h4>
            <p className="text-xs text-gray-400 mt-1 max-w-[280px]">
              Upload a baseline camera frame image first to calibrate the camera differencing engine.
            </p>
          </div>
        )}
      </div>

      <div className="w-full flex justify-between items-center text-[10px] text-gray-500 font-mono mt-4">
        <span>RESOLUTION: {imageRef.current ? `${imageRef.current.naturalWidth}x${imageRef.current.naturalHeight}px` : "N/A"}</span>
        <span>SCALE: {imageRef.current ? `${(scaleRef.current * 100).toFixed(1)}%` : "1:1"}</span>
      </div>
    </div>
  );
}
