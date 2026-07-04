"use client";
import { BACKEND_URL, WS_URL } from "@/config";

import React, { useEffect, useState, useRef } from "react";
import { useStore, Shot, Session, Candidate } from "@/store/useStore";
import OverviewCards from "@/components/dashboard/OverviewCards";
import LiveTargetView from "@/components/dashboard/LiveTargetView";
import ShotTable from "@/components/dashboard/ShotTable";
import StatsPanel from "@/components/dashboard/StatsPanel";
import ConnectionStatus from "@/components/dashboard/ConnectionStatus";
import TargetPreview from "@/components/dashboard/TargetPreview";
import ToastHost, { ToastItem, ToastVariant } from "@/components/dashboard/ToastHost";
import { playCaptureSound, playSuccessSound, playNeutralSound, playErrorSound } from "@/lib/sound";
import { PlusCircle, Upload, Play, Terminal, CircleCheck, AlertTriangle, Trash, Users, ShieldAlert, Eye, Camera, Flame, Menu, X, Download } from "lucide-react";

export default function DashboardPage() {
  const {
    activeSession,
    setActiveSession,
    setWsStatus,
    setShots,
    shots,
    addShot,
    setStatistics,
    setBaselineUrl,
    baselineUrl,
    setCurrentFrameUrl,
    setTargetDefinition,
    candidates,
    setCandidates,
    userRole,
    setUserRole,
    updateShot
  } = useStore();

  const [activeShooterCandidate, setActiveShooterCandidate] = useState<any | null>(null);
  const [instructorTab, setInstructorTab] = useState<"session" | "review">("session");
  const [reviewShots, setReviewShots] = useState<Shot[]>([]);
  const [activeUnitShooters, setActiveUnitShooters] = useState<any[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);

  // Toast + sound alert system (ported from CXR-AIM).
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const dismissToast = (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id));
  const notify = (variant: ToastVariant, title: string, message?: string) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((prev) => [...prev, { id, variant, title, message }]);
    if (variant === "success") playSuccessSound();
    else if (variant === "error") playErrorSound();
    else if (variant === "capture") playCaptureSound();
    else playNeutralSound();
  };

  // Download the full session (shots, scores, positions, angles, timestamps) as JSON.
  const handleExportSession = async () => {
    if (!activeSession) return;
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/sessions/${activeSession.id}/export`);
      if (!res.ok) { notify("error", "Export Failed", "Could not export session data."); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `session_${(activeSession.name || activeSession.id).replace(/\s+/g, "_")}_${activeSession.id.slice(0, 8)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      addLog("📦 Session data exported as JSON.");
      notify("success", "Session Exported", "Shot data downloaded as JSON.");
    } catch {
      notify("error", "Export Failed", "Could not reach the backend.");
    }
  };

  useEffect(() => {
    const fetchShooters = async () => {
      if (!activeSession?.unit_number) {
        setActiveUnitShooters([]);
        return;
      }
      try {
        const res = await fetch(`${BACKEND_URL}/api/v1/units/${activeSession.unit_number}/shooters`);
        if (res.ok) {
          const data = await res.json();
          setActiveUnitShooters(data);
        } else {
          setActiveUnitShooters(getUnitCandidates(activeSession.unit_number));
        }
      } catch (err) {
        console.error("Failed to fetch unit shooters, using mock:", err);
        setActiveUnitShooters(getUnitCandidates(activeSession.unit_number));
      }
    };
    fetchShooters();
  }, [activeSession?.unit_number]);

  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      addLog(`Uploading shooters CSV "${file.name}"...`);
      const res = await fetch(`${BACKEND_URL}/api/v1/units/upload-csv`, {
        method: "POST",
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        addLog(`Import success: ${data.message}`);
        alert(data.message);
        
        if (activeSession?.unit_number && data.units.includes(activeSession.unit_number)) {
          const shooterRes = await fetch(`${BACKEND_URL}/api/v1/units/${activeSession.unit_number}/shooters`);
          if (shooterRes.ok) {
            const shooterData = await shooterRes.json();
            setActiveUnitShooters(shooterData);
          }
        }
      } else {
        const errData = await res.json();
        addLog(`CSV Import failed: ${errData.detail || "Unknown error"}`);
        alert(`CSV Import failed: ${errData.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Failed to upload CSV:", err);
      addLog(`CSV Import error: Connection failed`);
      alert("CSV Import error: Connection failed");
    } finally {
      e.target.value = "";
    }
  };

  // Helper for weapon type display
  const getWeaponType = (caliber: number | undefined | null): string => {
    if (!caliber) return "N/A";
    if (caliber === 5.56) return "Rifle (5.56mm)";
    if (caliber === 7.62) return "Rifle (7.62mm)";
    if (caliber === 9) return "Pistol (9mm)";
    return `${caliber}mm`;
  };

  // Helper for target number extraction
  const getTargetNumber = (shooter: any | null | undefined): string => {
    if (!shooter) return "All";
    const sId = (shooter.shooter_id || shooter.id || "").toString();
    if (sId.endsWith("-01") || sId.endsWith("-A") || sId.endsWith("01") || sId.endsWith("A")) return "1";
    if (sId.endsWith("-02") || sId.endsWith("-B") || sId.endsWith("02") || sId.endsWith("B")) return "2";
    if (sId.endsWith("-03") || sId.endsWith("-C") || sId.endsWith("03") || sId.endsWith("C")) return "3";
    
    // Dynamic matching of trailing number/letter
    const match = sId.match(/(\\d+|[A-Z])$/i);
    if (match) {
      const val = match[1];
      if (val === "1" || val.toUpperCase() === "A") return "1";
      if (val === "2" || val.toUpperCase() === "B") return "2";
      if (val === "3" || val.toUpperCase() === "C") return "3";
      return val;
    }
    return "All";
  };

  // Mobile stats configuration loading from localStorage
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
      } catch (e) {}
    }
    if (savedMultiplier) {
      setScoreMultiplier(parseFloat(savedMultiplier) || 1.0);
    }
  }, [shots]);

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

  const getShooterShotsMobile = () => {
    if (!activeSession) return [];
    const actualShots = (() => {
      if (!activeShooterCandidate) return shots;
      const targetNum = getTargetNumber(activeShooterCandidate);
      if (targetNum === "1") {
        return shots.filter(s => s.shot_number % 3 === 1);
      } else if (targetNum === "2") {
        return shots.filter(s => s.shot_number % 3 === 2);
      } else if (targetNum === "3") {
        return shots.filter(s => s.shot_number % 3 === 0);
      }
      return shots;
    })();

    if (actualShots.length === 0 && (userRole === "shooter" || activeShooterCandidate !== null)) {
      return getMockShooterShots(activeSession.id, activeSession.bullet_caliber);
    }
    return actualShots;
  };

  const mobileShots = getShooterShotsMobile();
  const mobileValidShots = mobileShots.filter((s) => s.is_valid);
  const mobileMissedShots = mobileValidShots.filter(
    (s) => s.score === 0 || s.score === null || s.score === undefined
  ).length;

  const getMobileGroupingDistanceMm = (): number => {
    if (mobileValidShots.length < 2) return 0;
    let maxDist = 0;
    for (let i = 0; i < mobileValidShots.length; i++) {
      for (let j = i + 1; j < mobileValidShots.length; j++) {
        const dx = (mobileValidShots[i].x_calibrated || 0) - (mobileValidShots[j].x_calibrated || 0);
        const dy = (mobileValidShots[i].y_calibrated || 0) - (mobileValidShots[j].y_calibrated || 0);
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > maxDist) {
          maxDist = dist;
        }
      }
    }
    return maxDist;
  };

  const mobileGroupingMm = getMobileGroupingDistanceMm();
  const mobileGroupingInches = mobileGroupingMm / 25.4;

  const getMobileAllocatedPoints = (zoneScore: number | null | undefined): number => {
    if (zoneScore === null || zoneScore === undefined) return 0;
    const basePoints = pointAllocations[zoneScore] !== undefined ? pointAllocations[zoneScore] : zoneScore;
    return parseFloat((basePoints * scoreMultiplier).toFixed(2));
  };

  const mobileTotalScore = mobileValidShots.reduce(
    (sum, s) => sum + getMobileAllocatedPoints(s.score),
    0
  );



  const getUnitCandidates = (unitNumber: string | null) => {
    if (!unitNumber) return [];
    const normalized = unitNumber.trim();
    return [
      { id: `${normalized}-01`, name: `Shooter ${normalized}-A`, status: "Active" },
      { id: `${normalized}-02`, name: `Shooter ${normalized}-B`, status: "Ready" },
      { id: `${normalized}-03`, name: `Shooter ${normalized}-C`, status: "Pending" },
    ];
  };

  const fetchReviewShots = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/shots/review`);
      if (res.ok) {
        const data = await res.json();
        setReviewShots(data);
      }
    } catch (err) {
      console.error("Failed to fetch review shots:", err);
    }
  };

  const handleApproveReviewShot = async (shot: Shot) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/shots/${shot.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ boundary_status: "certain" })
      });
      if (res.ok) {
        addLog(`Approved shot #${shot.shot_number} from session "${shot.session_id.slice(0, 8)}..."`);
        fetchReviewShots();
        if (activeSession && shot.session_id === activeSession.id) {
          setShots(shots.map(s => s.id === shot.id ? { ...s, boundary_status: "certain" } : s));
        }
      }
    } catch (err) {
      console.error("Failed to approve shot:", err);
    }
  };

  const handleExcludeReviewShot = async (shot: Shot) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/shots/${shot.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_valid: false, boundary_status: "certain" })
      });
      if (res.ok) {
        addLog(`Excluded shot #${shot.shot_number} from session "${shot.session_id.slice(0, 8)}..."`);
        fetchReviewShots();
        if (activeSession && shot.session_id === activeSession.id) {
          setShots(shots.map(s => s.id === shot.id ? { ...s, is_valid: false, boundary_status: "certain" } : s));
        }
      }
    } catch (err) {
      console.error("Failed to exclude shot:", err);
    }
  };

  const handleViewReviewShot = async (shot: Shot) => {
    try {
      if (activeSession && shot.session_id === activeSession.id) {
        const unitCand = getUnitCandidates(activeSession.unit_number);
        setActiveShooterCandidate(unitCand[0] || { id: "T-01", name: "Shooter Alpha" });
        setInstructorTab("session");
      } else {
        addLog(`Warning: Shot #${shot.shot_number} belongs to session ${shot.session_id.slice(0, 8)} which is not currently active.`);
        setActiveShooterCandidate({ id: "T-Review", name: `Shooter Review (${shot.session_id.slice(0, 8)})` });
      }
    } catch (err) {
      console.error("Failed to view review shot:", err);
    }
  };

  useEffect(() => {
    if (userRole === "instructor") {
      fetchReviewShots();
    }
  }, [userRole, instructorTab, shots.length]);

  const [newSessionName, setNewSessionName] = useState("");
  const [newSessionTargetType, setNewSessionTargetType] = useState("figure_eleven");
  const [newSessionBulletCaliber, setNewSessionBulletCaliber] = useState(5.56);
  const [newSessionRange, setNewSessionRange] = useState("100m");
  const [newSessionDrillType, setNewSessionDrillType] = useState("stationary");
  const [newSessionBulletsPerDrill, setNewSessionBulletsPerDrill] = useState<number>(5);
  const [newSessionUnitNumber, setNewSessionUnitNumber] = useState("");
  const [newSessionDate, setNewSessionDate] = useState("");
  const [targetDefinitions, setTargetDefinitions] = useState<any[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // New Session Creation Wizard states
  const [setupStep, setSetupStep] = useState<1 | 2 | 3>(1);
  const [createdSessionId, setCreatedSessionId] = useState<string | null>(null);
  const [createdUnitNumber, setCreatedUnitNumber] = useState<string | null>(null);
  const [unitPersonnel, setUnitPersonnel] = useState<{ id: string; name: string }[]>([]);
  const [laneAssignments, setLaneAssignments] = useState<{ [lane: number]: { id: string; name: string } }>({});
  const [availableShootersSearch, setAvailableShootersSearch] = useState("");
  const [assigningLane, setAssigningLane] = useState<number | null>(null);
  const [isSavingAssignments, setIsSavingAssignments] = useState(false);
  const [aiVerifierEnabled, setAiVerifierEnabled] = useState(false);
  const [sessionDetailsTab, setSessionDetailsTab] = useState<"shots" | "candidates" | "stats">("stats");
  const [showCameraControls, setShowCameraControls] = useState(false);
  
  // Custom Target creation states
  const [showCreateTargetModal, setShowCreateTargetModal] = useState(false);
  const [customTargetName, setCustomTargetName] = useState("");
  const [customTargetWidth, setCustomTargetWidth] = useState(80.0);
  const [customTargetHeight, setCustomTargetHeight] = useState(80.0);
  const [customTargetDecimalScoring, setCustomTargetDecimalScoring] = useState(true);
  const [customTargetRingSpacing, setCustomTargetRingSpacing] = useState(2.5);
  const [customTargetCalibers, setCustomTargetCalibers] = useState<string[]>(["5.56", "7.62", "9.0"]);
  const [customTargetRings, setCustomTargetRings] = useState<{ value: number; outer_radius_mm: number }[]>([
    { value: 10, outer_radius_mm: 2.5 },
    { value: 9, outer_radius_mm: 5.0 },
    { value: 8, outer_radius_mm: 7.5 },
    { value: 7, outer_radius_mm: 10.0 },
    { value: 6, outer_radius_mm: 12.5 },
    { value: 5, outer_radius_mm: 15.0 },
    { value: 4, outer_radius_mm: 17.5 },
    { value: 3, outer_radius_mm: 20.0 },
    { value: 2, outer_radius_mm: 22.5 },
    { value: 1, outer_radius_mm: 25.0 }
  ]);
  const [customTargetPreviewBase64, setCustomTargetPreviewBase64] = useState<string | null>(null);
  const [customTargetType, setCustomTargetType] = useState<"circular" | "rectangular">("rectangular");
  const [customTargetTagSizeMm, setCustomTargetTagSizeMm] = useState(50.0);
  const [customTargetTagMarginMm, setCustomTargetTagMarginMm] = useState(20.0);
  const [customTargetRegions, setCustomTargetRegions] = useState<{ id: number; name: string; value: number; x_min_mm: number; y_min_mm: number; x_max_mm: number; y_max_mm: number }[]>([
    { id: 1, name: "Outer Torso", value: 4, x_min_mm: 40.0, y_min_mm: 42.5, x_max_mm: 540.0, y_max_mm: 842.5 },
    { id: 2, name: "Inner Center", value: 5, x_min_mm: 190.0, y_min_mm: 292.5, x_max_mm: 390.0, y_max_mm: 592.5 }
  ]);
  const [isDraggingCenter, setIsDraggingCenter] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ x: number; y: number } | null>(null);
  const [circularCenterMm, setCircularCenterMm] = useState<{ x: number; y: number }>({ x: 40.0, y: 40.0 });
  const [hoverMm, setHoverMm] = useState<{ x: number; y: number } | null>(null);
  const [selectedZoneId, setSelectedZoneId] = useState<number | null>(null);
  const [selectedRingIdx, setSelectedRingIdx] = useState<number | null>(null);

  const [isUploadingBaseline, setIsUploadingBaseline] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  
  // Camera Integration states
  const [cameraSource, setCameraSource] = useState("0");
  const [cameraResolution, setCameraResolution] = useState("native");
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [showTagFeed, setShowTagFeed] = useState(false);
  const [isCalibrating, setIsCalibrating] = useState(false);
  const [zoomFactor, setZoomFactor] = useState(1.0);
  const [isCapturingBeforeFire, setIsCapturingBeforeFire] = useState(false);
  const [cameraOnline, setCameraOnline] = useState(false);
  const [pingCooldown, setPingCooldown] = useState(0);

  const checkCameraStatus = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/camera/ping`);
      if (res.ok) {
        const data = await res.json();
        setCameraOnline(data.online);
        setIsCameraActive(data.online);
      }
    } catch {
      // Transient during backend startup; this polls, so just reflect offline.
      setCameraOnline(false);
      setIsCameraActive(false);
    }
  };

  const handlePingCamera = async () => {
    if (pingCooldown > 0) return;
    await checkCameraStatus();
    setPingCooldown(15);
  };

  // Cooldown timer effect
  useEffect(() => {
    if (pingCooldown <= 0) return;
    const timer = setInterval(() => {
      setPingCooldown((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [pingCooldown]);

  // Initial status check
  useEffect(() => {
    checkCameraStatus();
  }, [isCameraActive]);


  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  // Helper to append log lines
  const addLog = (message: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs((prev) => [`[${time}] ${message}`, ...prev.slice(0, 20)]);
  };

  const withCacheBuster = (filePath: string) => {
    const separator = filePath.includes("?") ? "&" : "?";
    return `${filePath}${separator}v=${Date.now()}`;
  };

  // Fetch target config details
  const fetchTargetDefinition = async (targetType: string) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/targets/${targetType}`);
      if (res.ok) {
        const data = await res.json();
        setTargetDefinition(data);
      }
    } catch (e) {
      console.error("Failed to load target definition", e);
    }
  };

  useEffect(() => {
    setCircularCenterMm({
      x: customTargetWidth / 2,
      y: customTargetHeight / 2
    });
  }, [customTargetWidth, customTargetHeight]);

  // Load target definitions list and active session on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const roleParam = params.get("role");
      if (roleParam === "shooter" || roleParam === "instructor" || roleParam === "technician") {
        setUserRole(roleParam);
      }
    }

    const now = new Date();
    const tzOffset = now.getTimezoneOffset() * 60000;
    setNewSessionDate(new Date(now.getTime() - tzOffset).toISOString().slice(0, 16));

    async function loadTargets() {
      try {
        const res = await fetch(`${BACKEND_URL}/api/v1/targets`);
        if (res.ok) {
          const data = await res.json();
          setTargetDefinitions(data);
        }
      } catch (err) {
        console.error("Failed to load target definitions:", err);
      }
    }

    async function loadAiVerifierStatus() {
      try {
        const res = await fetch(`${BACKEND_URL}/api/v1/config/ai-verifier`);
        if (res.ok) {
          const data = await res.json();
          setAiVerifierEnabled(data.enabled);
        }
      } catch (err) {
        console.error("Failed to load AI verifier status:", err);
      }
    }

    // The backend can take a few seconds to come up (CUDA/torch + model load). Wait until it's
    // reachable before the initial loaders so we don't fail permanently on a cold start.
    async function waitForBackend(maxAttempts = 30): Promise<boolean> {
      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
          const ping = await fetch(`${BACKEND_URL}/api/v1/health`);
          if (ping.ok) return true;
        } catch {
          if (attempt === 1) addLog("Waiting for backend to come online…");
        }
        await new Promise((r) => setTimeout(r, 1200));
      }
      return false;
    }

    async function initSession() {
      addLog("Initializing Shooting Target Analysis Platform...");
      try {
        const res = await fetch(`${BACKEND_URL}/api/v1/sessions/active`);
        if (res.ok) {
          const session: Session = await res.json();
          if (session) {
            addLog(`Found active session: "${session.name}"`);
            setActiveSession(session);
            await fetchSessionDetails(session.id);
            await fetchTargetDefinition(session.target_type);
          } else {
            addLog("No active session detected. Awaiting configuration...");
          }
        }
      } catch (error) {
        addLog("Error connecting to backend API. Ensure Uvicorn server is running on port 8000.");
        console.error("Session init failed:", error);
      }
    }

    (async () => {
      const online = await waitForBackend();
      if (!online) {
        addLog("Backend not reachable on port 8000.");
        return;
      }
      await Promise.all([loadTargets(), loadAiVerifierStatus()]);
      await initSession();
    })();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, []);

  // 2. Fetch shots and image baseline info
  const fetchSessionDetails = async (sessionId: string) => {
    try {
      // Fetch shots
      const shotsRes = await fetch(`${BACKEND_URL}/api/v1/sessions/${sessionId}/shots`);
      if (shotsRes.ok) {
        const shotsData: Shot[] = await shotsRes.json();
        setShots(shotsData);
        addLog(`Loaded ${shotsData.length} existing shots for this session.`);
      }

      // Fetch statistics
      const statsRes = await fetch(`${BACKEND_URL}/api/v1/sessions/${sessionId}/statistics`);
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStatistics(statsData);
      }

      // Check if baseline exists on backend
      const baselineRes = await fetch(`${BACKEND_URL}/api/v1/sessions/${sessionId}/baseline`);
      if (baselineRes.ok) {
        const baselineData = await baselineRes.json();
        if (baselineData && baselineData.file_path) {
          setBaselineUrl(withCacheBuster(baselineData.file_path));
          addLog("Loaded existing target baseline calibration.");
        } else {
          setBaselineUrl(null);
          addLog("No baseline calibration found. Connect camera and calibrate target.");
        }
      } else {
        setBaselineUrl(null);
      }
    } catch (e) {
      console.error("Failed to load session details", e);
    }
  };

  useEffect(() => {
    if (userRole === "shooter" || activeShooterCandidate !== null) {
      if (sessionDetailsTab === "candidates") {
        setSessionDetailsTab("stats");
      }
    }
  }, [userRole, activeShooterCandidate, sessionDetailsTab]);

  // 3. Connect to WebSockets
  useEffect(() => {
    if (!activeSession) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return;
    }

    const connectWebSocket = () => {
      setWsStatus("connecting");
      addLog(`Connecting WebSocket subscription for session ${activeSession.id.slice(0, 8)}...`);

      const ws = new WebSocket(`${WS_URL}/ws/session/${activeSession.id}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus("connected");
        addLog("WebSocket link established. Awaiting live trigger events...");
      };

      ws.onmessage = (event) => {
        try {
          // Check if heartbeat echo
          if (event.data.startsWith("heartbeat")) return;

          const payload = JSON.parse(event.data);
          if (payload.event === "SHOT_DETECTED") {
            const newShot: Shot = payload.data;
            addShot(newShot);
            const scoreStr = newShot.score !== undefined && newShot.score !== null ? `Score: ${newShot.score} (Decimal: ${newShot.decimal_score?.toFixed(1) || '0.0'})` : `at (${newShot.x_raw.toFixed(1)}, ${newShot.y_raw.toFixed(1)})`;
            addLog(`LIVE TELEMETRY: Shot #${newShot.shot_number} detected. ${scoreStr} (confidence ${(newShot.confidence * 100).toFixed(0)}%)`);
            notify("capture", `Shot #${newShot.shot_number} Detected`, scoreStr);
          } else if (payload.event === "CANDIDATES_DETECTED") {
            const newCandidates: Candidate[] = payload.data;
            setCandidates(newCandidates);
            addLog(`LIVE TELEMETRY: Resolved ${newCandidates.length} classical CV candidate proposals.`);
          } else if (payload.event === "BASELINE_UPLOADED") {
            setBaselineUrl(withCacheBuster(payload.data.file_path));
            setCurrentFrameUrl(null);
            if (payload.data.method === "fallback") {
              addLog("⚠️ LIVE TELEMETRY: Baseline updated via fallback center-crop (corners not detected).");
              notify("info", "Baseline Captured", "Center-crop fallback — add AprilTags for accurate zones.");
            } else {
              addLog("LIVE TELEMETRY: Baseline target calibration completed successfully.");
              notify("capture", "Baseline Calibrated", "Target locked & calibrated.");
            }
          } else if (payload.event === "SHOTS_CLEARED") {
            setShots([]);
            setCandidates([]);
            setStatistics({
              total_shots: 0,
              average_diameter_px: 0.0,
              largest_diameter_px: 0.0,
              smallest_diameter_px: 0.0,
              last_shot_time: null,
              session_status: activeSession ? activeSession.status : "active",
              camera_status: "online"
            });
            addLog("LIVE TELEMETRY: All shot markings cleared from this session.");
          } else if (payload.event === "SHOT_UPDATED") {
            const updatedShot: Shot = payload.data;
            updateShot(updatedShot);
            addLog(`LIVE TELEMETRY: Shot #${updatedShot.shot_number} updated status.`);
          } else if (payload.event === "FRAME_UPDATED") {
            setCurrentFrameUrl(withCacheBuster(payload.data.current_frame_url));
          }
        } catch (e) {
          console.error("Failed to parse websocket message", e);
        }
      };

      ws.onclose = () => {
        setWsStatus("disconnected");
        addLog("WebSocket disconnected. Retrying connection in 5 seconds...");
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connectWebSocket();
        }, 5000);
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        ws.close();
      };
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect callbacks
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [activeSession]);

  // 4. API Event: Create Session
  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSessionName.trim()) return;

    try {
      addLog(`Creating session "${newSessionName}"...`);
      const res = await fetch(`${BACKEND_URL}/api/v1/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          name: newSessionName, 
          target_type: newSessionTargetType,
          bullet_caliber: newSessionBulletCaliber,
          session_range: newSessionRange,
          drill_type: newSessionDrillType,
          bullets_per_drill: newSessionBulletsPerDrill,
          unit_number: newSessionUnitNumber,
          session_date: newSessionDate
        })
      });

      if (res.ok) {
        const session: Session = await res.json();
        setActiveSession(session);
        setShots([]);
        setCandidates([]);
        setBaselineUrl(null);
        setCurrentFrameUrl(null);
        await fetchTargetDefinition(session.target_type);
        setNewSessionName("");
        setNewSessionUnitNumber("");
        setNewSessionBulletsPerDrill(5);
        setNewSessionRange("100m");
        setNewSessionDrillType("stationary");
        // Reset date
        const now = new Date();
        const tzOffset = now.getTimezoneOffset() * 60000;
        setNewSessionDate(new Date(now.getTime() - tzOffset).toISOString().slice(0, 16));
        setShowCreateModal(false);
        addLog(`New session active: ${session.name} (Target: ${session.target_type}, Caliber: ${session.bullet_caliber}mm)`);
        // Force refresh stats
        setStatistics({
          total_shots: 0,
          average_diameter_px: 0.0,
          largest_diameter_px: 0.0,
          smallest_diameter_px: 0.0,
          last_shot_time: null,
          session_status: "active",
          camera_status: "online"
        });
      }
    } catch (error) {
      addLog("Failed to create new session.");
      console.error(error);
    }
  };

  const handleCreateSessionWizardStep1 = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSessionUnitNumber.trim()) return;

    try {
      addLog(`Creating draft session for Unit "${newSessionUnitNumber}"...`);
      
      const targetNameMap: { [key: string]: string } = {
        "figure_eleven": "Figure Eleven",
        "issf_10m_air_rifle": "ISSF 10m Air Rifle",
        "real_figure_11": "Real Figure 11"
      };
      const displayTargetName = targetNameMap[newSessionTargetType] || newSessionTargetType;

      const res = await fetch(`${BACKEND_URL}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          unitNumber: newSessionUnitNumber,
          targetType: displayTargetName,
          range: newSessionRange,
          drillType: newSessionDrillType,
          roundsPerShooter: newSessionBulletsPerDrill,
          caliber: newSessionBulletCaliber.toString(),
          sessionDate: newSessionDate ? newSessionDate.replace("T", " ") : undefined
        })
      });

      if (res.ok) {
        const data = await res.json();
        setCreatedSessionId(data.sessionId);
        setCreatedUnitNumber(data.unitNumber);
        addLog(`Session created: ${data.sessionId} for Unit ${data.unitNumber}.`);
        
        // Fetch unit personnel
        addLog(`Loading personnel for Unit ${data.unitNumber}...`);
        const personnelRes = await fetch(`${BACKEND_URL}/api/units/${data.unitNumber}/personnel`);
        if (personnelRes.ok) {
          const personnelData = await personnelRes.json();
          setUnitPersonnel(personnelData);
          addLog(`Loaded ${personnelData.length} personnel.`);
        } else {
          setUnitPersonnel([]);
        }
        
        // Clear old lane assignments
        setLaneAssignments({});
        setAvailableShootersSearch("");
        
        // Go to page 2
        setSetupStep(2);
      } else {
        const err = await res.json();
        alert(`Failed to create session: ${err.detail || "Unknown error"}`);
      }
    } catch (error) {
      addLog("Failed to connect to backend for session creation.");
      console.error(error);
      alert("Failed to connect to backend for session creation.");
    }
  };

  const handleStartSessionWizard = async () => {
    if (!createdSessionId) return;
    
    const assignedShooters = Object.entries(laneAssignments);
    if (assignedShooters.length < 1) {
      alert("Cannot start session. Minimum 1 assigned shooter is required.");
      return;
    }
    
    setIsSavingAssignments(true);
    try {
      addLog(`Saving lane assignments for session ${createdSessionId}...`);
      
      const payload = assignedShooters.map(([lane, shooter]) => ({
        lane: parseInt(lane),
        targetId: `T${parseInt(lane).toString().padStart(2, '0')}`,
        shooterId: shooter.id
      }));
      
      const saveRes = await fetch(`${BACKEND_URL}/api/sessions/${createdSessionId}/lane-assignments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      
      if (!saveRes.ok) {
        const err = await saveRes.json();
        alert(`Failed to save lane assignments: ${err.detail || "Unknown error"}`);
        setIsSavingAssignments(false);
        return;
      }
      
      addLog("Lane assignments saved successfully. Starting session...");
      
      const startRes = await fetch(`${BACKEND_URL}/api/sessions/${createdSessionId}/start`, {
        method: "POST"
      });
      
      if (startRes.ok) {
        addLog("Session started successfully!");
        
        const sessRes = await fetch(`${BACKEND_URL}/api/v1/sessions/active`);
        if (sessRes.ok) {
          const session = await sessRes.json();
          setActiveSession(session);
          setShots([]);
          setCandidates([]);
          setBaselineUrl(null);
          setCurrentFrameUrl(null);
          await fetchTargetDefinition(session.target_type);
          
          const shooterRes = await fetch(`${BACKEND_URL}/api/v1/units/${session.unit_number}/shooters`);
          if (shooterRes.ok) {
            const shooterData = await shooterRes.json();
            setActiveUnitShooters(shooterData);
          }
          
          setShowCreateModal(false);
          setSetupStep(1);
          setCreatedSessionId(null);
          setCreatedUnitNumber(null);
          setLaneAssignments({});
          
          setStatistics({
            total_shots: 0,
            average_diameter_px: 0.0,
            largest_diameter_px: 0.0,
            smallest_diameter_px: 0.0,
            last_shot_time: null,
            session_status: "active",
            camera_status: "online"
          });
        }
      } else {
        const err = await startRes.json();
        alert(`Failed to start session: ${err.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Error starting session:", err);
      alert("Connection error occurred while starting the session.");
    } finally {
      setIsSavingAssignments(false);
    }
  };

  // API Event: Create Target
  const handlePreviewImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onloadend = () => {
      setCustomTargetPreviewBase64(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleAddRing = () => {
    const nextValue = customTargetRings.length > 0 
      ? Math.min(...customTargetRings.map(r => r.value)) - 1
      : 10;
    const finalValue = Math.max(nextValue, 0);
    const nextRadius = customTargetRings.length > 0
      ? Math.max(...customTargetRings.map(r => r.outer_radius_mm)) + 2.5
      : 2.5;
    setCustomTargetRings([...customTargetRings, { value: finalValue, outer_radius_mm: nextRadius }]);
  };

  const handleRemoveRing = (index: number) => {
    setCustomTargetRings(customTargetRings.filter((_, i) => i !== index));
  };

  const handleRingChange = (index: number, field: "value" | "outer_radius_mm", val: number) => {
    const updated = customTargetRings.map((r, i) => {
      if (i === index) {
        return { ...r, [field]: val };
      }
      return r;
    });
    // Sort rings descending by radius
    updated.sort((a, b) => b.outer_radius_mm - a.outer_radius_mm);
    setCustomTargetRings(updated);
  };

  const handleAddRegion = () => {
    const nextId = customTargetRegions.length > 0 ? Math.max(...customTargetRegions.map(r => r.id)) + 1 : 1;
    setCustomTargetRegions([
      ...customTargetRegions,
      { id: nextId, name: `Zone ${nextId}`, value: 1, x_min_mm: 0, y_min_mm: 0, x_max_mm: 100, y_max_mm: 100 }
    ]);
  };

  const handleRemoveRegion = (id: number) => {
    setCustomTargetRegions(customTargetRegions.filter(r => r.id !== id));
  };

  const handleRegionChange = (id: number, field: string, val: any) => {
    setCustomTargetRegions(
      customTargetRegions.map(r => (r.id === id ? { ...r, [field]: val } : r))
    );
  };

  const handleCreateTarget = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customTargetName.trim()) return;

    const targetPayload = {
      name: customTargetName,
      width_mm: parseFloat(customTargetWidth.toString()) || 80.0,
      height_mm: parseFloat(customTargetHeight.toString()) || 80.0,
      bullet_compatibility: customTargetCalibers,
      decimal_scoring_supported: customTargetDecimalScoring,
      ring_spacing_mm: parseFloat(customTargetRingSpacing.toString()) || 2.5,
      tag_size_mm: parseFloat(customTargetTagSizeMm.toString()) || 50.0,
      tag_margin_mm: parseFloat(customTargetTagMarginMm.toString()) || 20.0,
      bullseyes: customTargetType === "circular" ? [
        {
          id: 1,
          center_x_mm: (parseFloat(customTargetWidth.toString()) || 80.0) / 2.0,
          center_y_mm: (parseFloat(customTargetHeight.toString()) || 80.0) / 2.0,
          scoring_rule: "inward",
          rings: customTargetRings.map(r => ({
            value: parseInt(r.value.toString()),
            outer_radius_mm: parseFloat(r.outer_radius_mm.toString())
          }))
        }
      ] : [],
      scoring_regions: customTargetType === "rectangular" ? customTargetRegions.map(r => ({
        id: r.id,
        name: r.name,
        value: parseInt(r.value.toString()),
        x_min_mm: parseFloat(r.x_min_mm.toString()),
        y_min_mm: parseFloat(r.y_min_mm.toString()),
        x_max_mm: parseFloat(r.x_max_mm.toString()),
        y_max_mm: parseFloat(r.y_max_mm.toString())
      })) : [],
      preview_image_base64: customTargetPreviewBase64
    };

    try {
      addLog(`Creating custom target "${customTargetName}"...`);
      const res = await fetch(`${BACKEND_URL}/api/v1/targets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(targetPayload)
      });

      if (res.ok) {
        addLog(`Custom target "${customTargetName}" successfully added.`);
        const targetsRes = await fetch(`${BACKEND_URL}/api/v1/targets`);
        if (targetsRes.ok) {
          const data = await targetsRes.json();
          setTargetDefinitions(data);
          const newTargetId = data.find((t: any) => t.name === customTargetName)?.id;
          if (newTargetId) {
            setNewSessionTargetType(newTargetId);
          }
        }
        
        setCustomTargetName("");
        setCustomTargetWidth(80.0);
        setCustomTargetHeight(80.0);
        setCustomTargetPreviewBase64(null);
        setShowCreateTargetModal(false);
      } else {
        const errData = await res.json();
        addLog(`Failed to add target: ${errData.detail || 'unknown error'}`);
      }
    } catch (error) {
      addLog("Failed to connect to target creation endpoint.");
      console.error(error);
    }
  };

  // 5. API Event: Upload Baseline Image
  const handleBaselineUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !activeSession) return;

    const file = files[0];
    const formData = new FormData();
    formData.append("file", file);

    setIsUploadingBaseline(true);
    addLog(`Uploading baseline target frame: "${file.name}"...`);

    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/sessions/${activeSession.id}/baseline`, {
        method: "POST",
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        // Extract static path
        setBaselineUrl(withCacheBuster(data.file_path));
        addLog("Baseline target registered successfully.");
      } else {
        addLog("Failed to register baseline target image.");
      }
    } catch (err) {
      addLog("Error uploading baseline.");
      console.error(err);
    } finally {
      setIsUploadingBaseline(false);
    }
  };

  // 6. API Event: Trigger Detection Frame
  const handleDetectUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !activeSession) return;
    if (!baselineUrl) {
      alert("Please upload a baseline target image before analyzing shooting frames.");
      return;
    }

    const file = files[0];
    const formData = new FormData();
    formData.append("file", file);

    setIsDetecting(true);
    addLog(`Ingesting capture frame: "${file.name}"...`);

    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/sessions/${activeSession.id}/detect`, {
        method: "POST",
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        addLog(`Analysis complete. Found ${data.new_shots_count} new bullet holes in frame.`);
        if (data.shots_detected && data.shots_detected.length > 0) {
          data.shots_detected.forEach((shot: Shot) => {
            addShot(shot);
          });
        }
        if (data.candidates_detected) {
          setCandidates(data.candidates_detected);
        }
        if (data.current_frame_url) {
          setCurrentFrameUrl(data.current_frame_url);
        }
      } else {
        const errorData = await res.json();
        addLog(`Error during CV detection: ${errorData.detail || "Server error"}`);
      }
    } catch (err) {
      addLog("Error running target detection pipeline.");
      console.error(err);
    } finally {
      setIsDetecting(false);
    }
  };

  // 7. API Event: Camera Controls
  const toggleCamera = async () => {
    if (!activeSession) return;
    if (isCameraActive) {
      try {
        addLog("Disconnecting camera source...");
        const res = await fetch(`${BACKEND_URL}/api/v1/camera/stop`, { method: "POST" });
        if (res.ok) {
          setIsCameraActive(false);
          addLog("Camera disconnected.");
        }
      } catch (err) {
        addLog("Failed to disconnect camera.");
      }
    } else {
      try {
        addLog(`Connecting camera source: "${cameraSource}"...`);
        let url = `${BACKEND_URL}/api/v1/camera/start?source=${encodeURIComponent(cameraSource)}`;
        if (cameraResolution !== "native") {
          const [w, h] = cameraResolution.split("x");
          url += `&width=${w}&height=${h}`;
        }
        const res = await fetch(url, { method: "POST" });
        if (res.ok) {
          setIsCameraActive(true);
          addLog(
            cameraResolution === "native"
              ? "Camera connected. Native high/maximum resolution feed active."
              : `Camera connected. Live feed active at ${cameraResolution}.`
          );
        } else {
          addLog("Failed to connect to camera. Check source index or URL.");
        }
      } catch (err) {
        addLog("Error starting camera service.");
      }
    }
  };

  const handleCalibrate = async (bypassAprilTag = false) => {
    if (!activeSession || !isCameraActive) return;
    setIsCalibrating(true);
    addLog(
      bypassAprilTag
        ? "Analyzing frame using Contour Detection ONLY (bypassing AprilTags)..."
        : "Analyzing frame for rectangular paper target. Calibrating homography..."
    );
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/camera/calibrate?session_id=${activeSession.id}&bypass_apriltag=${bypassAprilTag}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setBaselineUrl(withCacheBuster(data.file_path));
        setCurrentFrameUrl(null);
        if (data.method === "fallback") {
          addLog("⚠️ Calibration completed using fallback center-crop. (Paper corners not detected. Check lighting/contrast).");
        } else {
          addLog("Target calibration completed. Perspective rectified to 1000x1000 pixels.");
        }
      } else {
        const errorData = await res.json();
        addLog(`Calibration failed: ${errorData.detail || "Paper borders not detected"}`);
      }
    } catch (err) {
      addLog("Error executing target calibration.");
    } finally {
      setIsCalibrating(false);
    }
  };

  const handleBeforeFire = async () => {
    if (!activeSession || !isCameraActive) return;
    setIsCapturingBeforeFire(true);
    addLog("Capturing pristine baseline target frame (before fire)...");
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/camera/before_fire?session_id=${activeSession.id}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setBaselineUrl(withCacheBuster(data.file_path));
        setCurrentFrameUrl(null);
        if (data.method === "fallback") {
          addLog("📷 Pristine baseline target frame captured via fallback center-crop.");
        } else {
          addLog("📷 Pristine baseline target frame captured and registered (perspective rectified).");
        }
      } else {
        const errorData = await res.json();
        addLog(`Capture failed: ${errorData.detail || "Server error"}`);
      }
    } catch (err) {
      addLog("Error executing target baseline capture.");
    } finally {
      setIsCapturingBeforeFire(false);
    }
  };



  const handleZoomChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setZoomFactor(val);
    try {
      await fetch(`${BACKEND_URL}/api/v1/camera/zoom?factor=${val}`, { method: "POST" });
    } catch (err) {
      console.error("Failed to update camera zoom:", err);
    }
  };

  const handleFire = async () => {
    if (!activeSession || !isCameraActive || !baselineUrl) return;
    setIsDetecting(true);
    addLog("FIRED! Capturing camera frame and analyzing bullet hole impacts...");
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/camera/fire?session_id=${activeSession.id}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        addLog(`Analysis complete. Found ${data.new_shots_count} new bullet holes in frame.`);
        if (data.shots_detected && data.shots_detected.length > 0) {
          data.shots_detected.forEach((shot: Shot) => {
            addShot(shot);
          });
        }
        if (data.candidates_detected) {
          setCandidates(data.candidates_detected);
        }
        if (data.current_frame_url) {
          setCurrentFrameUrl(data.current_frame_url);
        }
      } else {
        const errorData = await res.json();
        addLog(`Analysis failed: ${errorData.detail || "Server error"}`);
      }
    } catch (err) {
      addLog("Error executing target detection pipeline.");
      console.error(err);
    } finally {
      setIsDetecting(false);
    }
  };

  const toggleAiVerifier = async () => {
    try {
      const nextVal = !aiVerifierEnabled;
      const res = await fetch(`${BACKEND_URL}/api/v1/config/ai-verifier?enabled=${nextVal}`, {
        method: "POST"
      });
      if (res.ok) {
        const data = await res.json();
        setAiVerifierEnabled(data.enabled);
        addLog(`SYSTEM CONFIG: YOLO AI Verification has been turned ${data.enabled ? "ON" : "OFF"}.`);
      }
    } catch (err) {
      addLog("Failed to update AI verifier configuration.");
      console.error(err);
    }
  };


  return (
    <main className="min-h-screen flex flex-col p-4 md:p-6 lg:p-8 space-y-6">
      <ToastHost toasts={toasts} onDone={dismissToast} />
      
      {/* Top Banner Header */}
      <header className="flex flex-col gap-4 border-b border-white/5 pb-4">
        <div className="flex flex-row justify-between items-center gap-4 w-full">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-neon animate-pulse neon-glow" />
              <h1 className="text-lg md:text-2xl font-bold font-mono tracking-wider uppercase text-white">
                PILSS Platform
              </h1>
              <span className="text-[9px] md:text-[10px] px-1.5 py-0.5 border border-white/10 rounded-full font-mono bg-white/5 text-gray-400">
                v1.0.0
              </span>
            </div>
            <p className="hidden md:block text-xs text-gray-500 font-mono mt-0.5">
              Precision-Impact-Localization-and-Scoring-System
            </p>
          </div>

          <div className="flex items-center gap-3">
            <ConnectionStatus />

            {/* Export session as JSON (ported from CXR-AIM) */}
            {activeSession && (userRole === "technician" || userRole === "instructor") && (
              <button
                onClick={handleExportSession}
                className="flex items-center gap-1.5 p-2 md:px-3 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white transition active:scale-95 shadow-md font-mono text-xs"
                aria-label="Export session as JSON"
                title="Export session data as JSON"
              >
                <Download className="w-4 h-4" />
                <span className="hidden md:inline">EXPORT</span>
              </button>
            )}

            {/* Hamburger Menu Controls */}
            <div className="relative font-mono">
              <button
                onClick={() => setMenuOpen(!menuOpen)}
                className="flex items-center justify-center p-2 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-gray-300 hover:text-white transition active:scale-95 shadow-md"
                aria-label="Toggle Controls Menu"
              >
                {menuOpen ? <X className="w-5 h-5 text-neon" /> : <Menu className="w-5 h-5" />}
              </button>

              {menuOpen && (
                <div className="glass-panel z-50 p-4 w-72 absolute right-0 top-11 flex flex-col gap-4 border border-white/10 shadow-2xl bg-[#080d1a]/95 backdrop-blur-md rounded-xl animate-fade-in font-mono">
                  
                  {/* Section 1: User Role Selection */}
                  <div className="flex flex-col gap-2">
                    <span className="text-[9px] uppercase text-gray-500 tracking-wider font-bold">Select User Role</span>
                    <div className="flex flex-col bg-[#030712] border border-white/5 rounded-lg p-1 gap-1">
                      <button
                        onClick={() => {
                          setUserRole("technician");
                          setMenuOpen(false);
                        }}
                        className={`px-3 py-2 rounded-md text-xs font-bold transition-all text-left flex justify-between items-center ${
                          userRole === "technician"
                            ? "bg-red-600 text-white shadow-md"
                            : "text-gray-400 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        <span>TECHNICIAN</span>
                        {userRole === "technician" && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
                      </button>
                      <button
                        onClick={() => {
                          setUserRole("instructor");
                          setMenuOpen(false);
                        }}
                        className={`px-3 py-2 rounded-md text-xs font-bold transition-all text-left flex justify-between items-center ${
                          userRole === "instructor"
                            ? "bg-blue-600 text-white shadow-md"
                            : "text-gray-400 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        <span>INSTRUCTOR</span>
                        {userRole === "instructor" && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
                      </button>
                      <button
                        onClick={() => {
                          setUserRole("shooter");
                          setMenuOpen(false);
                        }}
                        className={`px-3 py-2 rounded-md text-xs font-bold transition-all text-left flex justify-between items-center ${
                          userRole === "shooter"
                            ? "bg-emerald-600 text-white shadow-md"
                            : "text-gray-400 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        <span>SHOOTER</span>
                        {userRole === "shooter" && <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />}
                      </button>
                    </div>
                  </div>

                  {/* Section 2: Shooter / Target Profile Selector */}
                  {(userRole === "shooter" || userRole === "instructor") && (
                    <div className="flex flex-col gap-2 pt-3 border-t border-white/5">
                      <span className="text-[9px] uppercase text-gray-500 tracking-wider font-bold">Shooter / Target Profile</span>
                      <div className="flex flex-col gap-2 bg-[#030712] border border-white/5 rounded-lg p-2.5">
                        <span className="text-[10px] text-gray-400 truncate">
                          Active: <span className="text-white font-bold">{activeShooterCandidate?.shooter_name || activeShooterCandidate?.name || "All Target Shots"}</span>
                        </span>
                        
                        <select
                          value={activeShooterCandidate?.id || ""}
                          onChange={(e) => {
                            const selected = activeUnitShooters.find(t => t.id === e.target.value);
                            setActiveShooterCandidate(selected || null);
                            setMenuOpen(false);
                          }}
                          className="w-full bg-[#080d1a] border border-white/10 rounded-md px-2 py-1.5 text-xs text-white focus:outline-none focus:border-neon transition cursor-pointer"
                        >
                          <option value="">All Target Shots</option>
                          {activeUnitShooters.map((shooter) => (
                            <option key={shooter.id} value={shooter.id}>
                              {shooter.shooter_name || shooter.name}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  )}

                  {/* Section 3: AI Verifier (Technician Config) */}
                  {userRole === "technician" && (
                    <div className="flex flex-col gap-2 pt-3 border-t border-white/5">
                      <span className="text-[9px] uppercase text-gray-500 tracking-wider font-bold">Technician Tools</span>
                      <button
                        onClick={() => {
                          toggleAiVerifier();
                          setMenuOpen(false);
                        }}
                        className={`flex items-center justify-between w-full px-3 py-2 border rounded-lg text-xs font-mono font-bold transition-all duration-150 active:scale-95 shadow-md ${
                          aiVerifierEnabled
                            ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-400 hover:bg-emerald-900/20"
                            : "bg-amber-950/40 border-amber-500/30 text-amber-400 hover:bg-amber-900/40"
                        }`}
                        title="Toggle whether YOLO/SAHI verifies candidate bullet holes"
                      >
                        <div className="flex items-center gap-2">
                          <span className={`w-1.5 h-1.5 rounded-full ${aiVerifierEnabled ? "bg-emerald-400 animate-pulse neon-glow" : "bg-emerald-400"}`} />
                          <span>AI VERIFIER: {aiVerifierEnabled ? "ACTIVE" : "BYPASSED"}</span>
                        </div>
                      </button>
                    </div>
                  )}

                  {/* Section 4: Workspace Actions */}
                  {(userRole === "technician" || userRole === "instructor") && (
                    <div className="flex flex-col gap-2 pt-3 border-t border-white/5">
                      <span className="text-[9px] uppercase text-gray-500 tracking-wider font-bold">Workspace Actions</span>
                      <div className="flex flex-col gap-2">
                        {userRole === "technician" && (
                          <button
                            onClick={() => {
                              setShowCreateTargetModal(true);
                              setMenuOpen(false);
                            }}
                            className="flex items-center justify-center gap-2 px-3 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold rounded-lg border border-blue-500/20 shadow-md active:scale-95 transition w-full"
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            <span>CREATE TARGET</span>
                          </button>
                        )}
                        
                        {userRole === "technician" && (
                          <label className="flex items-center justify-center gap-2 px-3 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold rounded-lg border border-blue-500/20 shadow-md active:scale-95 transition cursor-pointer w-full text-center">
                            <Upload className="w-3.5 h-3.5" />
                            <span>IMPORT UNIT CSV</span>
                            <input
                              type="file"
                              accept=".csv"
                              onChange={(e) => {
                                handleCsvUpload(e);
                                setMenuOpen(false);
                              }}
                              className="hidden"
                            />
                          </label>
                        )}
                        
                        {(userRole === "technician" || userRole === "instructor") && (
                          <button
                            onClick={() => {
                              setShowCreateModal(true);
                              setMenuOpen(false);
                            }}
                            className="flex items-center justify-center gap-2 px-3 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold rounded-lg border border-emerald-500/20 shadow-md active:scale-95 transition w-full"
                          >
                            <PlusCircle className="w-3.5 h-3.5" />
                            <span>NEW SESSION</span>
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Dynamic Meta-Row for all roles */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 md:gap-3 bg-[#080d1a]/60 border border-white/5 backdrop-blur-md rounded-xl p-2 md:p-3.5 font-mono text-[10px] md:text-[11px] w-full shadow-lg animate-fade-in">
          <div className="bg-white/2 border border-white/5 rounded-lg p-2 md:p-2.5 flex flex-col gap-0.5 transition-all duration-150 hover:bg-white/5 hover:border-white/10">
            <span className="text-gray-500 uppercase text-[8px] md:text-[9px] tracking-wider font-bold">Shooter Name</span>
            <span className="text-white font-semibold text-[10.5px] md:text-xs truncate" title={activeShooterCandidate?.shooter_name || activeShooterCandidate?.name || "All Shooters"}>
              {activeShooterCandidate?.shooter_name || activeShooterCandidate?.name || "All Shooters"}
            </span>
          </div>
          <div className="bg-white/2 border border-white/5 rounded-lg p-2 md:p-2.5 flex flex-col gap-0.5 transition-all duration-150 hover:bg-white/5 hover:border-white/10">
            <span className="text-gray-500 uppercase text-[8px] md:text-[9px] tracking-wider font-bold">Shooter ID</span>
            <span className="text-indigo-400 font-semibold text-[10.5px] md:text-xs truncate" title={activeShooterCandidate?.shooter_id || activeShooterCandidate?.id || "N/A"}>
              {activeShooterCandidate?.shooter_id || activeShooterCandidate?.id || "N/A"}
            </span>
          </div>
          <div className="bg-white/2 border border-white/5 rounded-lg p-2 md:p-2.5 flex flex-col gap-0.5 transition-all duration-150 hover:bg-white/5 hover:border-white/10">
            <span className="text-gray-500 uppercase text-[8px] md:text-[9px] tracking-wider font-bold">Unit</span>
            <span className="text-emerald-400 font-semibold text-[10.5px] md:text-xs truncate" title={activeSession?.unit_number || "N/A"}>
              {activeSession?.unit_number || "N/A"}
            </span>
          </div>
          <div className="bg-white/2 border border-white/5 rounded-lg p-2 md:p-2.5 flex flex-col gap-0.5 transition-all duration-150 hover:bg-white/5 hover:border-white/10">
            <span className="text-gray-500 uppercase text-[8px] md:text-[9px] tracking-wider font-bold">Drill Type</span>
            <span className="text-amber-400 font-semibold text-[10.5px] md:text-xs uppercase truncate" title={activeSession?.drill_type || "N/A"}>
              {activeSession?.drill_type || "N/A"}
            </span>
          </div>
          <div className="bg-white/2 border border-white/5 rounded-lg p-2 md:p-2.5 flex flex-col gap-0.5 transition-all duration-150 hover:bg-white/5 hover:border-white/10">
            <span className="text-gray-500 uppercase text-[8px] md:text-[9px] tracking-wider font-bold">Range</span>
            <span className="text-sky-400 font-semibold text-[10.5px] md:text-xs truncate" title={activeSession?.session_range || "N/A"}>
              {activeSession?.session_range || "N/A"}
            </span>
          </div>
          <div className="bg-white/2 border border-white/5 rounded-lg p-2 md:p-2.5 flex flex-col gap-0.5 transition-all duration-150 hover:bg-white/5 hover:border-white/10">
            <span className="text-gray-500 uppercase text-[8px] md:text-[9px] tracking-wider font-bold">Weapon Type</span>
            <span className="text-rose-400 font-semibold text-[10.5px] md:text-xs truncate" title={getWeaponType(activeSession?.bullet_caliber)}>
              {getWeaponType(activeSession?.bullet_caliber)}
            </span>
          </div>
        </div>
      </header>

      {/* Instructor Sub-navigation Bar */}
      {userRole === "instructor" && (
        <div className="flex flex-wrap items-center justify-between border border-white/5 bg-[#080d1a]/85 backdrop-blur-md rounded-lg p-2.5 md:p-3.5 mb-4 md:mb-6 font-mono gap-2 md:gap-4 animate-fade-in text-[10px] md:text-xs">
          <div className="flex items-center gap-2 md:gap-4">
            <span className="text-[10px] md:text-xs text-indigo-400 font-bold uppercase tracking-wider">Instructor Workspace:</span>
            <div className="flex bg-[#030712] border border-white/10 rounded p-0.5 gap-1">
              <button
                onClick={() => {
                  setInstructorTab("session");
                  setActiveShooterCandidate(null);
                }}
                className={`px-3 py-1 md:px-4 md:py-1.5 rounded text-[10px] md:text-xs font-bold transition-all duration-150 ${
                  instructorTab === "session"
                    ? "bg-indigo-600 text-white shadow"
                    : "text-gray-400 hover:text-white hover:bg-white/5"
                }`}
              >
                SHOOTER DETAILS
              </button>
              <button
                onClick={() => setInstructorTab("review")}
                className={`px-3 py-1 md:px-4 md:py-1.5 rounded text-[10px] md:text-xs font-bold transition-all duration-150 relative ${
                  instructorTab === "review"
                    ? "bg-indigo-600 text-white shadow"
                    : "text-gray-400 hover:text-white hover:bg-white/5"
                }`}
              >
                REVIEW QUEUE
                {reviewShots.length > 0 && (
                  <span className="absolute -top-1.5 -right-1.5 bg-rose-600 text-white font-sans font-extrabold text-[8px] md:text-[9px] w-4 h-4 md:w-4.5 md:h-4.5 flex items-center justify-center rounded-full animate-bounce shadow">
                    {reviewShots.length}
                  </span>
                )}
              </button>
            </div>
          </div>
          <div className="text-[9px] md:text-[10px] text-gray-500">
            {activeSession ? (
              <span>ACTIVE SESSION: <span className="text-white font-bold">{activeSession.name}</span></span>
            ) : (
              <span>NO SESSION ACTIVE</span>
            )}
          </div>
        </div>
      )}

      {/* Main Grid dashboard layout */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-stretch">
        
        {(userRole === "shooter" || (userRole === "instructor" && activeShooterCandidate !== null)) ? (
          <>
            {/* Mobile View Layout (Visible only on screens < xl) */}
            <div className="xl:hidden flex flex-col gap-4 col-span-1 w-full animate-fade-in">
              {userRole === "instructor" && activeShooterCandidate && (
                <div className="bg-emerald-950/45 border border-emerald-500/30 rounded-lg p-2.5 flex justify-between items-center gap-2">
                  <div className="truncate">
                    <h2 className="text-[9px] font-bold font-mono text-emerald-400 uppercase tracking-wider">Monitoring Shooter</h2>
                    <span className="text-[10.5px] font-bold text-white font-mono truncate">
                      {activeShooterCandidate.shooter_name || activeShooterCandidate.name}
                    </span>
                  </div>
                  <button
                    onClick={() => setActiveShooterCandidate(null)}
                    className="px-2 py-0.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-[9px] font-mono font-bold rounded border border-emerald-500/20 active:scale-95 transition uppercase"
                  >
                    Exit
                  </button>
                </div>
              )}

              {/* Above-the-fold Container */}
              <div className="flex flex-col gap-4">
                {/* Before Fire & Trigger Fired Action Buttons */}
                <div className="grid grid-cols-2 gap-3 flex-shrink-0 min-h-[100px]">
                  {/* Capture Before Fire Button */}
                  <button
                    onClick={handleBeforeFire}
                    disabled={!isCameraActive || isCapturingBeforeFire}
                    className={`flex flex-col justify-center items-center text-center p-2.5 rounded-xl border transition-all duration-300 relative overflow-hidden shadow-2xl ${
                      !isCameraActive
                        ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                        : "border-blue-500/25 bg-blue-950/20 hover:bg-blue-900/30 text-white active:scale-[0.98]"
                    }`}
                    style={{
                      boxShadow: isCameraActive ? "0 8px 32px 0 rgba(59, 130, 246, 0.08), inset 0 0 16px rgba(59, 130, 246, 0.05)" : "none"
                    }}
                  >
                    <div className="flex flex-col items-center gap-1">
                      <Camera className="w-6 h-6 text-blue-400" />
                      <span className="text-[9px] font-extrabold font-mono uppercase tracking-wider text-blue-300">
                        {isCapturingBeforeFire ? "CAPTURING..." : "BEFORE FIRE"}
                      </span>
                      <span className="text-[7px] text-gray-400 font-mono leading-none">
                        Pristine baseline snapshot
                      </span>
                    </div>
                  </button>

                  {/* Trigger Fired Button */}
                  <button
                    onClick={handleFire}
                    disabled={!isCameraActive || !baselineUrl || isDetecting}
                    className={`flex flex-col justify-center items-center text-center p-2.5 rounded-xl border transition-all duration-300 relative overflow-hidden shadow-2xl ${
                      !isCameraActive || !baselineUrl
                        ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                        : "border-red-500/25 bg-red-950/20 hover:bg-red-900/30 text-white active:scale-[0.98]"
                    }`}
                    style={{
                      boxShadow: (isCameraActive && baselineUrl) ? "0 8px 32px 0 rgba(239, 68, 68, 0.08), inset 0 0 16px rgba(239, 68, 68, 0.05)" : "none"
                    }}
                  >
                    <div className="flex flex-col items-center gap-1">
                      <Flame className="w-6 h-6 text-red-400 animate-pulse" />
                      <span className="text-[9px] font-extrabold font-mono uppercase tracking-wider text-red-300">
                        {isDetecting ? "ANALYZING..." : "TRIGGER FIRED"}
                      </span>
                      <span className="text-[7px] text-gray-400 font-mono leading-none">
                        Localize bullet impact
                      </span>
                    </div>
                  </button>
                </div>
              </div>

              {/* Scrollable Details & Images (below the fold) */}
              <div className="mt-4 flex flex-col gap-6">
                {/* Mobile Shooter/Target selector is handled dynamically inside the header Hamburger Menu */}

                {/* Stats Row */}
                <div className="grid grid-cols-4 gap-3 w-full">
                  <div className="glass-panel p-2.5 flex flex-col justify-center border border-emerald-500/10 bg-emerald-950/5 shadow-lg min-h-[52px] text-center rounded-xl">
                    <span className="text-[7.5px] font-bold text-emerald-400/80 font-mono tracking-wider uppercase truncate">Shots</span>
                    <span className="text-sm font-extrabold text-emerald-400 font-mono mt-0.5 truncate">
                      {activeSession ? `${mobileValidShots.length}/${activeSession.bullets_per_drill || 0}` : "0"}
                    </span>
                  </div>

                  <div className="glass-panel p-2.5 flex flex-col justify-center border border-red-500/10 bg-red-950/5 shadow-lg min-h-[52px] text-center rounded-xl">
                    <span className="text-[7.5px] font-bold text-red-400/80 font-mono tracking-wider uppercase truncate">Missed</span>
                    <span className="text-sm font-extrabold text-red-400 font-mono mt-0.5 truncate font-bold">
                      {mobileMissedShots}
                    </span>
                  </div>

                  <div className="glass-panel p-2.5 flex flex-col justify-center border border-blue-500/10 bg-blue-950/5 shadow-lg min-h-[52px] text-center rounded-xl">
                    <span className="text-[7.5px] font-bold text-blue-400/80 font-mono tracking-wider uppercase truncate">Grouping</span>
                    <span className="text-sm font-extrabold text-blue-400 font-mono mt-0.5 truncate">
                      {mobileGroupingMm > 0 ? `${mobileGroupingInches.toFixed(2)}"` : "N/A"}
                    </span>
                  </div>

                  <div className="glass-panel p-2.5 flex flex-col justify-center border border-amber-500/10 bg-amber-950/5 shadow-lg min-h-[52px] text-center rounded-xl">
                    <span className="text-[7.5px] font-bold text-amber-400/80 font-mono tracking-wider uppercase truncate">Score</span>
                    <span className="text-sm font-extrabold text-amber-400 font-mono mt-0.5 truncate font-bold">
                      {mobileTotalScore.toFixed(1)}
                    </span>
                  </div>
                </div>

                {/* 1. Session Details Component */}
                <div className="glass-panel p-4 flex flex-col h-fit">
                  <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center w-full mb-4 border-b border-white/5 pb-3 gap-3">
                    <div className="leading-tight">
                      <h3 className="text-xs font-bold font-mono tracking-wider uppercase text-white">Session Details</h3>
                      <p className="text-[9px] text-gray-500 font-mono mt-0.5">Confirmed Shots, Candidates, Statistical metrics</p>
                    </div>
                    <div className="flex flex-wrap gap-1 font-mono text-[9px]">
                      <button
                        type="button"
                        onClick={() => setSessionDetailsTab("shots")}
                        className={`px-2 py-1 rounded-lg border transition font-bold ${
                          sessionDetailsTab === "shots"
                            ? "bg-neon/15 border-neon text-neon"
                            : "bg-white/2 border-white/10 text-gray-400 hover:text-white"
                        }`}
                      >
                        Confirmed
                      </button>
                      {userRole !== "shooter" && !activeShooterCandidate && (
                        <button
                          type="button"
                          onClick={() => setSessionDetailsTab("candidates")}
                          className={`px-2 py-1 rounded-lg border transition font-bold ${
                            sessionDetailsTab === "candidates"
                              ? "bg-neon/15 border-neon text-neon"
                              : "bg-white/2 border-white/10 text-gray-400 hover:text-white"
                          }`}
                        >
                          Candidates
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => setSessionDetailsTab("stats")}
                        className={`px-2 py-1 rounded-lg border transition font-bold ${
                          sessionDetailsTab === "stats"
                            ? "bg-neon/15 border-neon text-neon"
                            : "bg-white/2 border-white/10 text-gray-400 hover:text-white"
                        }`}
                      >
                        Metrics
                      </button>
                    </div>
                  </div>

                  <div className="flex-1">
                    {sessionDetailsTab === "shots" && <ShotTable forceMode="shots" selectedShooter={activeShooterCandidate} />}
                    {sessionDetailsTab === "candidates" && <ShotTable forceMode="candidates" selectedShooter={activeShooterCandidate} />}
                    {sessionDetailsTab === "stats" && <StatsPanel noBorder selectedShooter={activeShooterCandidate} />}
                  </div>
                </div>

                {/* 2. Live Target View Image Visualizer */}
                <LiveTargetView
                  cameraOnline={cameraOnline}
                  isCameraActive={isCameraActive}
                  pingCooldown={pingCooldown}
                  handlePingCamera={handlePingCamera}
                  selectedShooter={activeShooterCandidate}
                />

                {/* 3. Camera Configuration & Calibration Component */}
                <div className="glass-panel p-5">
                  <button
                    type="button"
                    onClick={() => setShowCameraControls(!showCameraControls)}
                    className="flex justify-between items-center w-full font-mono text-xs font-bold text-gray-300 hover:text-white uppercase tracking-wider transition focus:outline-none"
                  >
                    <div className="flex items-center gap-2">
                      <Play className="w-4 h-4 text-neon" />
                      <span>Camera Configuration & Calibration</span>
                    </div>
                    <span className="text-[10px] font-mono text-gray-500">
                      {showCameraControls ? "COLLAPSE [-]" : "EXPAND [+]"}
                    </span>
                  </button>

                  {showCameraControls && (
                    <div className="mt-4 border-t border-white/5 pt-4">
                      <div className="flex justify-between items-center w-full mb-4 border-b border-white/5 pb-3">
                        <div className="flex items-center gap-2">
                          <Play className="w-5 h-5 text-neon" />
                          <h3 className="text-sm font-bold font-mono tracking-wider uppercase">Live Camera Integration</h3>
                        </div>
                        
                        {/* Ping Camera Status Button */}
                        <div className="flex items-center gap-2.5">
                          <span className={`w-2 h-2 rounded-full ${cameraOnline || isCameraActive ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
                          <span className="text-[10px] font-mono uppercase text-gray-400">
                            {cameraOnline || isCameraActive ? "Online" : "Offline"}
                          </span>
                          <button
                            onClick={handlePingCamera}
                            disabled={pingCooldown > 0}
                            className="px-2.5 py-1 bg-white/5 hover:bg-white/10 text-gray-300 disabled:text-gray-600 disabled:hover:bg-white/5 border border-white/10 rounded text-[9px] font-mono transition"
                          >
                            {pingCooldown > 0 ? `PING (${pingCooldown}s)` : "PING CAMERA"}
                          </button>
                        </div>
                      </div>

                      {!activeSession ? (
                        <div className="flex items-center gap-3 p-4 border border-white/5 bg-white/2 rounded-lg text-xs font-mono text-amber-500">
                          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                          <span>No active shooting session. Click "NEW SESSION" above to begin.</span>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {/* Active Session & Details for Shooter */}
                          <div className="bg-[#090d16] border border-white/5 rounded-lg p-3.5 font-mono text-[10px] text-gray-400 flex flex-col gap-2 shadow-inner">
                            <div className="flex justify-between items-center border-b border-white/5 pb-1.5">
                              <span className="text-[11px] font-bold text-white uppercase tracking-wider">
                                Session: {activeSession.name}
                              </span>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-bold font-bold">
                                Caliber: {activeSession.bullet_caliber}mm
                              </span>
                            </div>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-2 gap-x-4">
                              {activeSession.unit_number && (
                                <div className="flex flex-col">
                                  <span className="text-[9px] text-gray-500 uppercase">Unit Number</span>
                                  <span className="text-white font-semibold text-[10.5px]">{activeSession.unit_number}</span>
                                </div>
                              )}
                              {activeSession.session_date && (
                                <div className="flex flex-col">
                                  <span className="text-[9px] text-gray-500 uppercase">Date & Time</span>
                                  <span className="text-white font-semibold text-[10.5px]">{activeSession.session_date.replace("T", " ")}</span>
                                </div>
                              )}
                              {activeSession.session_range && (
                                <div className="flex flex-col">
                                  <span className="text-[9px] text-gray-500 uppercase">Range (Distance)</span>
                                  <span className="text-white font-semibold text-[10.5px]">{activeSession.session_range}</span>
                                </div>
                              )}
                              {activeSession.drill_type && (
                                <div className="flex flex-col">
                                  <span className="text-[9px] text-gray-500 uppercase">Drill Type</span>
                                  <span className="text-white font-semibold text-[10.5px] capitalize">{activeSession.drill_type}</span>
                                </div>
                              )}
                              {activeSession.bullets_per_drill && (
                                <div className="flex flex-col">
                                  <span className="text-[9px] text-gray-500 uppercase">Bullets Limit</span>
                                  <span className="text-white font-semibold text-[10.5px]">{activeSession.bullets_per_drill} shots</span>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Capture Before Fire */}
                          <button
                            onClick={handleBeforeFire}
                            disabled={!isCameraActive || isCapturingBeforeFire}
                            className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 w-full ${
                              !isCameraActive
                                ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                                : "border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/10 text-white"
                            }`}
                          >
                            <div className="mb-2">
                              <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-blue-400 font-bold">
                                Before Fire
                              </h4>
                              <p className="text-[9px] text-gray-500 leading-tight">
                                Click before firing shots. Takes a pristine snapshot to serve as the reference for differencing.
                              </p>
                            </div>
                            <span className="text-[10px] font-mono font-bold px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded mt-2 uppercase font-bold">
                              Before Fire
                            </span>
                          </button>
         
                          {/* Fired snapshot trigger */}
                          <button
                            onClick={handleFire}
                            disabled={!isCameraActive || !baselineUrl || isDetecting}
                            className={`flex-col flex justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 w-full ${
                              !isCameraActive || !baselineUrl
                                ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                                : "border-red-500/20 bg-red-500/5 hover:bg-red-500/10 text-white"
                            }`}
                          >
                            <div className="mb-2">
                              <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-red-400 font-bold">
                                Trigger Fired
                              </h4>
                              <p className="text-[9px] text-gray-500 leading-tight">
                                Click after firing a shot. Snaps the live camera feed and compares it against the "Before Fire" baseline.
                              </p>
                            </div>
                            <span className="text-[10px] font-mono font-bold px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded mt-2 uppercase font-bold">
                              Trigger Fired
                            </span>
                          </button>

                          {/* Calibration Trigger Panel */}
                          <div className="flex flex-col gap-2 pt-2 border-t border-white/5">
                            <button
                              onClick={() => handleCalibrate(false)}
                              disabled={!isCameraActive || isCalibrating}
                              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-mono text-xs font-bold rounded-lg shadow-md active:scale-95 transition-all duration-150 uppercase"
                            >
                              <Play className="w-3.5 h-3.5" />
                              {isCalibrating ? "Calibrating..." : "Calibrate perspective"}
                            </button>
                            <button
                              onClick={() => handleCalibrate(true)}
                              disabled={!isCameraActive || isCalibrating}
                              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-white/5 border border-white/10 hover:bg-white/10 text-gray-300 font-mono text-xs font-bold rounded-lg active:scale-95 transition uppercase"
                            >
                              Contour Detection Only (No tags)
                            </button>
                          </div>

                          {/* Video Preview Feed & Zoom Slider */}
                          {isCameraActive && (
                            <div className="space-y-3 pt-2 border-t border-white/5">
                              <div className="relative border border-white/10 rounded-lg overflow-hidden bg-black flex items-center justify-center aspect-video">
                                <img
                                  key={showTagFeed ? "tagfeed" : "livefeed"}
                                  src={`${BACKEND_URL}/api/v1/camera/${showTagFeed ? "tag_stream" : "stream"}`}
                                  alt="Camera Video Stream Feed"
                                  className="w-full h-full object-cover"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowTagFeed((v) => !v)}
                                  className={`absolute top-2 left-2 px-2 py-0.5 rounded text-[9px] font-mono font-bold border transition ${
                                    showTagFeed
                                      ? "bg-fuchsia-600/30 text-fuchsia-300 border-fuchsia-400/50"
                                      : "bg-black/60 text-gray-300 border-white/20 hover:text-white hover:border-white/40"
                                  }`}
                                  title="Overlay live AprilTag detection to diagnose tag/backend issues"
                                >
                                  {showTagFeed ? "● LIVE TAG FEED" : "LIVE TAG FEED"}
                                </button>
                                <div className="absolute top-2 right-2 px-2 py-0.5 bg-black/60 rounded text-[9px] font-mono text-neon border border-neon/20 animate-pulse">
                                  {showTagFeed ? "TAG DEBUG" : "LIVE FEED"}
                                </div>
                              </div>

                              <div className="space-y-1.5 p-3 bg-white/2 border border-white/5 rounded-lg">
                                <div className="flex justify-between text-[10px] font-mono text-gray-400">
                                  <span>DIGITAL FEED ZOOM:</span>
                                  <span className="text-neon font-bold">{zoomFactor.toFixed(1)}x</span>
                                </div>
                                <input
                                  type="range"
                                  min="1.0"
                                  max="3.0"
                                  step="0.1"
                                  value={zoomFactor}
                                  onChange={handleZoomChange}
                                  className="w-full h-1.5 bg-[#030712] border border-white/10 rounded-lg appearance-none cursor-pointer accent-neon"
                                />
                              </div>
                            </div>
                          )}

                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Desktop View Layout - Left Column (Visible only on screens xl and up) */}
            <div className="hidden xl:flex xl:col-span-6 flex-col gap-6">
              
              {/* Desktop Shooter/Target selector is handled dynamically inside the header Hamburger Menu */}
              {userRole === "instructor" && activeShooterCandidate && (
                <div className="bg-emerald-950/40 border border-emerald-500/30 rounded-lg p-4 flex flex-wrap justify-between items-center gap-3">
                  <div>
                    <h2 className="text-xs font-bold font-mono text-emerald-400 tracking-wider uppercase">Shooter Monitoring Mode</h2>
                    <p className="text-[10px] text-gray-400 mt-1 font-mono font-bold">
                      Candidate: <span className="text-white font-bold">{activeShooterCandidate.shooter_name || activeShooterCandidate.name}</span> | Unit: <span className="text-white font-bold">{activeSession?.unit_number || "N/A"}</span>
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveShooterCandidate(null)}
                    className="px-3 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-[10px] font-mono font-bold rounded border border-emerald-500/20 shadow-md active:scale-95 transition uppercase"
                  >
                    ← Exit View
                  </button>
                </div>
              )}
              
              <LiveTargetView
                cameraOnline={cameraOnline}
                isCameraActive={isCameraActive}
                pingCooldown={pingCooldown}
                handlePingCamera={handlePingCamera}
                selectedShooter={activeShooterCandidate}
              />

              {/* Collapsible Session Controller Panel (Camera Streaming & Calibration) */}
              <div className="glass-panel p-5">
                <button
                  type="button"
                  onClick={() => setShowCameraControls(!showCameraControls)}
                  className="flex justify-between items-center w-full font-mono text-xs font-bold text-gray-300 hover:text-white uppercase tracking-wider transition focus:outline-none"
                >
                  <div className="flex items-center gap-2">
                    <Play className="w-4 h-4 text-neon" />
                    <span>Camera Configuration & Calibration</span>
                  </div>
                  <span className="text-[10px] font-mono text-gray-500">
                    {showCameraControls ? "COLLAPSE [-]" : "EXPAND [+]"}
                  </span>
                </button>

                {showCameraControls && (
                  <div className="mt-4 border-t border-white/5 pt-4">
                    <div className="flex justify-between items-center w-full mb-4 border-b border-white/5 pb-3">
                      <div className="flex items-center gap-2">
                        <Play className="w-5 h-5 text-neon" />
                        <h3 className="text-sm font-bold font-mono tracking-wider uppercase">Live Camera Integration</h3>
                      </div>
                      
                      {/* Ping Camera Status Button */}
                      <div className="flex items-center gap-2.5">
                        <span className={`w-2 h-2 rounded-full ${cameraOnline || isCameraActive ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
                        <span className="text-[10px] font-mono uppercase text-gray-400">
                          {cameraOnline || isCameraActive ? "Online" : "Offline"}
                        </span>
                        <button
                          onClick={handlePingCamera}
                          disabled={pingCooldown > 0}
                          className="px-2.5 py-1 bg-white/5 hover:bg-white/10 text-gray-300 disabled:text-gray-600 disabled:hover:bg-white/5 border border-white/10 rounded text-[9px] font-mono transition"
                        >
                          {pingCooldown > 0 ? `PING (${pingCooldown}s)` : "PING CAMERA"}
                        </button>
                      </div>
                    </div>

                    {!activeSession ? (
                      <div className="flex items-center gap-3 p-4 border border-white/5 bg-white/2 rounded-lg text-xs font-mono text-amber-500">
                        <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                        <span>No active shooting session. Click "NEW SESSION" above to begin.</span>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {/* Active Session & Details for Shooter */}
                        <div className="bg-[#090d16] border border-white/5 rounded-lg p-3.5 font-mono text-[10px] text-gray-400 flex flex-col gap-2 shadow-inner">
                          <div className="flex justify-between items-center border-b border-white/5 pb-1.5">
                            <span className="text-[11px] font-bold text-white uppercase tracking-wider">
                              Session: {activeSession.name}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-bold font-bold">
                              Caliber: {activeSession.bullet_caliber}mm
                            </span>
                          </div>
                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-2 gap-x-4">
                            {activeSession.unit_number && (
                              <div className="flex flex-col">
                                <span className="text-[9px] text-gray-500 uppercase">Unit Number</span>
                                <span className="text-white font-semibold text-[10.5px]">{activeSession.unit_number}</span>
                              </div>
                            )}
                            {activeSession.session_date && (
                              <div className="flex flex-col">
                                <span className="text-[9px] text-gray-500 uppercase">Date & Time</span>
                                <span className="text-white font-semibold text-[10.5px]">{activeSession.session_date.replace("T", " ")}</span>
                              </div>
                            )}
                            {activeSession.session_range && (
                              <div className="flex flex-col">
                                <span className="text-[9px] text-gray-500 uppercase">Range (Distance)</span>
                                <span className="text-white font-semibold text-[10.5px]">{activeSession.session_range}</span>
                              </div>
                            )}
                            {activeSession.drill_type && (
                              <div className="flex flex-col">
                                <span className="text-[9px] text-gray-500 uppercase">Drill Type</span>
                                <span className="text-white font-semibold text-[10.5px] capitalize">{activeSession.drill_type}</span>
                              </div>
                            )}
                            {activeSession.bullets_per_drill && (
                              <div className="flex flex-col">
                                <span className="text-[9px] text-gray-500 uppercase">Bullets Limit</span>
                                <span className="text-white font-semibold text-[10.5px]">{activeSession.bullets_per_drill} shots</span>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Capture Before Fire (Reference image) */}
                        <button
                          onClick={handleBeforeFire}
                          disabled={!isCameraActive || isCapturingBeforeFire}
                          className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 w-full ${
                            !isCameraActive
                              ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                              : "border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/10 text-white"
                          }`}
                        >
                          <div className="mb-2">
                            <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-blue-400 font-bold">
                              Before Fire
                            </h4>
                            <p className="text-[9px] text-gray-500 leading-tight">
                              Click before firing shots. Takes a pristine snapshot to serve as the reference for differencing.
                            </p>
                          </div>
                          <span className="text-[10px] font-mono font-bold px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded mt-2 uppercase font-bold">
                            Before Fire
                          </span>
                        </button>
       
                        {/* Fired snapshot trigger */}
                        <button
                          onClick={handleFire}
                          disabled={!isCameraActive || !baselineUrl || isDetecting}
                          className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 w-full ${
                            !isCameraActive || !baselineUrl
                              ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                              : "border-red-500/20 bg-red-500/5 hover:bg-red-500/10 text-white"
                          }`}
                        >
                          <div className="mb-2">
                            <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-red-400 font-bold">
                              Trigger Fired
                            </h4>
                            <p className="text-[9px] text-gray-500 leading-tight">
                              Click after firing a shot. Snaps the live camera feed and compares it against the "Before Fire" baseline.
                            </p>
                          </div>
                          <span className="text-[10px] font-mono font-bold px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded mt-2 uppercase font-bold">
                            Trigger Fired
                          </span>
                        </button>
       
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Desktop View Layout - Right Column (Visible only on screens xl and up) */}
            <div className="hidden xl:flex xl:col-span-6 flex-col gap-6">
              <OverviewCards isMonitoringShooter={userRole === "instructor" && activeShooterCandidate !== null} selectedShooter={activeShooterCandidate} />

              {/* Session Details Container */}
              <div className="glass-panel p-6 flex flex-col flex-1 h-fit">
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center w-full mb-4 border-b border-white/5 pb-3 gap-3">
                  <div className="leading-tight">
                    <h3 className="text-sm font-bold font-mono tracking-wider uppercase text-white">Session Details</h3>
                    <p className="text-[10px] text-gray-500 font-mono mt-0.5">Confirmed Shots, Candidates, Statistical metrics</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
                    <button
                      type="button"
                      onClick={() => setSessionDetailsTab("shots")}
                      className={`px-3 py-1.5 rounded-lg border transition font-bold ${
                        sessionDetailsTab === "shots"
                          ? "bg-neon/15 border-neon text-neon"
                          : "bg-white/2 border-white/10 text-gray-400 hover:text-white hover:bg-white/5"
                      }`}
                    >
                      Confirmed Shots
                    </button>
                    {userRole !== "shooter" && !activeShooterCandidate && (
                      <button
                        type="button"
                        onClick={() => setSessionDetailsTab("candidates")}
                        className={`px-3 py-1.5 rounded-lg border transition font-bold ${
                          sessionDetailsTab === "candidates"
                            ? "bg-neon/15 border-neon text-neon"
                            : "bg-white/2 border-white/10 text-gray-400 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        Candidates
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setSessionDetailsTab("stats")}
                      className={`px-3 py-1.5 rounded-lg border transition font-bold ${
                        sessionDetailsTab === "stats"
                          ? "bg-neon/15 border-neon text-neon"
                          : "bg-white/2 border-white/10 text-gray-400 hover:text-white hover:bg-white/5"
                      }`}
                    >
                      Statistical Metrics
                    </button>
                  </div>
                </div>

                <div className="flex-1">
                  {sessionDetailsTab === "shots" && <ShotTable forceMode="shots" selectedShooter={activeShooterCandidate} />}
                  {sessionDetailsTab === "candidates" && <ShotTable forceMode="candidates" selectedShooter={activeShooterCandidate} />}
                  {sessionDetailsTab === "stats" && <StatsPanel noBorder selectedShooter={activeShooterCandidate} />}
                </div>
              </div>
            </div>
          </>
        ) : (userRole === "instructor" && instructorTab === "review") ? (
          <div className="xl:col-span-12 flex flex-col gap-6 animate-fade-in">
            {/* Instructor Review Dashboard */}
            <div className="glass-panel p-6 flex flex-col gap-6">
              {/* Header */}
              <div className="flex flex-wrap items-center justify-between border-b border-white/5 pb-4 gap-4">
                <div>
                  <h2 className="text-base font-bold font-mono text-white tracking-wider uppercase flex items-center gap-2">
                    <ShieldAlert className="w-5 h-5 text-amber-500 animate-pulse" />
                    Shots Pending Boundary Verification
                  </h2>
                  <p className="text-xs text-gray-400 font-mono mt-1">
                    Review bullet impacts flagged by the localization engine for ring boundary validation.
                  </p>
                </div>
                <button
                  onClick={fetchReviewShots}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 border border-white/10 hover:bg-white/10 rounded font-mono text-xs text-gray-300 transition"
                >
                  REFRESH QUEUE
                </button>
              </div>

              {reviewShots.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center bg-[#030712]/30 border border-white/5 rounded-xl animate-fade-in">
                  <CircleCheck className="w-12 h-12 text-emerald-400 mb-3 animate-pulse" />
                  <h3 className="text-sm font-bold font-mono text-white uppercase tracking-wider">Review Queue Empty</h3>
                  <p className="text-xs text-gray-500 font-mono mt-1.5 max-w-sm">
                    All classical CV and AI verified shots have settled boundaries. No manual intervention required.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 animate-fade-in">
                  {reviewShots.map((shot) => {
                    const ageSec = Math.floor((Date.now() - new Date(shot.created_at).getTime()) / 1000);
                    const ageStr = ageSec < 60 ? `${ageSec}s ago` : ageSec < 3600 ? `${Math.floor(ageSec/60)}m ago` : `${Math.floor(ageSec/3600)}h ago`;

                    return (
                      <div 
                        key={shot.id} 
                        className="bg-[#060b16]/90 border border-amber-500/25 hover:border-amber-500/40 rounded-xl p-5 flex flex-col justify-between gap-4 shadow-lg shadow-amber-500/5 transition-all duration-150"
                      >
                        {/* Card Top */}
                        <div>
                          <div className="flex justify-between items-start mb-2">
                            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400 uppercase tracking-wider flex items-center gap-1">
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
                              Boundary Alert
                            </span>
                            <span className="text-[10px] text-gray-500 font-mono">{ageStr}</span>
                          </div>

                          <div className="flex justify-between items-baseline">
                            <h3 className="text-base font-bold font-mono text-white">Shot #{shot.shot_number}</h3>
                            <span className="text-[10px] text-gray-400 font-mono">Session: {shot.session_id.slice(0, 8)}...</span>
                          </div>
                        </div>

                        {/* Detail Stats */}
                        <div className="grid grid-cols-2 gap-3 bg-[#030712]/60 border border-white/5 rounded-lg p-3 font-mono text-[10px] text-gray-400">
                          <div className="flex flex-col">
                            <span className="text-[8px] text-gray-500 uppercase">Impact Score</span>
                            <span className="text-white font-bold text-sm mt-0.5">
                              {shot.score !== null && shot.score !== undefined ? `${shot.score} pts` : "N/A"}
                            </span>
                            {shot.decimal_score !== null && shot.decimal_score !== undefined && (
                              <span className="text-gray-400 font-medium text-[9px] mt-0.5">
                                Decimal: {shot.decimal_score.toFixed(1)}
                              </span>
                            )}
                          </div>
                          <div className="flex flex-col">
                            <span className="text-[8px] text-gray-500 uppercase">Boundary Distance</span>
                            <span className="text-white font-bold text-xs mt-1">
                              {shot.distance_to_nearest_ring_mm !== null && shot.distance_to_nearest_ring_mm !== undefined
                                ? `${shot.distance_to_nearest_ring_mm.toFixed(2)} mm`
                                : "N/A"}
                            </span>
                            <span className="text-gray-400 text-[8px] mt-0.5">
                              Nearest: Ring {shot.nearest_ring_value ?? "?"}
                            </span>
                          </div>
                          <div className="flex flex-col col-span-2 border-t border-white/5 pt-2 mt-1">
                            <span className="text-[8px] text-gray-500 uppercase">Localization Uncertainty</span>
                            <span className="text-amber-400 font-bold text-xs mt-0.5">
                              ± {shot.localization_error_mm !== undefined && shot.localization_error_mm !== null
                                ? `${shot.localization_error_mm.toFixed(2)} mm`
                                : "0.30 mm"}
                            </span>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="flex flex-col gap-2 pt-2 border-t border-white/5 mt-1">
                          <button
                            onClick={() => handleViewReviewShot(shot)}
                            className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-mono text-xs font-bold rounded-lg shadow-md active:scale-95 transition-all duration-150 uppercase"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            View on Target
                          </button>
                          <div className="grid grid-cols-2 gap-2">
                            <button
                              onClick={() => handleApproveReviewShot(shot)}
                              className="flex items-center justify-center gap-1 px-2.5 py-1.5 bg-[#0a1f18] hover:bg-[#0f2d22] border border-emerald-500/20 text-emerald-400 font-mono text-[10px] font-bold rounded-lg transition"
                            >
                              <CircleCheck className="w-3.5 h-3.5" />
                              Approve
                            </button>
                            <button
                              onClick={() => handleExcludeReviewShot(shot)}
                              className="flex items-center justify-center gap-1 px-2.5 py-1.5 bg-[#2a0e10] hover:bg-[#3d1518] border border-red-500/20 text-red-400 font-mono text-[10px] font-bold rounded-lg transition"
                            >
                              <Trash className="w-3.5 h-3.5" />
                              Exclude
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* Standard Technician/Instructor view - Left Column: Visualizer & Calibration Control (col-span-5) */}
            <div className="xl:col-span-5 flex flex-col gap-6">
              
              {/* Mobile-only Above-the-fold Action Buttons */}
              <div className="xl:hidden flex flex-col gap-4 w-full">
                {/* Before Fire & Trigger Fired Action Buttons */}
                <div className="grid grid-cols-2 gap-3 flex-shrink-0 min-h-[100px]">
                  {/* Capture Before Fire Button */}
                  <button
                    onClick={handleBeforeFire}
                    disabled={!isCameraActive || isCapturingBeforeFire}
                    className={`flex flex-col justify-center items-center text-center p-2.5 rounded-xl border transition-all duration-300 relative overflow-hidden shadow-2xl ${
                      !isCameraActive
                        ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                        : "border-blue-500/25 bg-blue-950/20 hover:bg-blue-900/30 text-white active:scale-[0.98]"
                    }`}
                    style={{
                      boxShadow: isCameraActive ? "0 8px 32px 0 rgba(59, 130, 246, 0.08), inset 0 0 16px rgba(59, 130, 246, 0.05)" : "none"
                    }}
                  >
                    <div className="flex flex-col items-center gap-1">
                      <Camera className="w-6 h-6 text-blue-400" />
                      <span className="text-[9px] font-extrabold font-mono uppercase tracking-wider text-blue-300">
                        {isCapturingBeforeFire ? "CAPTURING..." : "BEFORE FIRE"}
                      </span>
                      <span className="text-[7px] text-gray-400 font-mono leading-none">
                        Pristine baseline snapshot
                      </span>
                    </div>
                  </button>

                  {/* Trigger Fired Button */}
                  <button
                    onClick={handleFire}
                    disabled={!isCameraActive || !baselineUrl || isDetecting}
                    className={`flex flex-col justify-center items-center text-center p-2.5 rounded-xl border transition-all duration-300 relative overflow-hidden shadow-2xl ${
                      !isCameraActive || !baselineUrl
                        ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed text-gray-500"
                        : "border-red-500/25 bg-red-950/20 hover:bg-red-900/30 text-white active:scale-[0.98]"
                    }`}
                    style={{
                      boxShadow: (isCameraActive && baselineUrl) ? "0 8px 32px 0 rgba(239, 68, 68, 0.08), inset 0 0 16px rgba(239, 68, 68, 0.05)" : "none"
                    }}
                  >
                    <div className="flex flex-col items-center gap-1">
                      <Flame className="w-6 h-6 text-red-400 animate-pulse" />
                      <span className="text-[9px] font-extrabold font-mono uppercase tracking-wider text-red-300">
                        {isDetecting ? "ANALYZING..." : "TRIGGER FIRED"}
                      </span>
                      <span className="text-[7px] text-gray-400 font-mono leading-none">
                        Localize bullet impact
                      </span>
                    </div>
                  </button>
                </div>
              </div>

              <LiveTargetView
                cameraOnline={cameraOnline}
                isCameraActive={isCameraActive}
                pingCooldown={pingCooldown}
                handlePingCamera={handlePingCamera}
              />

              {/* Session Controller Panel (Camera Streaming & Calibration) */}
              <div className="glass-panel p-6">
                <div className="flex justify-between items-center w-full mb-4 border-b border-white/5 pb-3">
                  <div className="flex items-center gap-2">
                    <Play className="w-5 h-5 text-neon" />
                    <h3 className="text-sm font-bold font-mono tracking-wider uppercase">Live Camera Integration</h3>
                  </div>
                  
                  {/* Ping Camera Status Button */}
                  <div className="flex items-center gap-2.5">
                    <span className={`w-2 h-2 rounded-full ${cameraOnline || isCameraActive ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`} />
                    <span className="text-[10px] font-mono uppercase text-gray-400">
                      {cameraOnline || isCameraActive ? "Online" : "Offline"}
                    </span>
                    <button
                      onClick={handlePingCamera}
                      disabled={pingCooldown > 0}
                      className="px-2.5 py-1 bg-white/5 hover:bg-white/10 text-gray-300 disabled:text-gray-600 disabled:hover:bg-white/5 border border-white/10 rounded text-[9px] font-mono transition"
                    >
                      {pingCooldown > 0 ? `PING (${pingCooldown}s)` : "PING CAMERA"}
                    </button>
                  </div>
                </div>

                {!activeSession ? (
                  <div className="flex items-center gap-3 p-4 border border-white/5 bg-white/2 rounded-lg text-xs font-mono text-amber-500">
                    <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                    <span>No active shooting session. Click "NEW SESSION" above to begin.</span>
                  </div>
                ) : (
                  <div className="space-y-4">
                    
                    {/* Camera Source Selector */}
                    <div className="flex gap-2 items-end">
                      <div className="flex-1 space-y-1">
                        <label className="text-[9px] font-mono uppercase text-gray-500">Camera Source (Index or IP URL)</label>
                        <input
                          type="text"
                          placeholder="e.g. 0 (webcam) or http://192.168.1.100:8080/video"
                          value={cameraSource}
                          onChange={(e) => setCameraSource(e.target.value)}
                          disabled={isCameraActive || (userRole !== "technician" && userRole !== "instructor")}
                          className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon transition disabled:opacity-50"
                        />
                      </div>
                      <div className="w-32 md:w-44 space-y-1">
                        <label className="text-[9px] font-mono uppercase text-gray-500">Resolution</label>
                        <select
                          value={cameraResolution}
                          onChange={(e) => setCameraResolution(e.target.value)}
                          disabled={isCameraActive || (userRole !== "technician" && userRole !== "instructor")}
                          className="w-full bg-[#030712] border border-white/10 rounded px-2 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon transition disabled:opacity-50"
                        >
                          <option value="native">Native (Highest)</option>
                          <option value="3840x2160">3840x2160 (4K UHD)</option>
                          <option value="1920x1080">1920x1080 (1080p FHD)</option>
                          <option value="1280x720">1280x720 (720p HD)</option>
                          <option value="640x480">640x480 (VGA)</option>
                        </select>
                      </div>
                      <button
                        onClick={toggleCamera}
                        className={`px-4 py-1.5 rounded text-xs font-mono font-bold transition-all duration-150 ${
                          isCameraActive
                            ? "bg-red-600 hover:bg-red-500 text-white"
                            : "bg-white/5 border-white/10 hover:bg-white/10 text-gray-300 hover:text-white"
                        }`}
                      >
                        {isCameraActive ? "DISCONNECT" : "CONNECT"}
                      </button>
                    </div>

                    {/* Video Preview Feed & Zoom Slider */}
                    {isCameraActive && (userRole === "technician" || userRole === "instructor") && (
                      <div className="space-y-3">
                        <div className="relative border border-white/10 rounded-lg overflow-hidden bg-black flex items-center justify-center aspect-video">
                          <img
                            key={showTagFeed ? "tagfeed" : "livefeed"}
                            src={`${BACKEND_URL}/api/v1/camera/${showTagFeed ? "tag_stream" : "stream"}`}
                            alt="Camera Video Stream Feed"
                            className="w-full h-full object-cover"
                          />
                          <button
                            type="button"
                            onClick={() => setShowTagFeed((v) => !v)}
                            className={`absolute top-2 left-2 px-2 py-0.5 rounded text-[9px] font-mono font-bold border transition ${
                              showTagFeed
                                ? "bg-fuchsia-600/30 text-fuchsia-300 border-fuchsia-400/50"
                                : "bg-black/60 text-gray-300 border-white/20 hover:text-white hover:border-white/40"
                            }`}
                            title="Overlay live AprilTag detection to diagnose tag/backend issues"
                          >
                            {showTagFeed ? "● LIVE TAG FEED" : "LIVE TAG FEED"}
                          </button>
                          <div className="absolute top-2 right-2 px-2 py-0.5 bg-black/60 rounded text-[9px] font-mono text-neon border border-neon/20 animate-pulse">
                            {showTagFeed ? "TAG DEBUG" : "LIVE FEED"}
                          </div>
                        </div>

                        {/* Digital Zoom Slider */}
                        <div className="space-y-1.5 p-3 bg-white/2 border border-white/5 rounded-lg">
                          <div className="flex justify-between text-[10px] font-mono text-gray-400">
                            <span>DIGITAL FEED ZOOM:</span>
                            <span className="text-neon font-bold">{zoomFactor.toFixed(1)}x</span>
                          </div>
                          <input
                            type="range"
                            min="1.0"
                            max="3.0"
                            step="0.1"
                            value={zoomFactor}
                            onChange={handleZoomChange}
                            className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-neon focus:outline-none"
                            style={{
                              accentColor: "#10b981"
                            }}
                          />
                        </div>
                      </div>
                    )}

                    {/* Calibration & Monitoring Actions */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
                      
                      {/* Calibrate target on wall */}
                      <button
                        onClick={() => handleCalibrate(false)}
                        disabled={!isCameraActive || isCalibrating || (userRole !== "technician" && userRole !== "instructor")}
                        className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 ${
                          !isCameraActive || (userRole !== "technician" && userRole !== "instructor")
                            ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed"
                            : "border-white/10 bg-white/2 hover:bg-white/3 text-white"
                        }`}
                      >
                        <div className="mb-2">
                          <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1">
                            1. Calibrate Target
                          </h4>
                          <p className="text-[9px] text-gray-500 leading-tight">
                            Place target sheet on the wall, then auto-detect corners and lock perspective homography mapping.
                          </p>
                        </div>
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 bg-white/5 border border-white/10 rounded mt-2">
                          {isCalibrating ? "ANALYZING..." : (userRole !== "technician" && userRole !== "instructor") ? "🔒 TECHNICIAN ONLY" : "CALIBRATE"}
                        </span>
                      </button>

                      {/* Calibrate target on wall - Contour Only */}
                      <button
                        onClick={() => handleCalibrate(true)}
                        disabled={!isCameraActive || isCalibrating || (userRole !== "technician" && userRole !== "instructor")}
                        className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 ${
                          !isCameraActive || (userRole !== "technician" && userRole !== "instructor")
                            ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed"
                            : "border-orange-500/25 bg-orange-500/5 hover:bg-orange-500/10 text-white"
                        }`}
                      >
                        <div className="mb-2">
                          <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-orange-400">
                            1b. Contour Calibrate
                          </h4>
                          <p className="text-[9px] text-gray-500 leading-tight">
                            Bypass AprilTag detection. Direct detection of target paper outer boundaries using contours.
                          </p>
                        </div>
                        <span className="text-[10px] font-mono font-bold px-2 py-0.5 bg-orange-600/20 border border-orange-500/30 text-orange-400 rounded mt-2 animate-pulse">
                          {isCalibrating ? "ANALYZING..." : (userRole !== "technician" && userRole !== "instructor") ? "🔒 TECHNICIAN ONLY" : "CONTOUR CALIBRATE"}
                        </span>
                      </button>

                      {/* Capture Before Fire (Reference image) */}
                      <button
                        onClick={handleBeforeFire}
                        disabled={!isCameraActive || isCapturingBeforeFire}
                        className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 ${
                          !isCameraActive
                            ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed"
                            : "border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/10 text-white"
                        }`}
                      >
                        <div className="mb-2">
                          <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-blue-400">
                            2. Before Fire
                          </h4>
                          <p className="text-[9px] text-gray-500 leading-tight">
                            Click before firing shots. Takes a pristine snapshot to serve as the reference for differencing.
                          </p>
                        </div>
                        <span className="text-[10px] font-mono font-bold px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded mt-2">
                          {isCapturingBeforeFire ? "CAPTURING..." : "📷 BEFORE FIRE"}
                        </span>
                      </button>
     
                      {/* Fired snapshot trigger */}
                      <button
                        onClick={handleFire}
                        disabled={!isCameraActive || !baselineUrl || isDetecting}
                        className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition min-h-[8.5rem] pb-3 ${
                          !isCameraActive || !baselineUrl
                            ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed"
                            : "border-red-500/20 bg-red-500/5 hover:bg-red-500/10 text-white"
                        }`}
                      >
                        <div className="mb-2">
                          <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-red-400">
                            3. Trigger Fired
                          </h4>
                          <p className="text-[9px] text-gray-500 leading-tight">
                            Click after firing a shot. Snaps the live camera feed and compares it against the "Before Fire" baseline.
                          </p>
                        </div>
                        <span className="text-[10px] font-mono font-bold px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded mt-2">
                          {isDetecting ? "ANALYZING IMPACT..." : "🔥 TRIGGER FIRED"}
                        </span>
                      </button>
     
                    </div>

                    {/* Manual file upload fallback */}
                    {(userRole === "technician" || userRole === "instructor") && (
                      <div className="border-t border-white/5 pt-3 mt-3 flex flex-wrap justify-between items-center gap-2 text-[10px] font-mono text-gray-500 font-mono">
                        <span className="whitespace-nowrap">MANUAL FILE UPLOADS:</span>
                        <div className="flex items-center gap-2 flex-wrap">
                          <label className="text-neon hover:underline cursor-pointer whitespace-nowrap">
                            UPLOAD BASE
                            <input
                              type="file"
                              accept="image/*"
                              onChange={handleBaselineUpload}
                              className="hidden"
                            />
                          </label>
                          <span>|</span>
                          <label className={`text-neon hover:underline cursor-pointer whitespace-nowrap ${!baselineUrl ? "pointer-events-none opacity-40" : ""}`}>
                            ANALYZE FILE
                            <input
                              type="file"
                              accept="image/*"
                              onChange={handleDetectUpload}
                              className="hidden"
                              disabled={!baselineUrl}
                            />
                          </label>
                        </div>
                      </div>
                    )}

                  </div>
                )}
              </div>
            </div>

            {/* Original Layout (Technician/Instructor View) - Right Column: col-span-7 */}
            <div className="xl:col-span-7 flex flex-col gap-6">
              <OverviewCards />

              {/* Shooter Roster - Only for Instructor in Session Tab */}
              {userRole === "instructor" && (
                <div className="glass-panel p-5 flex flex-col gap-4 animate-fade-in">
                  <div className="flex items-center justify-between border-b border-white/5 pb-2">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-indigo-400" />
                      <h3 className="text-xs font-mono font-bold text-white uppercase tracking-wider">
                        Shooter Roster {activeSession?.unit_number ? `(Unit: ${activeSession.unit_number})` : ""}
                      </h3>
                    </div>
                    <span className="text-[9px] font-mono text-gray-500 uppercase">Select a shooter to monitor target</span>
                  </div>

                  {!activeSession ? (
                    <div className="text-xs font-mono text-gray-500 py-2">
                      Initialize a shooting session to view and monitor shooters.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {getUnitCandidates(activeSession.unit_number).map((shooter) => {
                        return (
                          <div 
                            key={shooter.id}
                            className="bg-[#030712]/60 border border-white/5 rounded-lg p-3 flex flex-col justify-between gap-3 hover:border-indigo-500/25 transition-all duration-150"
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex items-center gap-2">
                                <div className="w-7 h-7 rounded-full bg-indigo-950/50 border border-indigo-500/20 flex items-center justify-center text-xs font-mono font-bold text-indigo-300">
                                  {shooter.name.split("-").pop() || "S"}
                                </div>
                                <div>
                                  <h4 className="text-xs font-bold text-white font-mono">{shooter.name}</h4>
                                  <p className="text-[8px] text-gray-500 font-mono mt-0.5">ID: {shooter.id}</p>
                                </div>
                              </div>
                              <span className={`text-[8px] font-mono font-bold px-1.5 py-0.5 rounded ${
                                shooter.status === "Active"
                                  ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 animate-pulse"
                                  : shooter.status === "Ready"
                                  ? "bg-cyan-500/10 border border-cyan-500/20 text-cyan-400"
                                  : "bg-gray-500/10 border border-white/5 text-gray-400"
                              }`}>
                                {shooter.status.toUpperCase()}
                              </span>
                            </div>

                            <div className="flex justify-between items-center text-[9px] font-mono text-gray-400 border-t border-white/5 pt-2">
                              <span>Last Shot: <span className="text-white font-bold">{shooter.status === "Active" ? "9.8 pts" : "N/A"}</span></span>
                              <button
                                type="button"
                                onClick={() => setActiveShooterCandidate(shooter)}
                                className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded text-[9px] uppercase transition duration-150"
                              >
                                Monitor
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Session Details Container */}
              <div className="glass-panel p-6 flex flex-col flex-1 h-fit">
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center w-full mb-4 border-b border-white/5 pb-3 gap-3">
                  <div className="leading-tight">
                    <h3 className="text-sm font-bold font-mono tracking-wider uppercase text-white">Session Details</h3>
                    <p className="text-[10px] text-gray-500 font-mono mt-0.5">Confirmed Shots, Candidates, Statistical metrics</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
                    <button
                      type="button"
                      onClick={() => setSessionDetailsTab("shots")}
                      className={`px-3 py-1.5 rounded-lg border transition font-bold ${
                        sessionDetailsTab === "shots"
                          ? "bg-neon/15 border-neon text-neon"
                          : "bg-white/2 border-white/10 text-gray-400 hover:text-white hover:bg-white/5"
                      }`}
                    >
                      Confirmed Shots
                    </button>
                    <button
                      type="button"
                      onClick={() => setSessionDetailsTab("candidates")}
                      className={`px-3 py-1.5 rounded-lg border transition font-bold ${
                        sessionDetailsTab === "candidates"
                          ? "bg-neon/15 border-neon text-neon"
                          : "bg-white/2 border-white/10 text-gray-400 hover:text-white hover:bg-white/5"
                      }`}
                    >
                      Candidates
                    </button>
                    <button
                      type="button"
                      onClick={() => setSessionDetailsTab("stats")}
                      className={`px-3 py-1.5 rounded-lg border transition font-bold ${
                        sessionDetailsTab === "stats"
                          ? "bg-neon/15 border-neon text-neon"
                          : "bg-white/2 border-white/10 text-gray-400 hover:text-white hover:bg-white/5"
                      }`}
                    >
                      Statistical Metrics
                    </button>
                  </div>
                </div>

                <div className="flex-1">
                  {sessionDetailsTab === "shots" && <ShotTable forceMode="shots" />}
                  {sessionDetailsTab === "candidates" && <ShotTable forceMode="candidates" />}
                  {sessionDetailsTab === "stats" && <StatsPanel noBorder />}
                </div>
              </div>

              {/* Telemetry Log Console */}
              {userRole === "technician" && (
                <div className="glass-panel p-5">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3 border-b border-white/5 pb-2">
                    <div className="flex items-center gap-2 text-gray-400">
                      <Terminal className="w-4 h-4 text-neon" />
                      <span className="text-xs font-mono tracking-wider uppercase font-bold text-white">System Console Log</span>
                    </div>
                    <span className="text-[9px] font-mono text-gray-500 uppercase whitespace-nowrap">SYS_LOGS // STDOUT</span>
                  </div>
                  
                  <div className="h-24 overflow-y-auto font-mono text-[10px] text-emerald-500/80 space-y-1.5 scrollbar-thin">
                    {logs.length === 0 ? (
                      <p className="text-gray-600">Console idle. Awaiting user interaction...</p>
                    ) : (
                      logs.map((log, index) => (
                        <p key={index} className="leading-relaxed whitespace-pre-wrap">
                          {log}
                        </p>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* New Session Modal Overlay */}
       {showCreateModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/70 backdrop-blur-md z-50 p-4 animate-fade-in">
          <div className={`glass-panel w-full max-h-[90vh] overflow-y-auto p-6 border-white/10 relative scrollbar-thin transition-all duration-300 ${
            setupStep === 3 ? "max-w-4xl" : "max-w-md"
          }`}>
            
            {/* Header */}
            <div className="flex justify-between items-center mb-4 pb-3 border-b border-white/5">
              <h3 className="text-base font-bold font-mono tracking-wider uppercase text-white">
                {setupStep === 1 && "Step 1: Session Details"}
                {setupStep === 2 && "Step 2: Unit Personnel Loaded"}
                {setupStep === 3 && "Step 3: Lane Assignments"}
              </h3>
              
              {/* Step indicator */}
              <div className="flex items-center gap-1.5 font-mono text-[10px]">
                <span className={`px-2 py-0.5 rounded ${setupStep === 1 ? "bg-indigo-600 text-white font-bold" : "bg-white/5 text-gray-500"}`}>1</span>
                <span className="text-gray-600">/</span>
                <span className={`px-2 py-0.5 rounded ${setupStep === 2 ? "bg-indigo-600 text-white font-bold" : "bg-white/5 text-gray-500"}`}>2</span>
                <span className="text-gray-600">/</span>
                <span className={`px-2 py-0.5 rounded ${setupStep === 3 ? "bg-indigo-600 text-white font-bold" : "bg-white/5 text-gray-500"}`}>3</span>
              </div>
            </div>

            {/* STEP 1: SESSION DETAILS */}
            {setupStep === 1 && (
              <form onSubmit={handleCreateSessionWizardStep1} className="space-y-4">
                {/* Row 1: Unit Number & Date/Time */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-[10px] font-mono uppercase text-gray-400">Unit Number</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. 3B"
                      value={newSessionUnitNumber}
                      onChange={(e) => setNewSessionUnitNumber(e.target.value)}
                      className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] font-mono uppercase text-gray-400">Date & Time</label>
                    <input
                      type="datetime-local"
                      required
                      value={newSessionDate}
                      onChange={(e) => setNewSessionDate(e.target.value)}
                      className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    />
                  </div>
                </div>

                {/* Row 2: Target Type */}
                <div className="space-y-1">
                  <label className="text-[10px] font-mono uppercase text-gray-400">Target Type</label>
                  <select
                    value={newSessionTargetType}
                    onChange={(e) => setNewSessionTargetType(e.target.value)}
                    className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                  >
                    {targetDefinitions.map((target) => (
                      <option key={target.id} value={target.id}>
                        {target.name} ({target.width_mm}x{target.height_mm} mm)
                      </option>
                    ))}
                    {targetDefinitions.length === 0 && (
                      <>
                        <option value="figure_eleven">Figure Eleven (580x885 mm)</option>
                        <option value="issf_10m_air_rifle">ISSF 10m Air Rifle (80x80 mm)</option>
                        <option value="real_figure_11">Real Figure 11 (580x885 mm)</option>
                      </>
                    )}
                  </select>
                </div>

                {/* Target Preview */}
                <div className="space-y-1">
                  <label className="text-[10px] font-mono uppercase text-gray-400">Target Preview</label>
                  <TargetPreview 
                    target={
                      targetDefinitions.find(t => t.id === newSessionTargetType) || 
                      (newSessionTargetType === "figure_eleven" ? {
                        name: "Figure Eleven",
                        width_mm: 580.0,
                        height_mm: 885.0,
                        bullseyes: [],
                        scoring_regions: [
                          { id: 1, name: "Outer Torso", value: 4, x_min_mm: 40.0, y_min_mm: 42.5, x_max_mm: 540.0, y_max_mm: 842.5 },
                          { id: 2, name: "Inner Center", value: 5, x_min_mm: 190.0, y_min_mm: 292.5, x_max_mm: 390.0, y_max_mm: 592.5 }
                        ],
                        bullet_compatibility: ["5.56", "7.62", "9.0"],
                        decimal_scoring_supported: false
                      } : newSessionTargetType === "issf_10m_air_rifle" ? {
                        name: "ISSF 10m Air Rifle",
                        width_mm: 80.0,
                        height_mm: 80.0,
                        bullseyes: [{
                          id: 1, center_x_mm: 40, center_y_mm: 40, scoring_rule: "inward",
                          rings: [
                            { value: 10, outer_radius_mm: 0.25 },
                            { value: 9, outer_radius_mm: 2.75 },
                            { value: 8, outer_radius_mm: 5.25 },
                            { value: 7, outer_radius_mm: 7.75 },
                            { value: 6, outer_radius_mm: 10.25 },
                            { value: 5, outer_radius_mm: 12.75 },
                            { value: 4, outer_radius_mm: 15.25 },
                            { value: 3, outer_radius_mm: 17.75 },
                            { value: 2, outer_radius_mm: 20.25 },
                            { value: 1, outer_radius_mm: 22.75 }
                          ]
                        }],
                        bullet_compatibility: ["5.56", "7.62", "9.0"],
                        decimal_scoring_supported: true
                      } : {
                        name: "Real Figure 11",
                        width_mm: 580.0,
                        height_mm: 885.0,
                        bullseyes: [],
                        scoring_regions: [
                          { id: 1, name: "Outer Torso", value: 4, x_min_mm: 40.0, y_min_mm: 42.5, x_max_mm: 540.0, y_max_mm: 842.5 },
                          { id: 2, name: "Inner Center", value: 5, x_min_mm: 190.0, y_min_mm: 292.5, x_max_mm: 390.0, y_max_mm: 592.5 }
                        ],
                        bullet_compatibility: ["5.56", "7.62", "9.0"],
                        decimal_scoring_supported: false
                      })
                    }
                    className="h-32 w-full"
                  />
                </div>

                {/* Range & Drill Type */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-[10px] font-mono uppercase text-gray-400">Range</label>
                    <select
                      value={newSessionRange}
                      onChange={(e) => setNewSessionRange(e.target.value)}
                      className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    >
                      <option value="25m">25m</option>
                      <option value="50m">50m</option>
                      <option value="75m">75m</option>
                      <option value="100m">100m</option>
                      <option value="200m">200m</option>
                      <option value="300m">300m</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] font-mono uppercase text-gray-400">Drill Type</label>
                    <select
                      value={newSessionDrillType}
                      onChange={(e) => setNewSessionDrillType(e.target.value)}
                      className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    >
                      <option value="Stationary">Stationary</option>
                      <option value="Moving">Moving</option>
                      <option value="Dynamic">Dynamic</option>
                    </select>
                  </div>
                </div>

                {/* Rounds Per Shooter & Caliber */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-[10px] font-mono uppercase text-gray-400">Rounds Per Shooter</label>
                    <input
                      type="number"
                      required
                      min="1"
                      max="100"
                      value={newSessionBulletsPerDrill}
                      onChange={(e) => setNewSessionBulletsPerDrill(parseInt(e.target.value) || 5)}
                      className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-[10px] font-mono uppercase text-gray-400">Caliber</label>
                    <select
                      value={newSessionBulletCaliber}
                      onChange={(e) => setNewSessionBulletCaliber(parseFloat(e.target.value))}
                      className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    >
                      <option value="5.56">5.56 mm</option>
                      <option value="7.62">7.62 mm</option>
                      <option value="9.0">9.0 mm</option>
                    </select>
                  </div>
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setShowCreateModal(false);
                      setSetupStep(1);
                    }}
                    className="px-4 py-2 border border-white/10 hover:bg-white/5 rounded text-xs font-mono text-gray-400 hover:text-white transition"
                  >
                    CANCEL
                  </button>
                  <button
                    type="submit"
                    className="px-5 py-2 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-mono text-xs font-bold rounded shadow-lg active:scale-95 transition"
                  >
                    CONTINUE
                  </button>
                </div>
              </form>
            )}

            {/* STEP 2: UNIT PERSONNEL */}
            {setupStep === 2 && (
              <div className="space-y-5">
                <div className="p-4 bg-white/2 border border-white/5 rounded-xl space-y-2 font-mono">
                  <div className="flex justify-between items-center text-xs border-b border-white/5 pb-2">
                    <span className="text-gray-400 uppercase">Unit:</span>
                    <span className="text-white font-bold">{createdUnitNumber}</span>
                  </div>
                  <div className="flex justify-between items-center text-xs pt-1">
                    <span className="text-gray-400 uppercase">Personnel Count:</span>
                    <span className="text-neon font-bold">{unitPersonnel.length}</span>
                  </div>
                </div>

                <div className="space-y-1.5">
                  <h4 className="text-[10px] font-mono uppercase text-gray-400 tracking-wider">Personnel Roster:</h4>
                  <div className="bg-[#030712] border border-white/10 rounded-lg p-3 max-h-[250px] overflow-y-auto font-mono text-xs text-gray-300 divide-y divide-white/5 scrollbar-thin">
                    {unitPersonnel.map((person) => (
                      <div key={person.id} className="py-2 flex justify-between items-center">
                        <span className="text-white font-semibold">{person.name}</span>
                        <span className="text-gray-500 text-[10px]">ID: {person.id}</span>
                      </div>
                    ))}
                    {unitPersonnel.length === 0 && (
                      <p className="text-center py-6 text-gray-500">No personnel registered for this unit.</p>
                    )}
                  </div>
                </div>

                <div className="flex justify-between gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setSetupStep(1)}
                    className="px-4 py-2 border border-white/10 hover:bg-white/5 rounded text-xs font-mono text-gray-400 hover:text-white transition"
                  >
                    BACK
                  </button>
                  <button
                    type="button"
                    onClick={() => setSetupStep(3)}
                    className="px-5 py-2 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-mono text-xs font-bold rounded shadow-lg active:scale-95 transition"
                  >
                    CONTINUE TO LANE ASSIGNMENT
                  </button>
                </div>
              </div>
            )}

            {/* STEP 3: LANE ASSIGNMENTS */}
            {setupStep === 3 && (
              <div className="space-y-6">
                
                {/* Summary Bar */}
                <div className="grid grid-cols-3 gap-4 text-center font-mono text-[10.5px]">
                  <div className="bg-emerald-950/20 border border-emerald-500/20 rounded-xl py-2 px-3">
                    <span className="block text-[8px] text-emerald-400 uppercase tracking-wider mb-0.5">Assigned Shooters</span>
                    <span className="text-white font-extrabold text-sm">{Object.keys(laneAssignments).length}</span>
                  </div>
                  <div className="bg-white/2 border border-white/5 rounded-xl py-2 px-3">
                    <span className="block text-[8px] text-gray-500 uppercase tracking-wider mb-0.5">Empty Lanes</span>
                    <span className="text-white font-extrabold text-sm">{20 - Object.keys(laneAssignments).length}</span>
                  </div>
                  <div className="bg-indigo-950/20 border border-indigo-500/20 rounded-xl py-2 px-3">
                    <span className="block text-[8px] text-indigo-400 uppercase tracking-wider mb-0.5">Unassigned</span>
                    <span className="text-white font-extrabold text-sm">{unitPersonnel.length - Object.keys(laneAssignments).length}</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-stretch min-h-[400px]">
                  
                  {/* Left Column: Available Shooters */}
                  <div className="md:col-span-4 flex flex-col gap-3 p-4 bg-[#030712]/50 border border-white/5 rounded-xl">
                    <div className="leading-tight">
                      <h4 className="text-xs font-bold font-mono text-white uppercase tracking-wider">AVAILABLE SHOOTERS</h4>
                      <p className="text-[9px] text-gray-500 font-mono mt-0.5">Roster of shooters who can be assigned</p>
                    </div>

                    {/* Search input */}
                    <input
                      type="text"
                      placeholder="🔍 Search name..."
                      value={availableShootersSearch}
                      onChange={(e) => setAvailableShootersSearch(e.target.value)}
                      className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    />

                    {/* Scrollable list */}
                    <div className="flex-1 max-h-[300px] overflow-y-auto space-y-1.5 scrollbar-thin pr-1">
                      {unitPersonnel
                        .filter(p => !Object.values(laneAssignments).some(a => a.id === p.id))
                        .filter(p => p.name.toLowerCase().includes(availableShootersSearch.toLowerCase()))
                        .map(p => (
                          <div key={p.id} className="p-2 bg-white/2 hover:bg-white/5 border border-white/5 rounded-lg flex justify-between items-center text-xs font-mono group transition">
                            <div className="flex flex-col min-w-0">
                              <span className="text-white font-semibold truncate">{p.name}</span>
                              <span className="text-gray-500 text-[9px]">ID: {p.id}</span>
                            </div>
                            {assigningLane !== null && (
                              <button
                                onClick={() => {
                                  setLaneAssignments({ ...laneAssignments, [assigningLane]: p });
                                  setAssigningLane(null);
                                }}
                                className="px-2 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[10px] font-bold active:scale-95 transition"
                              >
                                ASSIGN
                              </button>
                            )}
                          </div>
                        ))}
                      {unitPersonnel.filter(p => !Object.values(laneAssignments).some(a => a.id === p.id)).length === 0 && (
                        <p className="text-center py-10 text-xs text-gray-500 font-mono">No available shooters.</p>
                      )}
                    </div>
                  </div>

                  {/* Right Column: Lane Table */}
                  <div className="md:col-span-8 flex flex-col p-4 bg-[#030712]/30 border border-white/5 rounded-xl">
                    <div className="leading-tight mb-3">
                      <h4 className="text-xs font-bold font-mono text-white uppercase tracking-wider">LANE ASSIGNMENT TABLE</h4>
                      <p className="text-[9px] text-gray-500 font-mono mt-0.5">Assign personnel to physical lanes (1-20)</p>
                    </div>

                    <div className="flex-1 max-h-[350px] overflow-y-auto border border-white/5 rounded-lg scrollbar-thin">
                      <table className="w-full border-collapse font-mono text-[11px] text-left">
                        <thead>
                          <tr className="bg-white/2 text-gray-400 font-bold border-b border-white/5">
                            <th className="py-2.5 px-4 text-center w-16">Lane</th>
                            <th className="py-2.5 px-3 w-20">Target</th>
                            <th className="py-2.5 px-4">Assigned Shooter</th>
                            <th className="py-2.5 px-4 text-right w-24">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {Array.from({ length: 20 }, (_, i) => {
                            const laneNum = i + 1;
                            const targetId = `T${laneNum.toString().padStart(2, '0')}`;
                            const assigned = laneAssignments[laneNum];
                            
                            return (
                              <tr key={laneNum} className={`hover:bg-white/2 transition ${assigningLane === laneNum ? "bg-indigo-600/10" : ""}`}>
                                <td className="py-2 px-4 text-center font-bold text-gray-300">
                                  {laneNum.toString().padStart(2, '0')}
                                </td>
                                <td className="py-2 px-3 text-indigo-400 font-bold">
                                  {targetId}
                                </td>
                                <td className="py-2 px-4">
                                  {assigned ? (
                                    <span className="text-white font-bold">{assigned.name}</span>
                                  ) : (
                                    <span className="text-gray-500 italic">Empty</span>
                                  )}
                                </td>
                                <td className="py-2 px-4 text-right">
                                  {assigned ? (
                                    <button
                                      onClick={() => {
                                        const nextAssignments = { ...laneAssignments };
                                        delete nextAssignments[laneNum];
                                        setLaneAssignments(nextAssignments);
                                      }}
                                      className="px-2 py-0.5 bg-rose-950/40 border border-rose-500/30 text-rose-400 hover:bg-rose-900/40 rounded text-[9px] font-bold active:scale-95 transition"
                                    >
                                      REMOVE
                                    </button>
                                  ) : (
                                    <button
                                      onClick={() => setAssigningLane(laneNum)}
                                      className={`px-2 py-0.5 rounded text-[9px] font-bold active:scale-95 transition ${
                                        assigningLane === laneNum
                                          ? "bg-amber-600 text-white animate-pulse"
                                          : "bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10"
                                      }`}
                                    >
                                      {assigningLane === laneNum ? "SELECTING..." : "ASSIGN"}
                                    </button>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                </div>

                <div className="flex justify-between items-center pt-2 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => {
                      setSetupStep(2);
                      setAssigningLane(null);
                    }}
                    className="px-4 py-2 border border-white/10 hover:bg-white/5 rounded text-xs font-mono text-gray-400 hover:text-white transition"
                  >
                    BACK
                  </button>
                  
                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        setShowCreateModal(false);
                        setSetupStep(1);
                        setAssigningLane(null);
                      }}
                      className="px-4 py-2 border border-white/10 hover:bg-white/5 rounded text-xs font-mono text-gray-400 hover:text-white transition"
                    >
                      CANCEL
                    </button>
                    <button
                      type="button"
                      disabled={Object.keys(laneAssignments).length < 1 || isSavingAssignments}
                      onClick={handleStartSessionWizard}
                      className="px-5 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-mono text-xs font-bold rounded shadow-lg active:scale-95 transition"
                    >
                      {isSavingAssignments ? "STARTING..." : "START SESSION"}
                    </button>
                  </div>
                </div>

              </div>
            )}

            {/* ASSIGNMENT MODAL OVERLAY (Mini overlay when user clicks ASSIGN from lane row) */}
            {assigningLane !== null && (
              <div className="fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm z-50 p-4">
                <div className="glass-panel max-w-sm w-full p-5 border-white/10 space-y-4">
                  <div className="flex justify-between items-center border-b border-white/5 pb-2">
                    <h4 className="text-sm font-bold font-mono text-white uppercase">
                      Assign Shooter (Lane {assigningLane.toString().padStart(2, '0')})
                    </h4>
                    <button 
                      onClick={() => setAssigningLane(null)} 
                      className="text-gray-400 hover:text-white font-bold"
                    >
                      ✕
                    </button>
                  </div>

                  <div className="space-y-3">
                    <input
                      type="text"
                      placeholder="🔍 Filter available..."
                      value={availableShootersSearch}
                      onChange={(e) => setAvailableShootersSearch(e.target.value)}
                      className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    />

                    <div className="max-h-[220px] overflow-y-auto space-y-1.5 scrollbar-thin">
                      {unitPersonnel
                        .filter(p => !Object.values(laneAssignments).some(a => a.id === p.id))
                        .filter(p => p.name.toLowerCase().includes(availableShootersSearch.toLowerCase()))
                        .map(p => (
                          <div
                            key={p.id}
                            onClick={() => {
                              setLaneAssignments({ ...laneAssignments, [assigningLane]: p });
                              setAssigningLane(null);
                            }}
                            className="p-2.5 bg-white/2 hover:bg-indigo-600/25 border border-white/5 rounded-lg flex justify-between items-center text-xs font-mono cursor-pointer transition"
                          >
                            <span className="text-white font-bold">{p.name}</span>
                            <span className="text-gray-500 text-[10px]">ID: {p.id}</span>
                          </div>
                        ))}
                      {unitPersonnel.filter(p => !Object.values(laneAssignments).some(a => a.id === p.id)).length === 0 && (
                        <p className="text-center py-6 text-xs text-gray-500 font-mono">No available shooters matching.</p>
                      )}
                    </div>
                  </div>

                  <div className="flex justify-end pt-2">
                    <button
                      onClick={() => setAssigningLane(null)}
                      className="px-4 py-1.5 border border-white/10 hover:bg-white/5 rounded text-xs font-mono text-gray-400 hover:text-white transition"
                    >
                      CANCEL
                    </button>
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
       )}

      {/* New Target Modal Overlay */}
      {showCreateTargetModal && (() => {
        const canvasDisplayWidth = 320;
        const aspect = customTargetWidth > 0 ? (customTargetHeight / customTargetWidth) : 1.0;
        let finalWidth = canvasDisplayWidth;
        let finalHeight = canvasDisplayWidth * aspect;
        if (finalHeight > 420) {
          finalHeight = 420;
          finalWidth = aspect > 0 ? (finalHeight / aspect) : canvasDisplayWidth;
        }

        return (
          <div className="fixed inset-0 flex items-center justify-center bg-black/75 backdrop-blur-md z-50 p-4">
            <div className="glass-panel max-w-5xl w-full max-h-[95vh] overflow-y-auto p-6 border-white/10 relative scrollbar-thin">
              <h3 className="text-base font-bold font-mono tracking-wider uppercase mb-4 text-white">
                Target Designer Studio
              </h3>
              
              <form onSubmit={handleCreateTarget} className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
                  {/* Left Column: Configuration Settings */}
                  <div className="md:col-span-7 space-y-4">
                    <div className="space-y-1">
                      <label className="text-[10px] font-mono uppercase text-gray-400">Target Name</label>
                      <input
                        type="text"
                        required
                        placeholder="e.g. Tactical Pistol 25m"
                        value={customTargetName}
                        onChange={(e) => setCustomTargetName(e.target.value)}
                        className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <label className="text-[10px] font-mono uppercase text-gray-400">Width (mm)</label>
                        <input
                          type="number"
                          step="0.1"
                          min="10"
                          required
                          value={customTargetWidth}
                          onChange={(e) => setCustomTargetWidth(parseFloat(e.target.value) || 0)}
                          className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-[10px] font-mono uppercase text-gray-400">Height (mm)</label>
                        <input
                          type="number"
                          step="0.1"
                          min="10"
                          required
                          value={customTargetHeight}
                          onChange={(e) => setCustomTargetHeight(parseFloat(e.target.value) || 0)}
                          className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                        />
                      </div>
                    </div>

                    {/* AprilTag Physical Configurations */}
                    <div className="space-y-1">
                      <label className="text-[10px] font-mono uppercase text-gray-400">AprilTag Real Size (mm)</label>
                      <input
                        type="number"
                        step="0.1"
                        min="1"
                        required
                        value={customTargetTagSizeMm}
                        onChange={(e) => setCustomTargetTagSizeMm(parseFloat(e.target.value) || 50.0)}
                        className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                      />
                    </div>

                    {/* Target Image Preview Uploader */}
                    <div className="space-y-1.5 border-t border-white/5 pt-3">
                      <label className="text-[10px] font-mono uppercase text-gray-400 block">Upload Soft Copy Image (Target Preview)</label>
                      <div className="flex items-center gap-3">
                        <input
                          type="file"
                          accept="image/*"
                          onChange={handlePreviewImageChange}
                          className="text-xs font-mono text-gray-500 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-mono file:bg-white/5 file:text-gray-300 hover:file:bg-white/10 file:cursor-pointer"
                        />
                      </div>
                    </div>

                    {/* Zone Value Editor List */}
                    {customTargetType === "circular" ? (
                      <div className="space-y-2 border-t border-white/5 pt-3">
                        <label className="text-[10px] font-mono uppercase text-gray-400 block">Circular Rings list (Sorted by radius)</label>
                        <div className="max-h-[180px] overflow-y-auto space-y-2 pr-1 scrollbar-thin">
                          {customTargetRings.map((ring, idx) => (
                            <div key={idx} className="flex items-center gap-2 bg-white/2 p-2 rounded border border-white/2">
                              <span className="text-[10px] font-mono text-gray-500 min-w-[50px] font-bold">Ring {idx + 1}</span>
                              <div className="flex items-center gap-1.5 flex-1">
                                <label className="text-[8px] font-mono text-gray-500 uppercase">Val:</label>
                                <input
                                  type="number"
                                  min="0"
                                  value={ring.value}
                                  onChange={(e) => handleRingChange(idx, "value", parseInt(e.target.value) || 0)}
                                  className="w-12 bg-[#030712] border border-white/10 rounded px-1.5 py-0.5 text-center text-xs font-mono text-white focus:outline-none"
                                />
                              </div>
                              <div className="flex items-center gap-1.5 flex-1">
                                <label className="text-[8px] font-mono text-gray-500 uppercase">Rad (mm):</label>
                                <input
                                  type="number"
                                  step="0.05"
                                  min="0.1"
                                  value={ring.outer_radius_mm}
                                  onChange={(e) => handleRingChange(idx, "outer_radius_mm", parseFloat(e.target.value) || 0)}
                                  className="w-18 bg-[#030712] border border-white/10 rounded px-1.5 py-0.5 text-center text-xs font-mono text-white focus:outline-none"
                                />
                              </div>
                              <button
                                type="button"
                                onClick={() => handleRemoveRing(idx)}
                                className="p-1 text-red-500 hover:text-red-400 hover:bg-red-500/10 rounded"
                                disabled={customTargetRings.length <= 1}
                              >
                                <Trash className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))}
                          {customTargetRings.length === 0 && (
                            <p className="text-[10px] font-mono text-gray-500 text-center py-2">No rings added yet. Draw them on the canvas.</p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2 border-t border-white/5 pt-3">
                        <label className="text-[10px] font-mono uppercase text-gray-400 block">Rectangular Zones list</label>
                        <div className="max-h-[180px] overflow-y-auto space-y-2 pr-1 scrollbar-thin">
                          {customTargetRegions.map((region) => (
                            <div key={region.id} className="flex items-center gap-2 bg-white/2 p-2 rounded border border-white/2">
                              <input
                                type="text"
                                value={region.name}
                                onChange={(e) => handleRegionChange(region.id, "name", e.target.value)}
                                className="bg-[#030712] border border-white/10 rounded px-1.5 py-0.5 text-xs font-mono text-white focus:outline-none w-24"
                              />
                              <div className="flex items-center gap-1.5 flex-1">
                                <label className="text-[8px] font-mono text-gray-500 uppercase">Val:</label>
                                <input
                                  type="number"
                                  value={region.value}
                                  onChange={(e) => handleRegionChange(region.id, "value", parseInt(e.target.value) || 0)}
                                  className="w-10 bg-[#030712] border border-white/10 rounded px-1 py-0.5 text-center text-xs font-mono text-white focus:outline-none"
                                />
                              </div>
                              <span className="text-[8px] font-mono text-gray-500">
                                {region.x_min_mm},{region.y_min_mm} to {region.x_max_mm},{region.y_max_mm} mm
                              </span>
                              <button
                                type="button"
                                onClick={() => handleRemoveRegion(region.id)}
                                className="p-1 text-red-500 hover:text-red-400 hover:bg-red-500/10 rounded"
                              >
                                <Trash className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          ))}
                          {customTargetRegions.length === 0 && (
                            <p className="text-[10px] font-mono text-gray-500 text-center py-2">No zones added yet. Click and drag on the canvas to draw.</p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right Column: Interactive Canvas Editor */}
                  <div className="md:col-span-5 flex flex-col items-center justify-start bg-white/2 border border-white/5 rounded-lg p-4 space-y-4 min-h-[480px]">
                    <div className="text-center w-full">
                      <h4 className="text-xs font-bold font-mono text-neon uppercase tracking-wider">Canvas Zone Designer</h4>
                      
                      {/* Zone Drawing Mode Selector */}
                      <div className="flex gap-2 justify-center mt-2 mb-1">
                        <button
                          type="button"
                          onClick={() => setCustomTargetType("rectangular")}
                          className={`px-3 py-1 text-[9px] font-mono font-bold rounded transition-all ${
                            customTargetType === "rectangular"
                              ? "bg-indigo-600 text-white"
                              : "bg-white/5 text-gray-400 hover:text-white border border-white/10"
                          }`}
                        >
                          Rectangular Zones
                        </button>
                        <button
                          type="button"
                          onClick={() => setCustomTargetType("circular")}
                          className={`px-3 py-1 text-[9px] font-mono font-bold rounded transition-all ${
                            customTargetType === "circular"
                              ? "bg-indigo-600 text-white"
                              : "bg-white/5 text-gray-400 hover:text-white border border-white/10"
                          }`}
                        >
                          Circular Rings
                        </button>
                      </div>

                      <p className="text-[9px] text-gray-400 mt-1">
                        {customTargetType === "circular" 
                          ? "Drag red crosshair to relocate target center. Drag outward from center to define ring boundaries."
                          : "Draw rectangular score zones by clicking and dragging directly on the image below."}
                      </p>
                    </div>

                    {/* Interactive Drawing Box */}
                    <div 
                      className="relative border border-white/10 bg-black/45 rounded overflow-hidden cursor-crosshair flex items-center justify-center transition-all shadow-inner"
                      style={{ width: finalWidth, height: finalHeight }}
                    >
                      {customTargetPreviewBase64 ? (
                        <img 
                          src={customTargetPreviewBase64} 
                          className="absolute inset-0 w-full h-full object-contain pointer-events-none select-none" 
                          alt="Target Soft Copy" 
                        />
                      ) : (
                        <div className="absolute inset-0 bg-white pointer-events-none border border-gray-300 flex items-center justify-center">
                          <span className="text-[10px] font-mono text-gray-400">SOFT COPY PREVIEW SHEET</span>
                        </div>
                      )}

                      <svg
                        className="absolute inset-0 w-full h-full select-none"
                        onMouseDown={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();
                          const x = e.clientX - rect.left;
                          const y = e.clientY - rect.top;
                          const x_mm = (x / finalWidth) * customTargetWidth;
                          const y_mm = (y / finalHeight) * customTargetHeight;

                          if (customTargetType === "circular") {
                            const cx_px = (circularCenterMm.x / customTargetWidth) * finalWidth;
                            const cy_px = (circularCenterMm.y / customTargetHeight) * finalHeight;
                            const dist = Math.sqrt((x - cx_px)**2 + (y - cy_px)**2);
                            if (dist < 15) {
                              setIsDraggingCenter(true);
                              return;
                            }
                            // Start drawing ring
                            setDragStart({ x: circularCenterMm.x, y: circularCenterMm.y });
                            setDragCurrent({ x: x_mm, y: y_mm });
                          } else {
                            // Start drawing rectangular zone
                            setDragStart({ x: x_mm, y: y_mm });
                            setDragCurrent({ x: x_mm, y: y_mm });
                          }
                        }}
                        onMouseMove={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();
                          const x = e.clientX - rect.left;
                          const y = e.clientY - rect.top;
                          const x_mm = (x / finalWidth) * customTargetWidth;
                          const y_mm = (y / finalHeight) * customTargetHeight;
                          
                          setHoverMm({ x: parseFloat(x_mm.toFixed(1)), y: parseFloat(y_mm.toFixed(1)) });

                          if (isDraggingCenter) {
                            setCircularCenterMm({
                              x: Math.max(0, Math.min(customTargetWidth, parseFloat(x_mm.toFixed(1)))),
                              y: Math.max(0, Math.min(customTargetHeight, parseFloat(y_mm.toFixed(1))))
                            });
                          } else if (dragStart) {
                            setDragCurrent({ x: x_mm, y: y_mm });
                          }
                        }}
                        onMouseUp={() => {
                          if (isDraggingCenter) {
                            setIsDraggingCenter(false);
                          } else if (dragStart && dragCurrent) {
                            if (customTargetType === "rectangular") {
                              const x_min = Math.min(dragStart.x, dragCurrent.x);
                              const x_max = Math.max(dragStart.x, dragCurrent.x);
                              const y_min = Math.min(dragStart.y, dragCurrent.y);
                              const y_max = Math.max(dragStart.y, dragCurrent.y);
                              
                              if (x_max - x_min > 5 && y_max - y_min > 5) {
                                const nextId = customTargetRegions.length > 0 ? Math.max(...customTargetRegions.map(r => r.id)) + 1 : 1;
                                setCustomTargetRegions([
                                  ...customTargetRegions,
                                  {
                                    id: nextId,
                                    name: `Zone ${nextId}`,
                                    value: 1,
                                    x_min_mm: parseFloat(x_min.toFixed(1)),
                                    y_min_mm: parseFloat(y_min.toFixed(1)),
                                    x_max_mm: parseFloat(x_max.toFixed(1)),
                                    y_max_mm: parseFloat(y_max.toFixed(1))
                                  }
                                ]);
                                setSelectedZoneId(nextId);
                              }
                            } else if (customTargetType === "circular") {
                              const dist_mm = Math.sqrt((dragCurrent.x - circularCenterMm.x)**2 + (dragCurrent.y - circularCenterMm.y)**2);
                              if (dist_mm > 2) {
                                const nextVal = customTargetRings.length > 0 ? Math.min(...customTargetRings.map(r => r.value)) - 1 : 10;
                                const updated = [...customTargetRings, { value: nextVal, outer_radius_mm: parseFloat(dist_mm.toFixed(2)) }];
                                updated.sort((a, b) => b.outer_radius_mm - a.outer_radius_mm);
                                setCustomTargetRings(updated);
                              }
                            }
                          }
                          setDragStart(null);
                          setDragCurrent(null);
                        }}
                        onMouseLeave={() => {
                          setHoverMm(null);
                          setIsDraggingCenter(false);
                          setDragStart(null);
                          setDragCurrent(null);
                        }}
                      >
                        {/* Render Circular rings */}
                        {customTargetType === "circular" && (
                          <>
                            {customTargetRings.map((ring, idx) => {
                              const r_px = (ring.outer_radius_mm / customTargetWidth) * finalWidth;
                              const cx_px = (circularCenterMm.x / customTargetWidth) * finalWidth;
                              const cy_px = (circularCenterMm.y / customTargetHeight) * finalHeight;
                              return (
                                <circle
                                  key={idx}
                                  cx={cx_px}
                                  cy={cy_px}
                                  r={r_px}
                                  fill="none"
                                  stroke={selectedRingIdx === idx ? "#10b981" : "rgba(16, 185, 129, 0.4)"}
                                  strokeWidth={selectedRingIdx === idx ? 2.5 : 1.5}
                                  className="transition-all cursor-pointer"
                                  onClick={() => setSelectedRingIdx(idx)}
                                />
                              );
                            })}
                            
                            {/* Center Pin Indicator (draggable) */}
                            <g className="cursor-move">
                              <circle
                                cx={(circularCenterMm.x / customTargetWidth) * finalWidth}
                                cy={(circularCenterMm.y / customTargetHeight) * finalHeight}
                                r={6}
                                fill="#ef4444"
                                fillOpacity={0.7}
                              />
                              <line
                                x1={(circularCenterMm.x / customTargetWidth) * finalWidth - 15}
                                y1={(circularCenterMm.y / customTargetHeight) * finalHeight}
                                x2={(circularCenterMm.x / customTargetWidth) * finalWidth + 15}
                                y2={(circularCenterMm.y / customTargetHeight) * finalHeight}
                                stroke="#ef4444"
                                strokeWidth={2}
                              />
                              <line
                                x1={(circularCenterMm.x / customTargetWidth) * finalWidth}
                                y1={(circularCenterMm.y / customTargetHeight) * finalHeight - 15}
                                x2={(circularCenterMm.x / customTargetWidth) * finalWidth}
                                y2={(circularCenterMm.y / customTargetHeight) * finalHeight + 15}
                                stroke="#ef4444"
                                strokeWidth={2}
                              />
                            </g>

                            {/* Circular drawing preview */}
                            {dragStart && dragCurrent && (
                              <circle
                                cx={(circularCenterMm.x / customTargetWidth) * finalWidth}
                                cy={(circularCenterMm.y / customTargetHeight) * finalHeight}
                                r={(Math.sqrt((dragCurrent.x - circularCenterMm.x)**2 + (dragCurrent.y - circularCenterMm.y)**2) / customTargetWidth) * finalWidth}
                                fill="none"
                                stroke="#10b981"
                                strokeWidth={2}
                                strokeDasharray="4,4"
                              />
                            )}
                          </>
                        )}

                        {/* Render Rectangular zones */}
                        {customTargetType === "rectangular" && (
                          <>
                            {customTargetRegions.map((region) => {
                              const x_px = (region.x_min_mm / customTargetWidth) * finalWidth;
                              const y_px = (region.y_min_mm / customTargetHeight) * finalHeight;
                              const w_px = ((region.x_max_mm - region.x_min_mm) / customTargetWidth) * finalWidth;
                              const h_px = ((region.y_max_mm - region.y_min_mm) / customTargetHeight) * finalHeight;
                              const isSelected = selectedZoneId === region.id;
                              return (
                                <g key={region.id}>
                                  <rect
                                    x={x_px}
                                    y={y_px}
                                    width={w_px}
                                    height={h_px}
                                    fill={isSelected ? "rgba(16, 185, 129, 0.2)" : "rgba(99, 102, 241, 0.12)"}
                                    stroke={isSelected ? "#10b981" : "#6366f1"}
                                    strokeWidth={isSelected ? 2.5 : 1.5}
                                    className="transition-all cursor-pointer"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedZoneId(region.id);
                                    }}
                                  />
                                  <text
                                    x={x_px + w_px / 2}
                                    y={y_px + h_px / 2}
                                    fill={isSelected ? "#10b981" : "#ffffff"}
                                    fontSize={10}
                                    fontWeight="bold"
                                    textAnchor="middle"
                                    dominantBaseline="middle"
                                    className="pointer-events-none drop-shadow"
                                  >
                                    {region.name} ({region.value} pts)
                                  </text>
                                </g>
                              );
                            })}

                            {/* Rectangular drawing preview */}
                            {dragStart && dragCurrent && (
                              <rect
                                x={(Math.min(dragStart.x, dragCurrent.x) / customTargetWidth) * finalWidth}
                                y={(Math.min(dragStart.y, dragCurrent.y) / customTargetHeight) * finalHeight}
                                width={(Math.abs(dragCurrent.x - dragStart.x) / customTargetWidth) * finalWidth}
                                height={(Math.abs(dragCurrent.y - dragStart.y) / customTargetHeight) * finalHeight}
                                fill="rgba(16, 185, 129, 0.15)"
                                stroke="#10b981"
                                strokeWidth={2}
                                strokeDasharray="4,4"
                              />
                            )}
                          </>
                        )}
                      </svg>
                    </div>

                    {/* Coordinate HUD */}
                    <div className="w-full flex justify-between items-center text-[10px] text-gray-400 font-mono">
                      <span>HUD: {hoverMm ? `${hoverMm.x} mm, ${hoverMm.y} mm` : "hover to display position"}</span>
                      <span>SIZE: {customTargetWidth}x{customTargetHeight} mm</span>
                    </div>

                    <div className="flex gap-2 w-full pt-1">
                      <button
                        type="button"
                        onClick={() => {
                          if (customTargetType === "circular") {
                            setCustomTargetRings([]);
                          } else {
                            setCustomTargetRegions([]);
                          }
                        }}
                        className="flex-1 py-1 rounded bg-red-950/20 border border-red-500/20 hover:bg-red-900/20 text-red-400 hover:text-red-300 text-xs font-mono transition"
                      >
                        CLEAR ALL ZONES
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (customTargetType === "circular") {
                            setCustomTargetRings([
                              { value: 10, outer_radius_mm: 2.5 },
                              { value: 9, outer_radius_mm: 5.0 },
                              { value: 8, outer_radius_mm: 7.5 },
                              { value: 7, outer_radius_mm: 10.0 },
                              { value: 6, outer_radius_mm: 12.5 },
                              { value: 5, outer_radius_mm: 15.0 },
                              { value: 4, outer_radius_mm: 17.5 },
                              { value: 3, outer_radius_mm: 20.0 },
                              { value: 2, outer_radius_mm: 22.5 },
                              { value: 1, outer_radius_mm: 25.0 }
                            ]);
                            setCircularCenterMm({ x: customTargetWidth/2, y: customTargetHeight/2 });
                          } else {
                            setCustomTargetRegions([
                              { id: 1, name: "Outer Torso", value: 4, x_min_mm: 40.0, y_min_mm: 42.5, x_max_mm: 540.0, y_max_mm: 842.5 },
                              { id: 2, name: "Inner Center", value: 5, x_min_mm: 190.0, y_min_mm: 292.5, x_max_mm: 390.0, y_max_mm: 592.5 }
                            ]);
                          }
                        }}
                        className="flex-1 py-1 rounded bg-white/5 border border-white/10 hover:bg-white/10 text-gray-300 text-xs font-mono transition"
                      >
                        RESET TEMPLATE
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end gap-3 pt-3 border-t border-white/5">
                  <button
                    type="button"
                    onClick={() => setShowCreateTargetModal(false)}
                    className="px-4 py-2 border border-white/10 hover:bg-white/5 rounded text-xs font-mono text-gray-400 hover:text-white transition"
                  >
                    CANCEL
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded text-xs font-mono text-white font-bold transition"
                  >
                    SAVE TARGET
                  </button>
                </div>
              </form>
            </div>
          </div>
        );
      })()}

    </main>
  );
}