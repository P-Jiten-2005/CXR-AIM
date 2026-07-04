# CXR-AIM — AI Marksmanship Analysis Platform

**Computer-vision shooting-performance analytics: real-time bullet-hole detection, automatic scoring, and role-based training analytics over a private network.**

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-App%20Router-000000?logo=nextdotjs&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Difference%20Engine-5C3EE8?logo=opencv&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8s-Verification%20Layer-orange)
![CUDA](https://img.shields.io/badge/PyTorch-CUDA%20%2F%20CPU-EE4C2C?logo=pytorch&logoColor=white)

CXR-AIM watches a shooting target through a camera, detects each newly created bullet hole the moment it appears, **scores it against a configurable target template**, and streams everything live to a role-based web dashboard. It is a complete analytics platform — sessions, shot history, scoring, zone alignment, a model registry, and a GPU training pipeline — not a single-model demo.

---

## 🧠 Detection Architecture

CXR-AIM deliberately does **not** run YOLO as the primary detector. The target is static; the only thing that changes is a new hole. A fast **OpenCV difference engine** finds *what changed*, and **YOLO verifies** *whether it is a hole*:

```
        Live Camera Feed
               │
   BEFORE FIRE ─► warp/calibrate ─► baseline ─┐
               │                               ▼
 shooter fires ─► AFTER FIRE ─► warp ─► current│
               │                               ▼
      ┌──────────  cv_engine.detect_holes()  ──────────┐
      │ ORB align → background-agnostic difference →     │
      │ edge/AprilTag jitter masking → morphology →      │
      │ contour shape filters → CANDIDATES               │
      └───────────────────────┬──────────────────────────┘
                              ▼
      ┌────── ai_verifier.verify_candidate_roi() ──────┐
      │ custom YOLOv8s (full-image / ROI / SAHI) →       │
      │ confirm or reject each candidate (or bypass)     │
      └───────────────────────┬──────────────────────────┘
                              ▼
   dedup ─► SCORING ─► DB ─► WebSocket ─► dashboard overlay
```

**Key properties**
- **Background-agnostic**: detects holes on white sheets *and* dark silhouettes (catches dark-on-white *and* light-on-black torn-paper edges).
- **AprilTags** are found with a dedicated library (never trained into YOLO); tag regions and warp-seam edges are masked out of detection.
- **YOLO is a verification layer** with a runtime **on/off toggle** (when bypassed, OpenCV candidates are accepted directly).
- Runs on **GPU (CUDA) when available**, else CPU — for both training and inference.

---

## ✨ Features

### Verification & Confidence Engine (V&CE)
- **Geometry Verifier:** Aspect-ratio, solidity, circularity, and area validation.
- **Duplicate Verifier:** Checks coordinates-distance and time-window against all session shots to avoid review queue duplicates.
- **Localization Verifier:** Centroid consensus check utilizing moment, dark-pixel-intensity, ellipse-fit, and peak intensity estimators.
- **Fallback Weight Re-normalization:** Dynamically ignores YOLO and re-normalizes CV verifier weights when YOLO is offline or bypassed.
- **450ms Failsafe Timeout:** Employs step-by-step inline elapsed checks to abort execution within 450ms, returning `REVIEW` with 0.45 confidence.
- **CRUD Lane Management & Audits:** Endpoints to manage per-lane verification parameters and retrieve append-only verification audit logs.

### Detection & scoring
- **Hybrid OpenCV + YOLOv8s pipeline** (difference engine → AI verification), GPU-accelerated.
- **Automatic scoring** against target templates — concentric rings **and** rectangular zones, integer + ISSF decimal scores, with **line-break boundary verification** (certain / probable / review-required).
- **Target Geometry Alignment** — detects the *real printed* scoring zones and fits a rotation+scale+translation transform so the scoring overlay snaps to the actual print (handles targets at any angle).
- **Calibration**: AprilTag perspective warp → paper-contour fallback → centered-crop fallback (so a visible tag-less target still produces a usable baseline; a black/wrong-camera frame is rejected).

### Role-based dashboard
- **ADMIN / TRAINER / SHOOTER** roles with tailored views.
- **TRAINER workspace**: *Live Monitoring* and a *Review Queue* of shots flagged for boundary verification (Approve / Exclude).
- **Image Review Station** tabs: Markings/Overlay, Calibration/Homography, Homographed (rectified), Difference map, and comparisons — with the scoring-zone overlay drawn on the warped target.
- **Confirmed Shots / Candidates / Statistics** tabs with filters (caliber, score, confidence, search), each shot showing position (mm), caliber, score, **detection method** (YOLO / SAHI / OpenCV / bypass), and boundary status.
- **Target Designer**: create custom targets by drawing rectangular zones or concentric rings on an uploaded soft copy.
- **Sound + toast alerts** on capture/detection events; **AI-verifier toggle**, **digital zoom**, and **shot validity review** persisted to the backend.

### Camera & capture
- Webcam index, **IP/RTSP URL**, or phone (DroidCam) sources.
- Requests **full native resolution** from the source (1080p+/4K where supported) instead of the 640×480 default; reports the negotiated resolution and warns on low-res/black feeds.
- MJPEG live preview, before/after capture workflow, digital zoom.

### Training & model registry
- **One-click / CLI YOLOv8s training** with a **CPU/GPU/AUTO device selector**, RAM-safe `--workers`, and automatic Pascal-VOC → YOLO dataset conversion + splits + reports.
- **Model registry**: every run records precision/recall/mAP50/mAP50-95; the active model is tracked in the DB and **hot-swapped** into the live verifier on completion.

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, async SQLAlchemy 2.0 |
| Computer vision | OpenCV (differencing, ORB registration, homography, zone detection), pupil-apriltags |
| AI verification | Ultralytics YOLOv8s, optional SAHI, PyTorch (CUDA/CPU) |
| Database | SQLite (development) / PostgreSQL-ready (Docker Compose) |
| Frontend | Next.js (App Router), React, Zustand, Tailwind CSS, HTML5 Canvas |
| Realtime | Native WebSockets, MJPEG camera streaming, Web-Audio alerts |
| Ops | Docker & Docker Compose, unified Python launcher |

---

## 📁 Repository Structure

```
CXR-AIM/
├── backend/
│   ├── app/
│   │   ├── core/                    # Settings + async DB session + additive migrations
│   │   ├── models/                  # ORM: Session, Image, Shot, Detection, ModelVersion, TrainingRun
│   │   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── cv_engine.py         # OpenCV difference engine (candidate detection)
│   │   │   ├── ai_verifier.py       # YOLOv8s / SAHI verification (+ on/off toggle)
│   │   │   ├── apriltag_service.py  # AprilTag detection & perspective warp
│   │   │   ├── camera_service.py    # Camera lifecycle, calibration, capture, zoom
│   │   │   ├── scoring_service.py   # Warped-px → mm scoring, projected zones, calibration debug
│   │   │   ├── zone_geometry.py     # Target Geometry Alignment (zone homography fit)
│   │   │   └── ws_manager.py        # WebSocket broadcaster
│   │   ├── scoring/                 # target_definition, scoring_engine, boundary_verification,
│   │   │                            #   coordinate_transformer (pure scoring logic)
│   │   └── main.py                  # FastAPI app & all routes
│   ├── configs/targets/             # Target templates (figure_11, issf_10m_air_rifle, …)
│   └── run.py                       # Uvicorn dev runner (auto-reload)
├── frontend/                        # Next.js role-based dashboard
│   └── src/
│       ├── app/                     # page.tsx (dashboard), layout, globals
│       ├── components/dashboard/    # LiveTargetView, ShotTable, OverviewCards, StatsPanel,
│       │                            #   ConnectionStatus, TargetPreview, ToastHost
│       ├── lib/sound.ts             # Web-Audio alert tones
│       └── store/useStore.ts        # Zustand global state
├── dataset_pipeline.py              # Pascal VOC → YOLO conversion, splits, dataset report
├── train.py                         # YOLOv8s training + model-registry registration + hot-swap
├── inference.py                     # Standalone CLI inference on an image pair
├── scripts/
│   ├── verify_detection.py          # Offline detection regression check
│   └── probe_cams.py                # Enumerate working camera indices/backends
├── docs/
│   ├── ARCHITECTURE.md              # Full architecture & per-pipeline module map
│   └── frontend-blueprint.md        # Frontend specification reference
├── docker-compose.yml               # Full stack + PostgreSQL
├── requirements.txt                 # Backend deps (incl. CUDA PyTorch index)
└── start_platform.py                # One-command launcher
```

> **Not in git (by design):** `dataset/`, `datasets/`, `runs/`, `backend/uploads/`, `*.pt` weights, `*.db`. See [Training](#-training--model-registry).

---

## 🚀 Quick Start

**Prerequisites:** Python 3.12+, Node.js 18+. NVIDIA GPU optional (CUDA auto-detected).

```bash
git clone https://github.com/ToTheBlankWorld/CXR-AIM.git
cd CXR-AIM
python start_platform.py
```

The launcher provisions `backend/venv`, installs Python + npm deps, then starts:
- **Dashboard** → http://localhost:3000
- **API + Swagger docs** → http://localhost:8000/docs

`Ctrl+C` in the launcher terminal cleanly stops both servers.

> **GPU note:** `requirements.txt` pins the CUDA PyTorch wheel (`--extra-index-url .../cu124`). On a machine without an NVIDIA GPU it falls back to CPU automatically.

---

## 📷 Session Workflow

1. **New Session** — set name, target template, and bullet caliber.
2. **Connect camera** — index (`0`, `1`), IP/RTSP URL, or DroidCam. Use `scripts/probe_cams.py` to find indices; the connect response reports the negotiated resolution.
3. **Calibrate / Before Fire** — captures and registers the perspective-rectified baseline. With AprilTags it uses the true homography; without, it falls back to paper-contour or a centered crop (a black/wrong-camera frame is rejected).
4. *(optional)* **Align Zones to Real Target** — fits the scoring zones to the actual print.
5. **Fire**, then **Trigger Fired / After Fire** — detects, verifies, scores, and registers new shots; the overlay, shot table, scores, and alerts update live.
6. Flagged (line-break) shots appear in the **Trainer → Review Queue** for Approve/Exclude.

---

## 🎓 Training & Model Registry

The verification model is trained on your own targets; the dataset is swappable without code changes.

1. **Provide data** in `dataset/` as image + Pascal VOC XML pairs annotating the `hole` class.
2. **Build + train** (auto-runs the dataset pipeline first):
   ```bash
   python train.py --epochs 50 --device auto --workers 2
   ```
   - `--device` — `auto` (GPU if available), `gpu`/`cpu`.
   - `--workers` — dataloader workers; **lower to 2 if you hit out-of-memory** on high-res images.
   - On completion: metrics parsed → new `ModelVersion` set active → live verifier hot-swapped.
3. **Verify offline** before going live:
   ```bash
   python scripts/verify_detection.py path/to/baseline.jpg path/to/capture.jpg
   ```

You can also launch training from the dashboard's training panel (CPU/GPU/AUTO selector).

---

## 📡 API Reference (summary)

### Camera & capture
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/camera/connect` · `/camera/start` | Connect a source (reports resolution + warnings) |
| `POST` | `/api/v1/camera/disconnect` · `/camera/stop` | Release the camera |
| `GET`  | `/api/v1/camera/stream` | Live MJPEG preview |
| `POST` | `/api/v1/camera/zoom?factor=` | Digital zoom |
| `POST` | `/api/v1/camera/calibrate` | Calibrate target homography |
| `POST` | `/api/v1/capture/before-fire` · `/camera/before_fire` | Register the baseline |
| `POST` | `/api/v1/capture/after-fire` · `/camera/fire` | Capture, detect, verify, score |
| `GET`  | `/api/v1/camera/ping` | Camera online state + resolution |

### Sessions, shots & scoring
| Method | Endpoint | Description |
|---|---|---|
| `POST` / `GET` | `/api/v1/sessions` · `/sessions/active` | Create / fetch active session |
| `PUT`  | `/api/v1/sessions/{id}/target` | Set target template + caliber |
| `GET`  | `/api/v1/sessions/{id}/projected-zones` | Scoring zones in warped-pixel space |
| `POST` | `/api/v1/sessions/{id}/detect-zones` | Fit zone-geometry alignment to the print |
| `GET`  | `/api/v1/shots` · `/shots/review` | Active-session shots / review queue |
| `PATCH`| `/api/v1/shots/{id}` | Update validity / boundary decision |
| `GET`  | `/api/v1/statistics` | Aggregated session statistics |

### Targets, config, training & models
| Method | Endpoint | Description |
|---|---|---|
| `GET` / `POST` | `/api/v1/targets` · `/targets/{id}` | List / create / fetch target templates |
| `GET` / `POST` | `/api/v1/config/ai-verifier` | Get / toggle YOLO verification |
| `POST` | `/api/v1/train` | Launch a background training run |
| `GET`  | `/api/v1/training/runs` · `/training/devices` · `/training/dataset-stats` | Training telemetry |
| `GET`  | `/api/v1/models` · `/models/active` | Model registry |
| `GET`  | `/api/v1/health` | System / camera / GPU status |

### V&CE Configuration & Audit Logs
| Method | Endpoint | Description |
|---|---|---|
| `GET`  | `/api/v1/lanes/{lane}/config` | Retrieve configuration for a specific lane (falls back to global defaults) |
| `POST` | `/api/v1/lanes/{lane}/config` | Create/update configuration parameters for a specific lane |
| `DELETE` | `/api/v1/lanes/{lane}/config` | Reset/delete configuration for a specific lane |
| `GET`  | `/api/v1/verification/audit` | Query, filter, and paginate the append-only verification audit logs |

### Realtime
| Protocol | Endpoint | Events |
|---|---|---|
| WebSocket | `/ws/session/{id}` | `SHOT_DETECTED`, `SHOT_UPDATED`, `BASELINE_UPLOADED`, `CURRENT_IMAGE_UPDATED`, `FRAME_UPDATED`, `SHOTS_CLEARED`, `ZONES_ALIGNED` |

Full interactive docs: **http://localhost:8000/docs**.

---

## ⚙️ Configuration

Settings live in `backend/app/core/config.py` (env-overridable):

| Setting | Default | Description |
|---|---|---|
| `DATABASE_URL` | SQLite in `data/` | Swap to `postgresql+asyncpg://…` for production |
| `UPLOAD_DIR` | `uploads` | Capture / baseline / debug image storage |
| `SAHI_ENABLED` | `false` | Sliced inference for tiny candidate ROIs |
| `CORS_ORIGINS` | `*` | Restrict to the dashboard origin in production |

DB columns added after the initial schema are applied automatically and idempotently by `core/database.py::run_additive_migrations()` (safe on existing databases).

---

## 🐳 Docker (PostgreSQL stack)

```bash
docker-compose up --build
```

Runs backend, frontend, and a PostgreSQL service (port `5432`).

---

## 🗺️ Roadmap

- [ ] **Tag-less target detection** (YOLO bounding-box or segmentation) — locate & crop the target without AprilTags
- [ ] Train the verifier on **warped 1000×1000** frames to close the raw-photo → warped-image domain gap
- [ ] Shooter posture analysis (Camera B — depth camera module)
- [ ] Multi-camera / multi-target lanes
- [ ] Session comparison, heatmaps, performance prediction, mobile dashboard

---

*See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full architecture and a per-pipeline module map (exactly which scripts power detection, scoring, alignment, camera, and training).*
