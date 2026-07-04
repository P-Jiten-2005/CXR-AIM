import { create } from "zustand";

export interface Detection {
  id: string;
  area: number;
  circularity: number;
  solidity: number;
  aspect_ratio: number;
  raw_contour: number[][] | null;
}

export interface Shot {
  id: string;
  session_id: string;
  image_id: string | null;
  shot_number: number;
  x_raw: number;
  y_raw: number;
  x_calibrated: number | null;
  y_calibrated: number | null;
  x_warped?: number | null;
  y_warped?: number | null;
  diameter_px: number;
  diameter_mm: number | null;
  confidence: number;
  is_valid: boolean;
  score?: number | null;
  decimal_score?: number | null;
  nearest_ring_value?: number | null;
  distance_to_nearest_ring_mm?: number | null;
  bullseye_id?: number | null;
  distance_to_center_mm?: number | null;
  boundary_status?: string | null;
  localization_error_mm?: number | null;
  detection_method?: string | null;
  created_at: string;
  detection?: Detection | null;
}

export interface Session {
  id: string;
  name: string;
  description: string | null;
  status: string;
  target_type: string;
  bullet_caliber: number;
  session_range: string | null;
  drill_type: string | null;
  bullets_per_drill: number | null;
  unit_number: string | null;
  session_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface Statistics {
  total_shots: number;
  average_diameter_px: number;
  largest_diameter_px: number;
  smallest_diameter_px: number;
  last_shot_time: string | null;
  session_status: string;
  camera_status: string;
}

export interface Candidate {
  x_raw: number;
  y_raw: number;
  x_warped?: number | null;
  y_warped?: number | null;
  diameter_px: number;
  confidence: number;
  verification_method: string;
  is_verified: boolean;
}

interface PlatformState {
  activeSession: Session | null;
  wsStatus: "connected" | "disconnected" | "connecting";
  shots: Shot[];
  candidates: Candidate[];
  statistics: Statistics;
  selectedShotId: string | null;
  hiddenShotIds: string[];
  baselineUrl: string | null;
  currentFrameUrl: string | null;
  targetDefinition: any | null;
  userRole: "technician" | "instructor" | "shooter";
  minCaliber: string;
  maxCaliber: string;
  minScore: string;
  minConfidence: string;
  searchQuery: string;
  
  setActiveSession: (session: Session | null) => void;
  setWsStatus: (status: "connected" | "disconnected" | "connecting") => void;
  setShots: (shots: Shot[]) => void;
  setCandidates: (candidates: Candidate[]) => void;
  addShot: (shot: Shot) => void;
  setStatistics: (stats: Statistics) => void;
  setSelectedShotId: (id: string | null) => void;
  toggleShotVisibility: (id: string) => void;
  setAllShotsVisible: (visible: boolean) => void;
  setBaselineUrl: (url: string | null) => void;
  setCurrentFrameUrl: (url: string | null) => void;
  setTargetDefinition: (targetDef: any | null) => void;
  setUserRole: (role: "technician" | "instructor" | "shooter") => void;
  updateShot: (shot: Shot) => void;
  setMinCaliber: (val: string) => void;
  setMaxCaliber: (val: string) => void;
  setMinScore: (val: string) => void;
  setMinConfidence: (val: string) => void;
  setSearchQuery: (val: string) => void;
  clearFilters: () => void;
  reset: () => void;
}

const initialStatistics: Statistics = {
  total_shots: 0,
  average_diameter_px: 0,
  largest_diameter_px: 0,
  smallest_diameter_px: 0,
  last_shot_time: null,
  session_status: "inactive",
  camera_status: "offline"
};

export const useStore = create<PlatformState>((set) => ({
  activeSession: null,
  wsStatus: "disconnected",
  shots: [],
  candidates: [],
  statistics: initialStatistics,
  selectedShotId: null,
  hiddenShotIds: [],
  baselineUrl: null,
  currentFrameUrl: null,
  targetDefinition: null,
  userRole: "technician",
  minCaliber: "",
  maxCaliber: "",
  minScore: "",
  minConfidence: "",
  searchQuery: "",

  setActiveSession: (session) => set({ activeSession: session }),
  setWsStatus: (status) => set({ wsStatus: status }),
  setShots: (shots) => set({ shots }),
  setCandidates: (candidates) => set({ candidates }),
  addShot: (shot) => set((state) => {
    // Avoid duplicate insertions
    if (state.shots.some((s) => s.id === shot.id)) return state;
    
    const newShots = [...state.shots, shot].sort((a, b) => a.shot_number - b.shot_number);
    
    // Update local statistics reactively before HTTP sync completes
    const validShots = newShots.filter((s) => s.is_valid);
    const total = validShots.length;
    const diameters = validShots.map((s) => s.diameter_px);
    const avg = total > 0 ? parseFloat((diameters.reduce((a, b) => a + b, 0) / total).toFixed(2)) : 0;
    const max = total > 0 ? parseFloat(Math.max(...diameters).toFixed(2)) : 0;
    const min = total > 0 ? parseFloat(Math.min(...diameters).toFixed(2)) : 0;

    return {
      shots: newShots,
      statistics: {
        ...state.statistics,
        total_shots: total,
        average_diameter_px: avg,
        largest_diameter_px: max,
        smallest_diameter_px: min,
        last_shot_time: shot.created_at
      }
    };
  }),
  setStatistics: (statistics) => set({ statistics }),
  setSelectedShotId: (selectedShotId) => set({ selectedShotId }),
  toggleShotVisibility: (id) => set((state) => ({
    hiddenShotIds: state.hiddenShotIds.includes(id)
      ? state.hiddenShotIds.filter((x) => x !== id)
      : [...state.hiddenShotIds, id],
  })),
  setAllShotsVisible: (visible) => set((state) => ({
    hiddenShotIds: visible ? [] : state.shots.map((s) => s.id),
  })),
  setBaselineUrl: (baselineUrl) => set({ baselineUrl }),
  setCurrentFrameUrl: (currentFrameUrl) => set({ currentFrameUrl }),
  setTargetDefinition: (targetDefinition) => set({ targetDefinition }),
  setUserRole: (userRole) => set({ userRole }),
  updateShot: (updatedShot) => set((state) => {
    const newShots = state.shots.map((s) => s.id === updatedShot.id ? updatedShot : s);
    
    const validShots = newShots.filter((s) => s.is_valid);
    const total = validShots.length;
    const diameters = validShots.map((s) => s.diameter_px);
    const avg = total > 0 ? parseFloat((diameters.reduce((a, b) => a + b, 0) / total).toFixed(2)) : 0;
    const max = total > 0 ? parseFloat(Math.max(...diameters).toFixed(2)) : 0;
    const min = total > 0 ? parseFloat(Math.min(...diameters).toFixed(2)) : 0;
    const lastShotTime = validShots.length > 0 ? validShots[validShots.length - 1].created_at : null;

    return {
      shots: newShots,
      statistics: {
        ...state.statistics,
        total_shots: total,
        average_diameter_px: avg,
        largest_diameter_px: max,
        smallest_diameter_px: min,
        last_shot_time: lastShotTime
      }
    };
  }),
  setMinCaliber: (minCaliber) => set({ minCaliber }),
  setMaxCaliber: (maxCaliber) => set({ maxCaliber }),
  setMinScore: (minScore) => set({ minScore }),
  setMinConfidence: (minConfidence) => set({ minConfidence }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  clearFilters: () => set({
    minCaliber: "",
    maxCaliber: "",
    minScore: "",
    minConfidence: "",
    searchQuery: "",
  }),
  reset: () => set({
    activeSession: null,
    shots: [],
    candidates: [],
    statistics: initialStatistics,
    selectedShotId: null,
    hiddenShotIds: [],
    baselineUrl: null,
    currentFrameUrl: null,
    targetDefinition: null,
    userRole: "technician",
    minCaliber: "",
    maxCaliber: "",
    minScore: "",
    minConfidence: "",
    searchQuery: "",
  })
}));
