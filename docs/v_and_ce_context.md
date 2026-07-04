# V&CE System Context

This document serves as the developer reference context for the Verification & Confidence Engine (V&CE) integrated within the CXR-AIM target analytics platform.

## Architecture

The V&CE intercepts raw OpenCV candidate proposals inside the main capture and detection loops, runs a 4-verifier pipeline, fuses the signal scores, determines the final shot verdict, writes append-only audits, and gates shot scoring.

```
       [Raw CV Candidate]
               │
               ▼
┌──────────────────────────────┐
│       DuplicateVerifier      │ ──► Rejects identical shots in same session/radius/window
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│       GeometryVerifier       │ ──► Checks solidity, circularity, aspect, and area bounds
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│         YOLOVerifier         │ ──► Runs YOLO crop ROI inference (re-normalizes if bypassed)
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│     LocalizationVerifier     │ ──► Computes centroid spread (moment, dark-weighted, ellipse)
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│      Active Disagreement     │ ──► Flag CONFLICT if YOLO vs. CV verifiers cleanly disagree
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│       Confidence Fusion      │ ──► Computes weighted sum score, flags VERIFIED or REVIEW
└──────────────────────────────┘
```

### Key Safety & Reliability Characteristics
- **No Concurrency Thread Exhaustion:** The pipeline runs inline synchronously within the CV flow to avoid Python GIL overhead, GPU resource leaks, and thread-safety race conditions inside the `AIVerifier`.
- **450ms Failsafe Timeout:** Employs step-by-step elapsed-time checks to safely abort processing after 450ms, degrading the verdict to `REVIEW` with a `0.45` score on timeout or general exceptions.
- **YOLO Offline Safe:** Re-normalizes weights and skips `CONFLICT` checks when YOLO is offline/bypassed (defaults to OpenCV fallback).

## Schemas & Database Models

### `LaneConfig`
Represents target detection and V&CE weight/threshold parameters for a physical shooting lane.
- `lane_id`: unique identifier for the lane.
- `threshold_verified`: fusion score cutoff for auto-approval.
- `yolo_conf_strict`, `yolo_conf_loose`: YOLO verifier confidence bands.
- `geom_circ_strict`, `geom_circ_loose`: shape circularity bands.
- `geom_area_loose_min`, `geom_area_loose_max`: area range limits.
- `weight_geometry`, `weight_yolo`, `weight_localization`: fusion weights.

### `VerificationAudit`
An append-only log of every candidate check and subsequent human adjudication.
- `id`, `shot_id`, `lane_id`, `x_raw`, `y_raw`, `verdict`, `confidence`, `explanation`, `signals_json`.
- Adjudication fields: `adjudication_decision`, `adjudicated_by`, `adjudicated_at`.

### `Shot` additions
- `x_raw`, `y_raw`, `diameter_px`, `verdict`, `explanation`.

## Endpoints

1. **Detection / Capture integration:**
   - `/sessions/{session_id}/detect`
   - `/capture/after-fire`
   - `/detect`
   All accept optional `lane` parameter, run V&CE, block scoring for `REVIEW`/`CONFLICT` shots, and execute background tasks for audit logging.
2. **Lane Config CRUD:**
   - `GET /api/v1/lanes/{lane}/config`
   - `POST /api/v1/lanes/{lane}/config`
   - `DELETE /api/v1/lanes/{lane}/config`
3. **Verification Audit Logs:**
   - `GET /api/v1/verification/audit`
4. **Adjudication Updates:**
   - `PATCH /shots/{shot_id}`
