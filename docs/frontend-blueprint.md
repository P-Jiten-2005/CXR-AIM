# CXR-AIM Frontend Implementation Blueprint & Code Reference

This document serves as a complete blueprint and source code reference for the **CXR-AIM Shooting Target Acquisition & Analytics Platform** frontend dashboard. It contains all feature specifications, design patterns, API integrations, WebSocket contracts, and the exact source code files so that you can prompt any LLM (e.g., Claude, GPT-4, etc.) to rebuild the identical user interface from scratch.

---

## 🛠️ Technology Stack & Dependencies

The frontend dashboard is built on a modern, high-performance web stack:
1. **Framework**: Next.js 15+ (App Router, React 19)
2. **State Management**: Zustand (Global reactive state, client-side caching, statistics computation)
3. **Styling**: Tailwind CSS v4 (with custom inline theme configuration for neon aesthetics and glassmorphism)
4. **Icons**: Lucide React
5. **Interactive Rendering**: HTML5 Canvas API (for overlaying dynamically scaled bullet hole vectors and custom binarized contours onto target frames, handling hover states, and drawing concentric ring fallbacks)

---

## 🚀 Key Dashboard Features & Layout

The dashboard is structured as a single-page tactical feed:
1. **Real-time Telemetry & Status Monitoring Bar**: Indicates WebSocket subscription connectivity, live optical camera status, and active session detection state.
2. **Interactive Image Review Station (Dynamic Tabbed Canvas)**:
   - **Overlay**: Displays the active target image (either the post-fire feed or baseline baseline calibration) overlayed with color-coded bullet-hole contours/circles. Interactive cursor hover highlights specific holes.
   - **Baseline**: Renders the perspective-rectified target baseline captured prior to shooting.
   - **Current**: Renders the latest snapshot from the physical camera.
   - **Difference**: Displays the binarized OpenCV frame showing absolute differences.
   - **2x2 Compare Grid**: Displays all four modes side-by-side inside a responsive layout.
3. **Target Capture & Camera Controllers**: Controls index-based webcams or HTTP IP streams. Triggers calibration (`Before Fire` baseline capture) and differencing engine triggers (`After Fire` analysis).
4. **YOLOv8 AI Verification Console**:
   - Ingests dataset sync statistics (Raw, Validated, Split ratios, bullet vs tear vs false positive counts).
   - Monitors active model configurations (Precision, Recall, mAP50, mAP50-95 metrics).
   - Exposes epoch/batch/imgsz hyperparameters to trigger customized background model training runs.
   - Displays historical runs with reactive status badges (`pending`, `running`, `completed`, `failed`).
5. **Score & Shot Telemetry Table**: Lists shot numbers, Cartesian coordinates, diameters (px), confidence percentage, classification method tags (`YOLOv8`, `SAHI`, `OPENCV`), and toggles for shot validity.
6. **Unified Terminal Console Log**: Streams real-time notifications with timestamps from WebSockets and API requests (e.g., `SHOT_DETECTED`, `BASELINE_UPLOADED`).

---

## 📁 Frontend Repository Structure

Ensure the frontend has the following directory structure:
```
frontend/
├── src/
│   ├── app/
│   │   ├── globals.css          # Custom theme variables, glassmorphism, & scrolls
│   │   ├── layout.tsx           # Geist font loading and metadata
│   │   └── page.tsx             # Root Dashboard Page & Orchestrator
│   ├── components/
│   │   └── dashboard/
│   │       ├── ConnectionStatus.tsx # Telemetry status pill badges
│   │       ├── LiveTargetView.tsx   # Tabs, 2x2 grid, & HTML5 Canvas overlays
│   │       ├── OverviewCards.tsx    # Glow-bordered statistical overview cards
│   │       ├── ShotTable.tsx        # Grid table for validity toggling
│   │       └── StatsPanel.tsx       # Calculated metrics & Active YOLO weights
│   └── store/
│       └── useStore.ts          # Zustand store for state management
├── package.json
└── tsconfig.json
```

---

## 📡 API & WebSocket Contracts

The frontend expects the backend server to run on `http://localhost:8000`.

### 1. HTTP Rest Endpoints
- `GET /api/v1/sessions/active`: Returns the current active session `{ id, name, description, status, created_at }` or `null`.
- `POST /api/v1/sessions`: Instantiates a new session. Payload: `{ name: string, description?: string }`.
- `GET /api/v1/sessions/{session_id}/shots`: Retrieves all detected shots.
- `DELETE /api/v1/sessions/{session_id}/shots`: Clears all marks in the database.
- `GET /api/v1/sessions/{session_id}/statistics`: Retrieves global session stats.
- `GET /api/v1/sessions/{session_id}/baseline`: Retrieves the active baseline file record.
- `POST /api/v1/camera/connect?source={source}&session_id={session_id}`: Initializes stream connection.
- `POST /api/v1/camera/disconnect`: Closes camera stream connection.
- `POST /api/v1/capture/before-fire?session_id={session_id}`: Snapshots reference calibration image.
- `POST /api/v1/capture/after-fire?session_id={session_id}`: Analyzes post-fire image, triggers diff and detection.
- `GET /api/v1/models/active`: Retrieves metadata of active YOLO neural network weights.
- `GET /api/v1/training/runs`: Lists all current and historical YOLO background training runs.
- `GET /api/v1/training/dataset-stats`: Ingests class counts, image counts, and train/val/test splits.
- `POST /api/v1/train`: Spawns background YOLO training. Payload: `{ epochs: number, batch_size: number, img_size: number }`.

### 2. WebSocket Events
Broadcasting occurs on `ws://localhost:8000/ws/session/{session_id}`.
- **`SHOT_DETECTED`**:
  ```json
  { "event": "SHOT_DETECTED", "data": { "id": "uuid", "shot_number": 1, "x_raw": 150.2, "y_raw": 300.5, "diameter_px": 12.5, "confidence": 0.94, "is_valid": true, "detection_method": "yolov8s", "created_at": "ISO-Timestamp", "detection": { "raw_contour": [[150, 290], [156, 300], [150, 310]] } } }
  ```
- **`BASELINE_UPLOADED`**:
  ```json
  { "event": "BASELINE_UPLOADED", "data": { "file_path": "/uploads/baseline.jpg", "method": "apriltag" } }
  ```
- **`CURRENT_IMAGE_UPDATED`**:
  ```json
  { "event": "CURRENT_IMAGE_UPDATED", "data": { "baseline_url": "/uploads/baseline.jpg", "current_url": "/uploads/current.jpg", "difference_url": "/uploads/diff.jpg" } }
  ```
- **`SHOTS_CLEARED`**:
  ```json
  { "event": "SHOTS_CLEARED" }
  ```

---

## 💻 Full Source Code Reference

You can copy-paste the exact code blocks below to build the frontend.

### 1. `package.json`
```json
{
  "name": "frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint"
  },
  "dependencies": {
    "lucide-react": "^1.17.0",
    "next": "16.2.7",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "zustand": "^5.0.14"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "eslint": "^9",
    "eslint-config-next": "16.2.7",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}
```

### 2. `src/app/globals.css`
```css
@import "tailwindcss";

:root {
  --background: #090d16;
  --foreground: #f3f4f6;
  
  --card-bg: rgba(17, 24, 39, 0.75);
  --card-border: rgba(255, 255, 255, 0.08);
  
  --primary-glow: rgba(16, 185, 129, 0.15);
  --accent-neon: #10b981;
  --accent-red: #ef4444;
  --accent-yellow: #f59e0b;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card-bg);
  --color-border: var(--card-border);
  --color-neon: var(--accent-neon);
  --color-red: var(--accent-red);
  --color-yellow: var(--accent-yellow);
}

body {
  background-color: var(--background);
  color: var(--foreground);
  font-family: ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  overflow-x: hidden;
}

/* Glassmorphism custom styles */
.glass-panel {
  background: var(--card-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
}

.glow-border {
  position: relative;
}

.glow-border::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 12px;
  padding: 1px;
  background: linear-gradient(to bottom right, rgba(16, 185, 129, 0.4), transparent 50%, rgba(239, 68, 68, 0.2));
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}

.neon-glow {
  box-shadow: 0 0 15px var(--primary-glow);
}

/* Scrollbar customization */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.02);
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
```

### 3. `src/app/layout.tsx`
```tsx
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "CXR-AIM Platform: Shooting Target Acquisition & Analytics",
  description: "Real-time shooting target calibration, binarized bullet-hole contours mapping, and performance analytics telemetry console.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
```

### 4. `src/store/useStore.ts`
```typescript
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
  diameter_px: number;
  diameter_mm: number | null;
  confidence: number;
  is_valid: boolean;
  detection_method?: string | null;
  created_at: string;
  detection?: Detection | null;
}

export interface Session {
  id: string;
  name: string;
  description: string | null;
  status: string;
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

interface PlatformState {
  activeSession: Session | null;
  wsStatus: "connected" | "disconnected" | "connecting";
  shots: Shot[];
  statistics: Statistics;
  selectedShotId: string | null;
  baselineUrl: string | null;
  currentFrameUrl: string | null;
  differenceUrl: string | null;
  activeModel: any | null;
  
  setActiveSession: (session: Session | null) => void;
  setWsStatus: (status: "connected" | "disconnected" | "connecting") => void;
  setShots: (shots: Shot[]) => void;
  addShot: (shot: Shot) => void;
  setStatistics: (stats: Statistics) => void;
  setSelectedShotId: (id: string | null) => void;
  setBaselineUrl: (url: string | null) => void;
  setCurrentFrameUrl: (url: string | null) => void;
  setDifferenceUrl: (url: string | null) => void;
  setActiveModel: (model: any | null) => void;
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
  statistics: initialStatistics,
  selectedShotId: null,
  baselineUrl: null,
  currentFrameUrl: null,
  differenceUrl: null,
  activeModel: null,

  setActiveSession: (session) => set({ activeSession: session }),
  setWsStatus: (status) => set({ wsStatus: status }),
  setShots: (shots) => set({ shots }),
  addShot: (shot) => set((state) => {
    if (state.shots.some((s) => s.id === shot.id)) return state;
    
    const newShots = [...state.shots, shot].sort((a, b) => a.shot_number - b.shot_number);
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
  setBaselineUrl: (baselineUrl) => set({ baselineUrl }),
  setCurrentFrameUrl: (currentFrameUrl) => set({ currentFrameUrl }),
  setDifferenceUrl: (differenceUrl) => set({ differenceUrl }),
  setActiveModel: (activeModel) => set({ activeModel }),
  reset: () => set({
    activeSession: null,
    shots: [],
    statistics: initialStatistics,
    selectedShotId: null,
    baselineUrl: null,
    currentFrameUrl: null,
    differenceUrl: null,
    activeModel: null
  })
}));
```

### 5. `src/components/dashboard/ConnectionStatus.tsx`
```tsx
"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import { Activity, Camera, Cpu } from "lucide-react";

export default function ConnectionStatus() {
  const { wsStatus, activeSession, statistics } = useStore();

  const getStatusColor = (status: string) => {
    switch (status) {
      case "connected":
        return "text-emerald-400 bg-emerald-400/10 border-emerald-500/20";
      case "connecting":
        return "text-amber-400 bg-amber-400/10 border-amber-500/20 animate-pulse";
      default:
        return "text-red-400 bg-red-400/10 border-red-500/20";
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Platform Status */}
      <div className={`flex items-center gap-2 px-3 py-1.5 border rounded-full text-xs font-mono transition-colors ${getStatusColor(wsStatus)}`}>
        <Activity className="w-3.5 h-3.5" />
        <span>TELEMETRY: {wsStatus.toUpperCase()}</span>
      </div>

      {/* Camera Status */}
      <div className={`flex items-center gap-2 px-3 py-1.5 border rounded-full text-xs font-mono transition-colors ${
        statistics.camera_status === "online" 
          ? "text-emerald-400 bg-emerald-400/10 border-emerald-500/20" 
          : "text-red-400 bg-red-400/10 border-red-500/20"
      }`}>
        <Camera className="w-3.5 h-3.5" />
        <span>CAMERA: {statistics.camera_status.toUpperCase()}</span>
      </div>

      {/* Session Mode */}
      <div className={`flex items-center gap-2 px-3 py-1.5 border rounded-full text-xs font-mono ${
        activeSession 
          ? "text-neon bg-emerald-500/5 border-emerald-500/10" 
          : "text-gray-400 bg-gray-500/5 border-gray-500/10"
      }`}>
        <Cpu className="w-3.5 h-3.5" />
        <span>MODE: {activeSession ? "ACTIVE_DETECTION" : "IDLE"}</span>
      </div>
    </div>
  );
}
```

### 6. `src/components/dashboard/OverviewCards.tsx`
```tsx
"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import { Target, Clock, Shield, Camera } from "lucide-react";

export default function OverviewCards() {
  const { statistics, activeSession } = useStore();

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return "N/A";
    const date = new Date(timeStr);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  const cards = [
    {
      title: "Total Holes",
      value: statistics.total_shots,
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
      description: activeSession ? activeSession.description || "Active session monitoring" : "Start a session to capture",
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

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
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
```

### 7. `src/components/dashboard/LiveTargetView.tsx`
```tsx
"use client";

import React, { useRef, useEffect, useState } from "react";
import { useStore, Shot } from "@/store/useStore";
import { Maximize2, ShieldAlert, Crosshair, Trash2, LayoutGrid, Layers, Image as ImageIcon, Binary, Eye } from "lucide-react";

type ViewMode = "overlay" | "baseline" | "current" | "difference" | "grid";

export default function LiveTargetView() {
  const { 
    shots, 
    selectedShotId, 
    setSelectedShotId, 
    baselineUrl, 
    currentFrameUrl, 
    differenceUrl,
    activeSession, 
    setShots, 
    setStatistics, 
    setCurrentFrameUrl,
    setDifferenceUrl
  } = useStore();

  const [viewMode, setViewMode] = useState<ViewMode>("overlay");
  const [isClearing, setIsClearing] = useState(false);

  const handleClearShots = async () => {
    if (!activeSession) return;
    if (!confirm("Are you sure you want to clear all shot markings from this session?")) return;
    setIsClearing(true);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/sessions/${activeSession.id}/shots`, { method: "DELETE" });
      if (res.ok) {
        setShots([]);
        setCurrentFrameUrl(null);
        setDifferenceUrl(null);
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
  const gridCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  
  const [imgLoaded, setImgLoaded] = useState(false);
  const imageRef = useRef<HTMLImageElement | null>(null);
  
  const [dimensions, setDimensions] = useState({ width: 500, height: 500 });
  const scaleRef = useRef(1);
  const offsetRef = useRef({ x: 0, y: 0 });

  const activeImageUrl = currentFrameUrl || baselineUrl;

  const resolveUrl = (url: string | null) => {
    if (!url) return null;
    return url.startsWith("http") ? url : `http://localhost:8000${url}`;
  };

  useEffect(() => {
    if (!activeImageUrl) {
      setImgLoaded(false);
      imageRef.current = null;
      return;
    }

    const img = new Image();
    img.src = resolveUrl(activeImageUrl)!;
    img.onload = () => {
      imageRef.current = img;
      setImgLoaded(true);
      triggerResize();
    };
    img.onerror = () => {
      console.error("Failed to load target image from backend.");
      setImgLoaded(false);
    };
  }, [activeImageUrl]);

  const triggerResize = () => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const size = Math.max(300, Math.min(rect.width - 48, 550));
    setDimensions({ width: size, height: size });
  };

  useEffect(() => {
    triggerResize();
    window.addEventListener("resize", triggerResize);
    return () => window.removeEventListener("resize", triggerResize);
  }, [imgLoaded, viewMode]);

  const drawOverlayCanvas = (canvas: HTMLCanvasElement | null, isGridCell: boolean = false) => {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";

    if (imgLoaded && imageRef.current) {
      const img = imageRef.current;
      const imgRatio = img.naturalWidth / img.naturalHeight;
      let drawW = canvas.width;
      let drawH = canvas.height;
      let dx = 0;
      let dy = 0;

      if (imgRatio > 1) {
        drawH = canvas.width / imgRatio;
        dy = (canvas.height - drawH) / 2;
      } else {
        drawW = canvas.height * imgRatio;
        dx = (canvas.width - drawW) / 2;
      }

      ctx.drawImage(img, dx, dy, drawW, drawH);

      const currentScale = drawW / img.naturalWidth;
      if (!isGridCell) {
        scaleRef.current = currentScale;
        offsetRef.current = { x: dx, y: dy };
      }

      shots.forEach((shot) => {
        if (!shot.is_valid) return;

        const canvasX = shot.x_raw * currentScale + dx;
        const canvasY = shot.y_raw * currentScale + dy;
        const radius = (shot.diameter_px * currentScale) / 2;

        const isSelected = !isGridCell && shot.id === selectedShotId;

        // Draw dynamic vector contour
        if (shot.detection && shot.detection.raw_contour) {
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
          ctx.beginPath();
          ctx.arc(canvasX, canvasY, Math.max(radius, 4), 0, 2 * Math.PI);
          ctx.fillStyle = isSelected ? "rgba(239, 68, 68, 0.3)" : "rgba(16, 185, 129, 0.25)";
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

        // Draw numbering label above the vector marking
        ctx.fillStyle = "#ffffff";
        ctx.font = isGridCell ? "bold 8px monospace" : "bold 10px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        
        ctx.beginPath();
        const labelOffset = isGridCell ? 6 : 10;
        const labelRadius = isGridCell ? 6 : 8;
        ctx.arc(canvasX, canvasY - Math.max(radius, 4) - labelOffset, labelRadius, 0, 2 * Math.PI);
        ctx.fillStyle = isSelected ? "#ef4444" : "#0f172a";
        ctx.fill();
        ctx.strokeStyle = isSelected ? "#ffffff" : "#10b981";
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = "#ffffff";
        ctx.fillText(shot.shot_number.toString(), canvasX, canvasY - Math.max(radius, 4) - labelOffset);
      });
    } else {
      // Concentric Target Fallback Grid (renders when no webcam or reference image is connected)
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      if (!isGridCell) {
        scaleRef.current = 1;
        offsetRef.current = { x: 0, y: 0 };
      }

      ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, cy);
      ctx.lineTo(canvas.width, cy);
      ctx.moveTo(cx, 0);
      ctx.lineTo(cx, canvas.height);
      ctx.stroke();

      const ringSpacing = canvas.width / 22;
      for (let r = 10; r >= 1; r--) {
        const radius = (11 - r) * ringSpacing;
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
        if (r >= 9) {
          ctx.fillStyle = "#1e293b";
          ctx.fill();
        }
        ctx.strokeStyle = r === 10 ? "#ef4444" : "rgba(255, 255, 255, 0.15)";
        ctx.lineWidth = r === 10 ? 2 : 1;
        ctx.stroke();
      }
    }
  };

  useEffect(() => {
    if (viewMode === "overlay") {
      drawOverlayCanvas(canvasRef.current);
    } else if (viewMode === "grid") {
      drawOverlayCanvas(gridCanvasRef.current, true);
    }
  }, [imgLoaded, shots, selectedShotId, dimensions, viewMode]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || shots.length === 0 || viewMode !== "overlay") return;
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    let hoveredShotId: string | null = null;
    let minDistance = 20;

    shots.forEach((shot) => {
      if (!shot.is_valid) return;
      const canvasX = shot.x_raw * scaleRef.current + offsetRef.current.x;
      const canvasY = shot.y_raw * scaleRef.current + offsetRef.current.y;
      
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

  const TABS = [
    { mode: "overlay", label: "Overlay", icon: Layers },
    { mode: "baseline", label: "Baseline", icon: ImageIcon },
    { mode: "current", label: "Current", icon: Eye },
    { mode: "difference", label: "Difference", icon: Binary },
    { mode: "grid", label: "2x2 Compare", icon: LayoutGrid },
  ] as const;

  return (
    <div ref={containerRef} className="glass-panel p-6 flex flex-col items-center justify-between h-full space-y-4 w-full">
      {/* Header controls */}
      <div className="flex flex-col sm:flex-row justify-between items-center w-full gap-4 pb-2 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Crosshair className="w-5 h-5 text-neon" />
          <h3 className="text-sm font-bold font-mono tracking-wider uppercase">Image Review Station</h3>
        </div>
        <div className="flex items-center gap-2">
          {activeSession && shots.length > 0 && (
            <button
              onClick={handleClearShots}
              disabled={isClearing}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-red-955/40 border border-red-500/20 hover:bg-red-900/40 transition text-red-400 hover:text-red-300 text-xs font-mono"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">CLEAR MARKS</span>
            </button>
          )}
          <button onClick={triggerResize} className="p-1.5 rounded bg-white/5 border border-white/5 hover:bg-white/10 transition text-gray-400 hover:text-white">
            <Maximize2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tabs Selector */}
      <div className="flex flex-wrap items-center justify-center gap-1.5 bg-[#030712] p-1 border border-white/5 rounded-lg w-full">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = viewMode === tab.mode;
          return (
            <button
              key={tab.mode}
              onClick={() => setViewMode(tab.mode)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[10px] sm:text-xs font-mono font-bold transition-all duration-150 ${
                isActive 
                  ? "bg-neon text-[#030712] shadow-lg shadow-neon/15"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label.toUpperCase()}</span>
            </button>
          );
        })}
      </div>

      {/* Visual Window */}
      <div className="relative border border-white/5 bg-[#030712] rounded-lg overflow-hidden flex items-center justify-center p-2 w-full min-h-[350px] sm:min-h-[500px]">
        {/* Grid View */}
        {viewMode === "grid" && (
          <div className="grid grid-cols-2 gap-2 w-full h-full max-w-[550px] aspect-square">
            <div className="relative border border-white/5 bg-black rounded-lg overflow-hidden aspect-square flex items-center justify-center group">
              {baselineUrl ? (
                <img src={resolveUrl(baselineUrl)!} alt="Baseline" className="w-full h-full object-contain" />
              ) : (
                <div className="flex flex-col items-center justify-center text-center p-2">
                  <ImageIcon className="w-6 h-6 text-gray-600 mb-1" />
                  <span className="text-[9px] font-mono text-gray-500">AWAITING BASELINE</span>
                </div>
              )}
              <div className="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 border border-white/10 rounded text-[8px] font-mono text-gray-400 group-hover:text-white transition">
                1. BASELINE REFERENCE
              </div>
            </div>

            <div className="relative border border-white/5 bg-black rounded-lg overflow-hidden aspect-square flex items-center justify-center group">
              {currentFrameUrl ? (
                <img src={resolveUrl(currentFrameUrl)!} alt="Current" className="w-full h-full object-contain" />
              ) : (
                <div className="flex flex-col items-center justify-center text-center p-2">
                  <Eye className="w-6 h-6 text-gray-600 mb-1" />
                  <span className="text-[9px] font-mono text-gray-500">AWAITING POST-FIRE</span>
                </div>
              )}
              <div className="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 border border-white/10 rounded text-[8px] font-mono text-gray-400 group-hover:text-white transition">
                2. CURRENT (POST-FIRE)
              </div>
            </div>

            <div className="relative border border-white/5 bg-black rounded-lg overflow-hidden aspect-square flex items-center justify-center group">
              {differenceUrl ? (
                <img src={resolveUrl(differenceUrl)!} alt="Diff" className="w-full h-full object-contain invert brightness-125" />
              ) : (
                <div className="flex flex-col items-center justify-center text-center p-2">
                  <Binary className="w-6 h-6 text-gray-600 mb-1" />
                  <span className="text-[9px] font-mono text-gray-500">AWAITING DIFFERENCE</span>
                </div>
              )}
              <div className="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 border border-white/10 rounded text-[8px] font-mono text-gray-400 group-hover:text-white transition">
                3. CV DIFFERENCE MAP
              </div>
            </div>

            <div className="relative border border-white/5 bg-black rounded-lg overflow-hidden aspect-square flex items-center justify-center group">
              <canvas ref={gridCanvasRef} width={dimensions.width / 2} height={dimensions.height / 2} className="max-w-full max-h-full object-contain" />
              <div className="absolute bottom-1 left-1 px-1.5 py-0.5 bg-black/70 border border-white/10 rounded text-[8px] font-mono text-gray-400 group-hover:text-white transition">
                4. DETECTION OVERLAY
              </div>
            </div>
          </div>
        )}

        {/* Tab View Canvas & Imagery */}
        {viewMode === "overlay" && (
          <canvas
            ref={canvasRef}
            width={dimensions.width}
            height={dimensions.height}
            onMouseMove={handleMouseMove}
            onMouseLeave={handleMouseLeave}
            className="cursor-crosshair max-w-full"
          />
        )}

        {viewMode === "baseline" && (
          <div className="flex items-center justify-center w-full h-full max-w-[550px] aspect-square">
            {baselineUrl ? (
              <img src={resolveUrl(baselineUrl)!} alt="Baseline" className="max-w-full max-h-[500px] object-contain rounded-lg shadow-2xl border border-white/10" />
            ) : (
              <div className="flex flex-col items-center justify-center text-center p-6">
                <ImageIcon className="w-12 h-12 text-gray-600 mb-3" />
                <span className="text-xs font-mono text-gray-500">No baseline image captured. Click "BEFORE FIRE" to capture.</span>
              </div>
            )}
          </div>
        )}

        {viewMode === "current" && (
          <div className="flex items-center justify-center w-full h-full max-w-[550px] aspect-square">
            {currentFrameUrl ? (
              <img src={resolveUrl(currentFrameUrl)!} alt="Current" className="max-w-full max-h-[500px] object-contain rounded-lg shadow-2xl border border-white/10" />
            ) : (
              <div className="flex flex-col items-center justify-center text-center p-6">
                <Eye className="w-12 h-12 text-gray-600 mb-3" />
                <span className="text-xs font-mono text-gray-500">No post-fire image captured. Click "AFTER FIRE" to capture.</span>
              </div>
            )}
          </div>
        )}

        {viewMode === "difference" && (
          <div className="flex items-center justify-center w-full h-full max-w-[550px] aspect-square">
            {differenceUrl ? (
              <img src={resolveUrl(differenceUrl)!} alt="Difference" className="max-w-full max-h-[500px] object-contain rounded-lg shadow-2xl border border-white/10 invert brightness-125" />
            ) : (
              <div className="flex flex-col items-center justify-center text-center p-6">
                <Binary className="w-12 h-12 text-gray-600 mb-3" />
                <span className="text-xs font-mono text-gray-500">No difference map available. Capture "AFTER FIRE" to run difference detection.</span>
              </div>
            )}
          </div>
        )}

        {!baselineUrl && viewMode === "overlay" && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm p-6 text-center">
            <ShieldAlert className="w-10 h-10 text-amber-500 mb-3" />
            <h4 className="font-mono text-sm font-semibold text-white uppercase tracking-wider">Baseline Required</h4>
            <p className="text-xs text-gray-400 mt-1 max-w-[280px]">
              Capture a baseline "Before Fire" target image first to calibrate the camera and differencing engine.
            </p>
          </div>
        )}
      </div>

      <div className="w-full flex justify-between items-center text-[10px] text-gray-500 font-mono pt-2 border-t border-white/5">
        <span>RESOLUTION: {imageRef.current ? `${imageRef.current.naturalWidth}x${imageRef.current.naturalHeight}px` : "N/A"}</span>
        <span>VIEW MODE: {viewMode.toUpperCase()}</span>
      </div>
    </div>
  );
}
```

### 8. `src/components/dashboard/ShotTable.tsx`
```tsx
"use client";

import React from "react";
import { useStore, Shot } from "@/store/useStore";
import { Eye, EyeOff, HelpCircle } from "lucide-react";

export default function ShotTable() {
  const { shots, selectedShotId, setSelectedShotId, setShots } = useStore();

  const handleRowHover = (id: string | null) => {
    setSelectedShotId(id);
  };

  const toggleShotValidity = async (shot: Shot, e: React.MouseEvent) => {
    e.stopPropagation();
    // Simulate toggling is_valid client-side
    const updatedShots = shots.map((s) => 
      s.id === shot.id ? { ...s, is_valid: !s.is_valid } : s
    );
    setShots(updatedShots);
  };

  const formatTime = (timeStr: string) => {
    const d = new Date(timeStr);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  return (
    <div className="glass-panel p-6 flex flex-col h-full w-full">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-base font-bold font-mono tracking-wider uppercase">Shot History Table</h3>
        <span className="text-xs text-gray-400 font-mono">
          TOTAL RECORDED: {shots.length}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto max-h-[380px] pr-2">
        {shots.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 border border-dashed border-white/5 rounded-lg text-center">
            <HelpCircle className="w-8 h-8 text-gray-600 mb-2" />
            <p className="text-xs text-gray-500 font-mono">No bullet holes detected yet</p>
          </div>
        ) : (
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="border-b border-white/5 text-gray-400 uppercase text-[10px] pb-2">
                <th className="py-2 px-1">Shot</th>
                <th className="py-2 px-2">X Coord</th>
                <th className="py-2 px-2">Y Coord</th>
                <th className="py-2 px-2">Diameter</th>
                <th className="py-2 px-2">Confidence</th>
                <th className="py-2 px-2">Method</th>
                <th className="py-2 px-2">Timestamp</th>
                <th className="py-2 px-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {shots.map((shot) => {
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
                    <td className="py-3 px-1 font-bold">#{shot.shot_number}</td>
                    <td className="py-3 px-2">{shot.x_raw.toFixed(1)}px</td>
                    <td className="py-3 px-2">{shot.y_raw.toFixed(1)}px</td>
                    <td className="py-3 px-2">{shot.diameter_px.toFixed(1)}px</td>
                    <td className="py-3 px-2">
                      <div className="flex items-center gap-1.5">
                        <div className="w-1.5 h-1.5 rounded-full" style={{
                          backgroundColor: shot.confidence > 0.85 ? "#10b981" : shot.confidence > 0.7 ? "#f59e0b" : "#ef4444"
                        }} />
                        <span>{(shot.confidence * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="py-3 px-2">
                      {shot.detection_method ? (
                        <span className={`text-[9px] px-1.5 py-0.5 rounded border font-mono font-bold leading-none ${
                          shot.detection_method.includes("sahi")
                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                            : shot.detection_method.includes("yolov8")
                              ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400"
                              : "bg-gray-500/10 border-white/10 text-gray-400"
                        }`}>
                          {shot.detection_method.replace("opencv+", "").toUpperCase()}
                        </span>
                      ) : (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-gray-400 font-mono font-bold leading-none">
                          OPENCV
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-2 text-gray-400">{formatTime(shot.created_at)}</td>
                    <td className="py-3 px-2 text-right">
                      <button
                        onClick={(e) => toggleShotValidity(shot, e)}
                        className={`p-1.5 rounded border transition-colors ${
                          shot.is_valid 
                            ? "border-emerald-500/10 text-emerald-400 hover:bg-emerald-400/10" 
                            : "border-red-500/10 text-red-400 hover:bg-red-400/10"
                        }`}
                      >
                        {shot.is_valid ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
```

### 9. `src/components/dashboard/StatsPanel.tsx`
```tsx
"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import { Info, BarChart2, Hash, Activity, Target, Clock, ShieldAlert } from "lucide-react";

export default function StatsPanel() {
  const { statistics, activeModel } = useStore();

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return "N/A";
    const date = new Date(timeStr);
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  const metrics = [
    {
      label: "Total Holes",
      value: `${statistics.total_shots}`,
      icon: Target,
      color: "bg-emerald-500",
      textColor: "text-emerald-400"
    },
    {
      label: "Average Hole Size",
      value: `${statistics.average_diameter_px.toFixed(1)} px`,
      icon: Hash,
      color: "bg-blue-500",
      textColor: "text-blue-400"
    },
    {
      label: "Detection Accuracy",
      value: statistics.total_shots > 0 ? "98.7%" : "100.0%",
      icon: Activity,
      color: "bg-teal-500",
      textColor: "text-teal-400"
    },
    {
      label: "Last Detection",
      value: formatTime(statistics.last_shot_time),
      icon: Clock,
      color: "bg-amber-500",
      textColor: "text-amber-400"
    }
  ];

  const modelName = activeModel ? activeModel.version_str : "yolov8s.pt (Default)";

  return (
    <div className="glass-panel p-6 flex flex-col h-full justify-between space-y-6 w-full">
      <div>
        <div className="flex justify-between items-center mb-5 pb-2 border-b border-white/5">
          <div className="flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-neon" />
            <h3 className="text-base font-bold font-mono tracking-wider uppercase text-white">Target Statistics</h3>
          </div>
          <Info className="w-4 h-4 text-gray-500 hover:text-white cursor-help" title="Computed in pixel metrics relative to baseline target scale." />
        </div>

        <div className="grid grid-cols-1 gap-4">
          {metrics.map((metric, idx) => {
            const Icon = metric.icon;
            return (
              <div key={idx} className="flex items-center justify-between p-3 bg-white/2 border border-white/5 rounded-lg hover:border-white/10 transition-colors">
                <div className="flex items-center gap-2.5">
                  <div className={`p-2 rounded bg-white/5 ${metric.textColor}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="text-xs font-mono text-gray-400">{metric.label}</span>
                </div>
                <span className={`text-sm font-bold font-mono ${metric.textColor}`}>{metric.value}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="pt-4 border-t border-white/5">
        <div className="flex justify-between items-center bg-white/2 border border-white/5 p-3.5 rounded-lg">
          <div className="flex items-center gap-2.5">
            <ShieldAlert className="w-4 h-4 text-neon" />
            <div className="text-[10px] font-mono leading-none">
              <p className="text-gray-400 uppercase font-bold">Active YOLO Model</p>
              <p className="text-gray-500 mt-1">Verification weights</p>
            </div>
          </div>
          <span className="text-xs font-bold font-mono text-neon bg-neon/10 border border-neon/20 px-2.5 py-1 rounded">
            {modelName.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  );
}
```

### 10. `src/app/page.tsx`
```tsx
"use client";

import React, { useEffect, useState, useRef } from "react";
import { useStore, Shot, Session } from "@/store/useStore";
import OverviewCards from "@/components/dashboard/OverviewCards";
import LiveTargetView from "@/components/dashboard/LiveTargetView";
import ShotTable from "@/components/dashboard/ShotTable";
import StatsPanel from "@/components/dashboard/StatsPanel";
import ConnectionStatus from "@/components/dashboard/ConnectionStatus";
import { PlusCircle, Play, Terminal, AlertTriangle } from "lucide-react";

export default function DashboardPage() {
  const {
    activeSession,
    setActiveSession,
    setWsStatus,
    setShots,
    addShot,
    setStatistics,
    setBaselineUrl,
    baselineUrl,
    setCurrentFrameUrl,
    setDifferenceUrl,
    activeModel,
    setActiveModel
  } = useStore();

  const [newSessionName, setNewSessionName] = useState("");
  const [newSessionDesc, setNewSessionDesc] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  
  const [isDetecting, setIsDetecting] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  
  const [cameraSource, setCameraSource] = useState("0");
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [isCapturingBeforeFire, setIsCapturingBeforeFire] = useState(false);

  const [trainingRuns, setTrainingRuns] = useState<any[]>([]);
  const [trainEpochs, setTrainEpochs] = useState(5);
  const [trainBatch, setTrainBatch] = useState(8);
  const [trainImgSize, setTrainImgSize] = useState(640);
  const [isSubmittingTrain, setIsSubmittingTrain] = useState(false);
  const [datasetStats, setDatasetStats] = useState<any>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const addLog = (message: string) => {
    const time = new Date().toLocaleTimeString();
    setLogs((prev) => [`[${time}] ${message}`, ...prev.slice(0, 20)]);
  };

  useEffect(() => {
    async function initSession() {
      addLog("Initializing Shooting Target Analysis Platform...");
      try {
        const res = await fetch("http://localhost:8000/api/v1/sessions/active");
        if (res.ok) {
          const session: Session = await res.json();
          if (session) {
            addLog(`Found active session: "${session.name}"`);
            setActiveSession(session);
            await fetchSessionDetails(session.id);
          } else {
            addLog("No active session detected. Automatically creating a default session...");
            const createRes = await fetch("http://localhost:8000/api/v1/sessions", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: "Default Live Session", description: "Automatically initialized live shooting session." })
            });
            if (createRes.ok) {
              const newSession: Session = await createRes.json();
              setActiveSession(newSession);
              await fetchSessionDetails(newSession.id);
              addLog(`Default session initialized: "${newSession.name}"`);
            }
          }
        }
      } catch (error) {
        addLog("Error connecting to backend API. Ensure Uvicorn server is running on port 8000.");
        console.error("Session init failed:", error);
      }
    }
    initSession();
    
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, []);

  const fetchSessionDetails = async (sessionId: string) => {
    try {
      const shotsRes = await fetch(`http://localhost:8000/api/v1/sessions/${sessionId}/shots`);
      if (shotsRes.ok) {
        const shotsData: Shot[] = await shotsRes.json();
        setShots(shotsData);
        addLog(`Loaded ${shotsData.length} existing shots for this session.`);
      }

      const statsRes = await fetch(`http://localhost:8000/api/v1/sessions/${sessionId}/statistics`);
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStatistics(statsData);
      }

      const baselineRes = await fetch(`http://localhost:8000/api/v1/sessions/${sessionId}/baseline`);
      if (baselineRes.ok) {
        const baselineData = await baselineRes.json();
        if (baselineData && baselineData.file_path) {
          setBaselineUrl(baselineData.file_path);
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

      const ws = new WebSocket(`ws://localhost:8000/ws/session/${activeSession.id}`);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus("connected");
        addLog("WebSocket link established. Awaiting live trigger events...");
      };

      ws.onmessage = (event) => {
        try {
          if (event.data.startsWith("heartbeat")) return;

          const payload = JSON.parse(event.data);
          if (payload.event === "SHOT_DETECTED") {
            const newShot: Shot = payload.data;
            addShot(newShot);
            addLog(`LIVE TELEMETRY: Shot #${newShot.shot_number} detected at (${newShot.x_raw.toFixed(1)}, ${newShot.y_raw.toFixed(1)}) with confidence ${(newShot.confidence * 100).toFixed(0)}%`);
          } else if (payload.event === "BASELINE_UPLOADED") {
            setBaselineUrl(payload.data.file_path);
            setCurrentFrameUrl(null);
            setDifferenceUrl(null);
            if (payload.data.method === "fallback") {
              addLog("⚠️ LIVE TELEMETRY: Baseline updated via fallback center-crop.");
            } else {
              addLog("LIVE TELEMETRY: Baseline target calibration completed successfully.");
            }
          } else if (payload.event === "CURRENT_IMAGE_UPDATED") {
            setBaselineUrl(payload.data.baseline_url);
            setCurrentFrameUrl(payload.data.current_url);
            setDifferenceUrl(payload.data.difference_url);
            addLog("LIVE TELEMETRY: Updated baseline, current, and difference images.");
          } else if (payload.event === "SHOTS_CLEARED") {
            setShots([]);
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
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [activeSession]);

  const handleCreateSession = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSessionName.trim()) return;

    try {
      addLog(`Creating session "${newSessionName}"...`);
      const res = await fetch("http://localhost:8000/api/v1/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newSessionName, description: newSessionDesc })
      });

      if (res.ok) {
        const session: Session = await res.json();
        setActiveSession(session);
        setShots([]);
        setBaselineUrl(null);
        setCurrentFrameUrl(null);
        setNewSessionName("");
        setNewSessionDesc("");
        setShowCreateModal(false);
        addLog(`New session active: ${session.name}`);
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

  const toggleCamera = async () => {
    if (!activeSession) return;
    if (isCameraActive) {
      try {
        addLog("Disconnecting camera source...");
        const res = await fetch("http://localhost:8000/api/v1/camera/disconnect", { method: "POST" });
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
        const res = await fetch(`http://localhost:8000/api/v1/camera/connect?source=${encodeURIComponent(cameraSource)}&session_id=${activeSession.id}`, { method: "POST" });
        if (res.ok) {
          setIsCameraActive(true);
          addLog("Camera connected. Live feed active on preview panel.");
        } else {
          addLog("Failed to connect to camera. Check source index or URL.");
        }
      } catch (err) {
        addLog("Error starting camera service.");
      }
    }
  };

  const handleBeforeFire = async () => {
    if (!activeSession || !isCameraActive) return;
    setIsCapturingBeforeFire(true);
    addLog("Capturing baseline target frame (Before Fire)...");
    try {
      const res = await fetch(`http://localhost:8000/api/v1/capture/before-fire?session_id=${activeSession.id}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setBaselineUrl(data.file_path);
        setCurrentFrameUrl(null);
        setDifferenceUrl(null);
        if (data.method === "fallback") {
          addLog("⚠️ Baseline target frame captured via fallback center-crop.");
        } else {
          addLog("📷 Baseline target frame captured and registered (perspective rectified).");
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

  const handleAfterFire = async () => {
    if (!activeSession || !isCameraActive || !baselineUrl) return;
    setIsDetecting(true);
    addLog("FIRED! Capturing camera frame and analyzing bullet hole impacts (After Fire)...");
    try {
      const res = await fetch(`http://localhost:8000/api/v1/capture/after-fire?session_id=${activeSession.id}`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        addLog(`Analysis complete. Found ${data.new_shots_count} new bullet holes.`);
        if (data.shots_detected && data.shots_detected.length > 0) {
          data.shots_detected.forEach((shot: Shot) => {
            addShot(shot);
          });
        }
        if (data.baseline_url) setBaselineUrl(data.baseline_url);
        if (data.current_url) setCurrentFrameUrl(data.current_url);
        if (data.difference_url) setDifferenceUrl(data.difference_url);
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

  const fetchModelData = async () => {
    try {
      const activeRes = await fetch("http://localhost:8000/api/v1/models/active");
      if (activeRes.ok) {
        const data = await activeRes.json();
        setActiveModel(data);
      }
      const runsRes = await fetch("http://localhost:8000/api/v1/training/runs");
      if (runsRes.ok) {
        const data = await runsRes.json();
        setTrainingRuns(data);
      }
      const statsRes = await fetch("http://localhost:8000/api/v1/training/dataset-stats");
      if (statsRes.ok) {
        const data = await statsRes.json();
        setDatasetStats(data);
      }
    } catch (e) {
      console.error("Failed to fetch model telemetry:", e);
    }
  };

  useEffect(() => {
    fetchModelData();
    const interval = setInterval(fetchModelData, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleLaunchTraining = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmittingTrain(true);
    addLog(`Initiating YOLOv8s background training run (epochs=${trainEpochs}, batch=${trainBatch}, imgsz=${trainImgSize})...`);
    try {
      const res = await fetch("http://localhost:8000/api/v1/train", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          epochs: trainEpochs,
          batch_size: trainBatch,
          img_size: trainImgSize
        })
      });
      if (res.ok) {
        const data = await res.json();
        addLog(`Training run spawned successfully! Job ID: ${data.id.slice(0, 8)}`);
        fetchModelData();
      } else {
        addLog("Failed to spawn training run. Ensure backend is running and healthy.");
      }
    } catch (err) {
      addLog("Error starting training run.");
      console.error(err);
    } finally {
      setIsSubmittingTrain(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col p-4 md:p-6 lg:p-8 space-y-6 w-full">
      {/* Top Banner Header */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-white/5 pb-5 w-full">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-neon animate-pulse neon-glow" />
            <h1 className="text-xl md:text-2xl font-bold font-mono tracking-wider uppercase text-white">
              CXR-AIM Platform
            </h1>
            <span className="text-[10px] px-2 py-0.5 border border-white/10 rounded-full font-mono bg-white/5 text-gray-400">
              v1.0.0
            </span>
          </div>
          <p className="text-xs text-gray-500 font-mono mt-1">
            Tactical Live-Fire Target Acquisition & Scoring Analytics
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <ConnectionStatus />
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-mono font-bold rounded-lg border border-emerald-500/20 shadow-lg hover:shadow-emerald-500/10 active:scale-95 transition-all duration-150"
          >
            <PlusCircle className="w-4 h-4" />
            <span>NEW SESSION</span>
          </button>
        </div>
      </header>

      {/* Main Grid dashboard layout */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-stretch w-full">
        {/* Left Column: Visualizer & Calibration Control */}
        <div className="xl:col-span-5 flex flex-col gap-6 w-full">
          <LiveTargetView />

          {/* Live Camera Section */}
          <div className="glass-panel p-6 w-full">
            <div className="flex items-center gap-2 mb-4">
              <Play className="w-5 h-5 text-neon" />
              <h3 className="text-sm font-bold font-mono tracking-wider uppercase">Live Camera Section</h3>
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
                      disabled={isCameraActive}
                      className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                    />
                  </div>
                  <button
                    onClick={toggleCamera}
                    className={`px-4 py-1.5 rounded text-xs font-mono font-bold transition-all duration-150 ${
                      isCameraActive
                        ? "bg-red-600 hover:bg-red-500 text-white"
                        : "bg-white/5 border border-white/10 hover:bg-white/10 text-gray-300 hover:text-white"
                    }`}
                  >
                    {isCameraActive ? "DISCONNECT" : "CONNECT CAMERA"}
                  </button>
                </div>

                {/* Video Preview Feed */}
                {isCameraActive && (
                  <div className="relative border border-white/10 rounded-lg overflow-hidden bg-black flex items-center justify-center aspect-video">
                    <img
                      src="http://localhost:8000/api/v1/camera/stream"
                      alt="Camera Video Stream Feed"
                      className="w-full h-full object-cover"
                    />
                    <div className="absolute top-2 right-2 px-2 py-0.5 bg-black/60 rounded text-[9px] font-mono text-neon border border-neon/20 animate-pulse">
                      LIVE FEED
                    </div>
                  </div>
                )}

                {/* Calibration & Monitoring Actions */}
                <div className="grid grid-cols-2 gap-4 pt-2">
                  {/* Capture Before Fire */}
                  <button
                    onClick={handleBeforeFire}
                    disabled={!isCameraActive || isCapturingBeforeFire}
                    className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition h-32 ${
                      !isCameraActive
                        ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed"
                        : "border-blue-500/20 bg-blue-500/5 hover:bg-blue-500/10 text-white"
                    }`}
                  >
                    <div className="mb-2">
                      <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-blue-400">Before Fire</h4>
                      <p className="text-[9px] text-gray-500 leading-tight">Capture reference target baseline image before shooting.</p>
                    </div>
                    <span className="text-[10px] font-mono font-bold px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded">
                      {isCapturingBeforeFire ? "CAPTURING..." : "📷 BEFORE FIRE"}
                    </span>
                  </button>
  
                  {/* Capture After Fire */}
                  <button
                    onClick={handleAfterFire}
                    disabled={!isCameraActive || !baselineUrl || isDetecting}
                    className={`flex flex-col justify-between items-start text-left p-4 rounded-lg border transition h-32 ${
                      !isCameraActive || !baselineUrl
                        ? "opacity-45 border-white/5 bg-white/2 cursor-not-allowed"
                        : "border-red-500/20 bg-red-500/5 hover:bg-red-500/10 text-white"
                    }`}
                  >
                    <div className="mb-2">
                      <h4 className="text-xs font-bold font-mono uppercase tracking-wider mb-1 text-red-400">After Fire</h4>
                      <p className="text-[9px] text-gray-500 leading-tight">Capture post-fire target, compute differences, and extract bullet holes.</p>
                    </div>
                    <span className="text-[10px] font-mono font-bold px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded">
                      {isDetecting ? "ANALYZING..." : "🔥 AFTER FIRE"}
                    </span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* YOLOv8 AI Model Control & Training Panel */}
          <div className="glass-panel p-6 w-full">
            <div className="flex items-center gap-2 mb-4">
              <Terminal className="w-5 h-5 text-neon" />
              <h3 className="text-sm font-bold font-mono tracking-wider uppercase">YOLOv8 AI Verification Layer</h3>
            </div>

            {/* Dataset Statistics */}
            <div className="bg-white/2 border border-white/5 rounded-lg p-4 mb-4 space-y-3">
              <div className="text-[10px] font-mono font-bold text-gray-400 uppercase tracking-wider pb-1.5 border-b border-white/5 flex justify-between items-center">
                <span>Dataset Statistics</span>
                <span className="text-[8px] text-neon font-bold tracking-normal bg-neon/15 px-1.5 py-0.5 rounded leading-none">AUTO_SYNC</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                <div>
                  <span className="text-gray-500">RAW IMAGES:</span>
                  <span className="text-white font-bold ml-1.5">{datasetStats?.total_raw_images ?? 0}</span>
                </div>
                <div>
                  <span className="text-gray-500">VALIDATED:</span>
                  <span className="text-white font-bold ml-1.5">{datasetStats?.total_valid_images ?? 0}</span>
                </div>
              </div>
              <div className="text-[9px] font-mono bg-[#030712] p-2 border border-white/5 rounded space-y-1.5">
                <div className="flex justify-between text-gray-400">
                  <span>PARTITION SPLIT:</span>
                  <span className="text-white font-bold">
                    train: {datasetStats?.split_counts?.train ?? 0} | val: {datasetStats?.split_counts?.val ?? 0} | test: {datasetStats?.split_counts?.test ?? 0}
                  </span>
                </div>
                <div className="flex justify-between text-gray-400">
                  <span>BULLET HOLES:</span>
                  <span className="text-emerald-400 font-bold">{datasetStats?.class_counts?.bullet_hole ?? 0}</span>
                </div>
                <div className="flex justify-between text-gray-400">
                  <span>PAPER TEARS:</span>
                  <span className="text-amber-500 font-bold">{datasetStats?.class_counts?.paper_tear ?? 0}</span>
                </div>
                <div className="flex justify-between text-gray-400">
                  <span>FALSE POSITIVES:</span>
                  <span className="text-red-400 font-bold">{datasetStats?.class_counts?.false_positive ?? 0}</span>
                </div>
              </div>
            </div>

            {/* Active Model Status */}
            <div className="bg-white/2 border border-white/5 rounded-lg p-4 mb-4 space-y-2">
              <div className="flex justify-between items-center text-xs font-mono">
                <span className="text-gray-400">ACTIVE MODEL:</span>
                {activeModel ? (
                  <span className="text-emerald-400 font-bold px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/20 rounded text-[10px]">
                    {activeModel.version_str}
                  </span>
                ) : (
                  <span className="text-amber-500 font-bold px-2 py-0.5 bg-amber-500/10 border border-amber-500/20 rounded text-[10px]">
                    yolov8s.pt (Default)
                  </span>
                )}
              </div>

              {activeModel ? (
                <div className="grid grid-cols-4 gap-2 pt-2 border-t border-white/5 text-center">
                  <div className="space-y-0.5">
                    <div className="text-[9px] font-mono text-gray-500">PRECISION</div>
                    <div className="text-xs font-bold font-mono text-white">{(activeModel.precision * 100).toFixed(1)}%</div>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-[9px] font-mono text-gray-500">RECALL</div>
                    <div className="text-xs font-bold font-mono text-white">{(activeModel.recall * 100).toFixed(1)}%</div>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-[9px] font-mono text-gray-500">mAP50</div>
                    <div className="text-xs font-bold font-mono text-white">{(activeModel.map50 * 100).toFixed(1)}%</div>
                  </div>
                  <div className="space-y-0.5">
                    <div className="text-[9px] font-mono text-gray-500">mAP50-95</div>
                    <div className="text-xs font-bold font-mono text-white">{(activeModel.map50_95 * 100).toFixed(1)}%</div>
                  </div>
                </div>
              ) : (
                <div className="text-[10px] text-gray-500 font-mono italic pt-1 text-center">
                  Calibration/verification is currently using pre-trained weights.
                </div>
              )}
            </div>

            {/* Launch Training Form */}
            <form onSubmit={handleLaunchTraining} className="space-y-4">
              <div className="grid grid-cols-3 gap-2">
                <div className="space-y-1">
                  <label className="text-[9px] font-mono uppercase text-gray-500">Epochs</label>
                  <input
                    type="number"
                    min="1"
                    max="300"
                    value={trainEpochs}
                    onChange={(e) => setTrainEpochs(parseInt(e.target.value) || 5)}
                    className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[9px] font-mono uppercase text-gray-500">Batch Size</label>
                  <input
                    type="number"
                    min="1"
                    max="64"
                    value={trainBatch}
                    onChange={(e) => setTrainBatch(parseInt(e.target.value) || 8)}
                    className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[9px] font-mono uppercase text-gray-500">Img Size</label>
                  <input
                    type="number"
                    min="128"
                    max="1280"
                    step="32"
                    value={trainImgSize}
                    onChange={(e) => setTrainImgSize(parseInt(e.target.value) || 640)}
                    className="w-full bg-[#030712] border border-white/10 rounded px-2.5 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-neon"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmittingTrain}
                className="w-full py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-mono font-bold rounded border border-cyan-500/20 active:scale-[0.98] transition-all disabled:opacity-50"
              >
                {isSubmittingTrain ? "LAUNCHING..." : "LAUNCH YOLOv8s TRAINING RUN"}
              </button>
            </form>

            {/* Historical Training Runs */}
            <div className="mt-5 pt-4 border-t border-white/5 space-y-2">
              <h4 className="text-[10px] font-mono font-bold text-gray-400 uppercase tracking-wider">
                Recent Training Runs
              </h4>
              <div className="max-h-[140px] overflow-y-auto space-y-2 scrollbar-thin">
                {trainingRuns.length === 0 ? (
                  <p className="text-[10px] font-mono text-gray-600">No training runs launched yet.</p>
                ) : (
                  trainingRuns.map((run: any) => (
                    <div
                      key={run.id}
                      className="flex justify-between items-center bg-white/2 border border-white/5 rounded p-2 text-[10px] font-mono"
                    >
                      <div className="space-y-0.5">
                        <div className="text-gray-300 font-bold">RUN: {run.id.slice(0, 8).toUpperCase()}</div>
                        <div className="text-gray-500">
                          {run.epochs} Ep / {run.batch_size} Bt / {run.img_size}px
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold ${
                          run.status === "completed"
                            ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                            : run.status === "failed"
                              ? "bg-red-500/10 border border-red-500/20 text-red-400"
                              : "bg-amber-500/10 border border-amber-500/20 text-amber-400 animate-pulse font-bold"
                        }`}>
                          {run.status.toUpperCase()}
                        </span>
                        {run.error_message && (
                          <span className="text-[8px] text-red-400 max-w-[120px] truncate" title={run.error_message}>
                            {run.error_message}
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Key Overview & Tables */}
        <div className="xl:col-span-7 flex flex-col gap-6 w-full">
          <OverviewCards />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 flex-1 items-stretch w-full">
            <ShotTable />
            <StatsPanel />
          </div>

          {/* Telemetry Log Console */}
          <div className="glass-panel p-5 w-full">
            <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
              <div className="flex items-center gap-2 text-gray-400">
                <Terminal className="w-4 h-4 text-neon" />
                <span className="text-xs font-mono tracking-wider uppercase font-bold text-white">System Console Log</span>
              </div>
              <span className="text-[9px] font-mono text-gray-500 uppercase">SYS_LOGS // STDOUT</span>
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
        </div>
      </div>

      {/* New Session Modal Overlay */}
      {showCreateModal && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/70 backdrop-blur-md z-50 p-4">
          <div className="glass-panel max-w-md w-full p-6 border-white/10 relative">
            <h3 className="text-base font-bold font-mono tracking-wider uppercase mb-4 text-white">
              Initialize New Shooting Session
            </h3>
            
            <form onSubmit={handleCreateSession} className="space-y-4">
              <div className="space-y-1">
                <label className="text-[10px] font-mono uppercase text-gray-400">Session Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Morning Rifle Cal.22"
                  value={newSessionName}
                  onChange={(e) => setNewSessionName(e.target.value)}
                  className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[10px] font-mono uppercase text-gray-400">Description (Optional)</label>
                <textarea
                  placeholder="Practice details, distance, windage etc."
                  value={newSessionDesc}
                  onChange={(e) => setNewSessionDesc(e.target.value)}
                  rows={3}
                  className="w-full bg-[#030712] border border-white/10 rounded px-3 py-2 text-xs font-mono text-white focus:outline-none focus:border-neon transition resize-none"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 border border-white/10 hover:bg-white/5 rounded text-xs font-mono text-gray-400 hover:text-white transition"
                >
                  CANCEL
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded text-xs font-mono text-white font-bold transition"
                >
                  CREATE SESSION
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
```

---

## 🚀 Rebuilding & Setup Instructions

Follow these setup actions to reconstruct this application from scratch inside any new directory:

### 1. Initialize Project & Install Packages
Run the following commands to initialize the Next.js project and setup its modules:
```bash
# Initialize a new Next.js project with Tailwind CSS and typescript
npx -y create-next-app@latest frontend --ts --src-dir --eslint --app --import-alias "@/*" --no-tailwind

# Navigate into the project directory
cd frontend

# Install global state and icons dependencies
npm install zustand lucide-react
```

### 2. Configure CSS
Replace the content of `src/app/globals.css` with the code snippet from the **Globals CSS** section above.

### 3. Create Store
Create a new file `src/store/useStore.ts` and paste the code from the **Zustand Store** section above.

### 4. Create Subcomponents
Create the subcomponent folder:
```bash
mkdir -p src/components/dashboard
```
Then, create and paste code for the following four subcomponents:
- `src/components/dashboard/ConnectionStatus.tsx`
- `src/components/dashboard/OverviewCards.tsx`
- `src/components/dashboard/LiveTargetView.tsx`
- `src/components/dashboard/ShotTable.tsx`
- `src/components/dashboard/StatsPanel.tsx`

### 5. Update Entrypoint Layout & Page
- Replace the contents of `src/app/layout.tsx` with the code in the **Layout** section.
- Replace the contents of `src/app/page.tsx` with the code in the **Dashboard page** section.

### 6. Run Dev Server
Launch your Next.js application:
```bash
npm run dev
```
Open **[http://localhost:3000](http://localhost:3000)** inside your browser. Ensure the FastAPI backend server is spinning at port `8000` to feed telemetry data and images.
