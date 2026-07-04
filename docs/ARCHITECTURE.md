# CXR-AIM — Architecture & Pipeline Reference

> **CXR-AIM** (Computer Vision eXtended Range – AI Marksmanship) is a shooting-target analytics
> platform: it watches a target through a camera, detects each **new bullet hole**, scores it against
> a configurable target template, and streams everything to a live web dashboard.

This document describes the full architecture and **exactly which modules/scripts are responsible for
each pipeline**, so you can trace any feature end-to-end.

---

## 1. High-Level System

```
┌──────────────┐     HTTP / WebSocket / MJPEG      ┌───────────────────────────┐
│   Frontend   │  ◄──────────────────────────────► │         Backend            │
│  Next.js     │                                    │   FastAPI (app/main.py)    │
│  dashboard   │                                    │                            │
└──────────────┘                                    │  services/   scoring/      │
                                                     │  models/     scoring eng.  │
        ▲                                            └─────────────┬─────────────┘
        │                                                          │
        │                                                          ▼
   Web browser                                          ┌────────────────────┐
   (localhost:3000)                                     │  SQLite / Postgres  │
                                                        │  + uploads/ images  │
                                                        └────────────────────┘
        ▲
        │ USB / IP / DroidCam
   ┌─────────┐
   │ Camera  │  → physical target with 4 AprilTags
   └─────────┘
```

- **Backend:** Python 3.12, FastAPI, async SQLAlchemy. Entry: `backend/run.py` → `backend/app/main.py`.
- **Frontend:** Next.js (App Router) + Zustand store. Entry: `frontend/src/app/page.tsx`.
- **Launcher:** `start_platform.py` provisions venv + npm, starts both servers.
- **Database:** SQLite by default (`data/target_analysis.db`), PostgreSQL-ready.
- **Compute:** YOLOv8s + PyTorch on **GPU (CUDA) if available**, else CPU.

---

## 2. Directory / Module Map

### Backend (`backend/app/`)
| Path | Responsibility |
|---|---|
| `main.py` | FastAPI app — **all HTTP routes, WebSocket, pipeline orchestration** |
| `run.py` | Uvicorn dev runner (auto-reload) |
| `core/config.py` | Settings (DB URL, upload dir, SAHI flags) |
| `core/database.py` | Async engine/session + **idempotent additive migrations** |
| `models/models.py` | ORM tables: `Session`, `Image`, `Shot`, `Detection`, `ModelVersion`, `TrainingRun` |
| `schemas/schemas.py` | Pydantic request/response schemas |
| **`services/camera_service.py`** | Camera lifecycle, AprilTag calibration, perspective warp, Before/After capture |
| **`services/apriltag_service.py`** | AprilTag detection + paper-corner recovery + A4 warp |
| **`services/cv_engine.py`** | **OpenCV difference engine** — primary bullet-hole candidate detector |
| **`services/ai_verifier.py`** | **YOLOv8s / SAHI verification** layer (confirms/rejects candidates) |
| `services/scoring_service.py` | Warped-pixel → mm scoring, projected zones, calibration debug image |
| `services/zone_geometry.py` | **Target Geometry Alignment** — detect printed zones, fit scale+shift homography |
| `services/ws_manager.py` | WebSocket broadcast manager |
| `scoring/target_definition.py` | Target template model (rings/zones, JSON load/save) |
| `scoring/scoring_engine.py` | Integer + decimal score from impact mm |
| `scoring/boundary_verification.py` | Line-break confidence (certain / probable / review) |
| `scoring/coordinate_transformer.py` | px ↔ mm projective transforms |

### Root scripts
| Script | Responsibility |
|---|---|
| `start_platform.py` | One-command launcher (banner, provisioning, runs both servers) |
| `dataset_pipeline.py` | Pascal VOC XML → YOLO format, train/val/test split, dataset report |
| `train.py` | YOLOv8s training pipeline + model-registry registration + hot-swap |
| `inference.py` | Standalone CLI inference on an image pair |
| `scripts/verify_detection.py` | Offline detection regression check on a baseline/capture pair |
| `scripts/probe_cams.py` | Enumerate working camera indices/backends |

### Frontend (`frontend/src/`)
| Path | Responsibility |
|---|---|
| `app/page.tsx` | Dashboard root — session init, WebSocket, camera/capture/training controls |
| `store/useStore.ts` | Zustand global state (shots, stats, zones, targets) |
| `components/dashboard/LiveTargetView.tsx` | **Image Review Station** — Overlay/Calibration/Homographed/Current/Difference/2×2 |
| `components/dashboard/TargetSettings.tsx` | Target select, caliber, **Align Zones**, New Target |
| `components/dashboard/TargetDesigner.tsx` | Canvas target creator (draw zones/rings) |
| `components/dashboard/TargetPreview.tsx` | SVG/image preview of a target template |
| `components/dashboard/ShotTable.tsx` | Per-shot table (score, coords, method) |
| `components/dashboard/OverviewCards.tsx` | Total score / holes / session / sensor cards |
| `components/dashboard/StatsPanel.tsx` | Aggregate statistics |
| `components/dashboard/ToastHost.tsx` + `lib/sound.ts` | Toast alerts + Web-Audio sound cues |

---

## 3. THE BULLET-DETECTION PIPELINE  ⟵ most important

**Architecture rule:** YOLO is **not** the primary detector. The target is static; only new holes
change. A fast **OpenCV difference engine** finds *what changed* → **YOLO verifies** *whether it's a
hole*. This is intentional and must be preserved.

```
Live feed ─► BEFORE FIRE ─► (warp) ─► baseline ─┐
                                                 ▼
shooter fires ─► AFTER FIRE ─► (warp) ─► current │
                                                 ▼
            ┌──────────────  cv_engine.detect_holes()  ──────────────┐
            │ ORB align → background-agnostic diff → edge/tag mask    │
            │ → morphology → contour shape filters → CANDIDATES       │
            └───────────────────────────┬────────────────────────────┘
                                         ▼
            ┌──────  ai_verifier.verify_candidate_roi()  ──────┐
            │ full-image YOLOv8s (custom model) / ROI / SAHI    │
            │ → confirm or reject each candidate                │
            └───────────────────────────┬───────────────────────┘
                                         ▼
            dedup vs existing shots ─► scoring ─► DB ─► WebSocket ─► dashboard
```

### Scripts/modules involved in bullet detection (in call order)

| # | Module · function | Role |
|---|---|---|
| 1 | `app/main.py` → `capture_before_fire()` | Captures + warps the **baseline**, clears old shots, resets alignment |
| 2 | `services/camera_service.py` → `calibrate_homography()`, `rectify_frame()` | AprilTag-based **perspective warp** to 1000×1000 |
| 3 | `services/apriltag_service.py` → `detect_and_warp()`, `detect_tags()` | Detect tags, recover paper corners, warp |
| 4 | `app/main.py` → `capture_after_fire()` / `run_detect()` / `run_detection()` | Orchestrates a detection run |
| 5 | **`services/cv_engine.py` → `detect_holes()`** | **Primary detector.** ORB align (`align_images`), absolute-difference + new-dark mask, **edge-based jitter suppression**, AprilTag exclusion (`_baseline_exclusion_mask`), morphology, contour filters (area/circularity/solidity/aspect/border) → candidate list |
| 6 | **`services/ai_verifier.py` → `verify_candidate_roi()`** | **Verification.** Runs the active custom YOLOv8s model (full-image match, ROI crop, or SAHI). Returns verified/conf/class. Falls back to a strict OpenCV shape check if YOLO misses |
| 7 | `services/ai_verifier.py` → `run_sahi_inference()`, `_apply_nms()` | Optional sliced inference for tiny ROIs (off by default) |
| 8 | `app/main.py` → `apply_scoring_to_shot()` | Scores the confirmed hole (see §4) |
| 9 | `models/models.py` (`Shot`, `Detection`) | Persists shot + detection metrics |
| 10 | `services/ws_manager.py` → `broadcast_to_session()` | Pushes `SHOT_DETECTED` to the dashboard |
| 11 | `components/dashboard/LiveTargetView.tsx` | Draws the hole, contour, number, score on the canvas |

**Key detection properties**
- Works on **white sheets and dark silhouettes** (background-agnostic diff: catches dark-on-white *and* light-on-black torn paper).
- **AprilTags** are detected by a dedicated library, never trained into YOLO; tag regions are masked out of detection.
- Warp-jitter false positives are suppressed at baseline **edges**, not whole dark regions.
- Offline regression: `scripts/verify_detection.py <baseline> <capture>`.

---

## 4. THE SCORING PIPELINE

```
detected shot (x_raw, y_raw in 1000×1000 warped px)
        │
        ▼  scoring_service.warped_to_mm()  →  observed mm
        │      (optional) apply inverse geometry homography → template mm
        ▼
scoring/scoring_engine.py  →  integer + decimal score, nearest ring, distance
        │
        ▼
scoring/boundary_verification.py  →  line-break confidence
        │
        ▼  stored on Shot, broadcast, shown in ShotTable / OverviewCards
```

| Module · function | Role |
|---|---|
| `services/scoring_service.py` → `score_warped_shot()` | Converts warped px → mm, applies alignment, calls engine |
| `scoring/scoring_engine.py` → `score_shot()` | Ring (inward/outward) **and** rectangular-zone scoring; ISSF decimals |
| `scoring/boundary_verification.py` → `verify_boundary()` | certain / probable / review_required |
| `scoring/target_definition.py` | Loads target templates from `backend/configs/targets/*.json` |
| `app/main.py` → `apply_scoring_to_shot()`, `build_shot_response()` | Wire-up + response with score fields |

---

## 5. TARGET GEOMETRY ALIGNMENT PIPELINE (homography / zone fit)

Corrects "digital template ≠ real print" (print scale, stretch, offset).

```
warped baseline ─► zone_geometry.compute_geometry_homography()
   detect printed rectangles (_detect_scoring_zone_quads) / rings (_detect_scoring_zone_ellipses)
   → match to template zones (_match_quad_to_region)
   → least-squares SCALE+TRANSLATE fit (robust; no spurious rotation/shear)
   → store on Session.geometry_homography_json
        │
        ▼
applied in: scoring_service.compute_projected_zones() (overlay)
            scoring_service.score_warped_shot()        (scoring)
            scoring_service.generate_calibration_debug_image() (Calibration tab)
```

| Module · function | Role |
|---|---|
| `services/zone_geometry.py` → `compute_geometry_homography()` | Detect + match + fit scale/shift transform |
| `app/main.py` → `detect_zones()` (`POST /sessions/{id}/detect-zones`) | Endpoint behind "Align Zones to Real Target" |
| `services/scoring_service.py` → `generate_calibration_debug_image()` | Renders the Calibration/Homography diagnostic image |
| `components/dashboard/TargetSettings.tsx` | "Align Zones" button + status |
| `components/dashboard/LiveTargetView.tsx` | Overlay + **Calibration** tabs |

---

## 6. CAMERA & CAPTURE PIPELINE

| Module · function | Role |
|---|---|
| `services/camera_service.py` → `start_camera()` / `_capture_loop()` | Open device (DShow→MSMF fallback), threaded frame grab, black-frame/DroidCam warnings |
| `services/camera_service.py` → `calibrate_homography()` | AprilTag → paper-contour → **fail-fast** (no blind crop) |
| `services/camera_service.py` → `capture_before_fire()` / `rectify_frame()` | Warp current frame to 1000×1000 |
| `app/main.py` → `/camera/stream` (`gen_camera_frames`) | MJPEG preview |
| `app/main.py` → `/camera/connect`, `/capture/before-fire`, `/capture/after-fire` | Camera + capture endpoints |

---

## 7. TRAINING & MODEL-REGISTRY PIPELINE

```
dataset/ (img + VOC XML)
   └► dataset_pipeline.run_pipeline()  → datasets/ (YOLO format) + dataset.yaml + report
        └► train.py run_training_pipeline()  → YOLOv8s train (GPU/CPU, --workers)
             └► parse metrics → register ModelVersion (active) → hot-swap ai_verifier
```

| Module · function | Role |
|---|---|
| `dataset_pipeline.py` → `run_pipeline()`, `parse_voc_xml()` | VOC→YOLO, splits, `dataset.yaml`, reports. Trains class **`hole` only** |
| `train.py` → `run_training_pipeline()` | GPU auto-detect (`--device auto/gpu/cpu`), `--workers` (RAM-safe), early metrics |
| `train.py` → `register_model_version_db()` | New `ModelVersion` set active; hot-swaps `ai_verifier` |
| `app/main.py` → `/train`, `/training/runs`, `/training/devices`, `/models*` | Training control + telemetry |
| `components/dashboard` (training panel in `page.tsx`) | Epochs/batch/imgsz + CPU/GPU selector |

**Commands**
```bash
python dataset_pipeline.py
python train.py --epochs 50 --device auto --workers 2
python scripts/verify_detection.py <baseline.jpg> <capture.jpg>
```

---

## 8. Data Model (DB)

| Table | Key fields |
|---|---|
| `Session` | `status`, `target_type`, `bullet_caliber`, `geometry_homography_json` |
| `Image` | `image_type` (baseline/capture/difference), `file_path` |
| `Shot` | `x_raw,y_raw` (warped px), `x_calibrated,y_calibrated` (mm), `diameter_*`, `confidence`, `detection_method`, **scoring fields** (`score`, `decimal_score`, `nearest_ring_value`, `boundary_status`, …) |
| `Detection` | shape metrics (`area`, `circularity`, `solidity`, `aspect_ratio`, `raw_contour`) |
| `ModelVersion` | `version_str`, `model_path`, `precision/recall/map50/map50_95`, `is_active` |
| `TrainingRun` | `status`, `epochs`, `metrics_json`, `dataset_size` |

Schema is created via `Base.metadata.create_all`; new columns are added by
`core/database.py::run_additive_migrations()` (idempotent, safe on existing DBs).

---

## 9. Real-time Channels

| Channel | Source | Consumer |
|---|---|---|
| WebSocket `/ws/session/{id}` | `ws_manager.broadcast_to_session()` | `page.tsx` |
| Events | `SHOT_DETECTED`, `BASELINE_UPLOADED`, `CURRENT_IMAGE_UPDATED`, `SHOTS_CLEARED`, `ZONES_ALIGNED` | store + UI |
| MJPEG `/camera/stream` | `camera_service` | live preview |

---

## 10. End-to-End Sequence (one shot)

1. **New Session** → `POST /sessions` (sets target + caliber).
2. **Connect camera** → `POST /camera/connect`; preview via `/camera/stream`.
3. **Before Fire** → warp baseline, clear shots, generate Calibration view.
4. *(optional)* **Align Zones** → `POST /sessions/{id}/detect-zones` fits zones to the print.
5. **Fire.**
6. **After Fire** → `cv_engine.detect_holes` → `ai_verifier` → `apply_scoring_to_shot` → DB → `SHOT_DETECTED`.
7. Dashboard updates overlay, shot table, score cards, statistics — with sound + toast.

---

*Generated as a living reference. If a module moves or a pipeline changes, update the relevant section.*
