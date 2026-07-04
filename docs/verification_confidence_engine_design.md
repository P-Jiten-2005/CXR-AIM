# Verification & Confidence Engine (V&CE) Design Specification

This document details the architecture, database schema modifications, mathematical fusion formulas, and integration path for the **Verification & Confidence Engine (V&CE)** within the CXR-AIM Shooting Target Acquisition & Analytics Platform.

---

## 1. Purpose & Goals

The V&CE introduces a multi-verifier verification layer between raw contour/change detection and shot scoring. Fusing classical computer vision signals with AI YOLOv8 crop verification guarantees bullet-hole authenticity, prevents double-scoring, and isolates calibration/noise failures.

### Key Goals:
- **Zero False-Positives**: High precision in automatic scoring via strict `VERIFIED` thresholds.
- **High Recall**: All borderline cases, grazing shots, or weak consensus detections are routed to `REVIEW` instead of being silently discarded.
- **Auditability**: Complete append-only audit trail of every candidate detection, including hard-gated rejections.
- **Fail-safe Performance**: Real-time processing ($\le 500$ ms) and graceful degradation to manual review in case of component timeouts or system exceptions.

---

## 2. Component Architecture

The V&CE runs on the centralized backend, evaluating candidate proposals emitted by the OpenCV difference engine before they are registered as shots.

```
                  Raw OpenCV Candidates (cX, cY, w, h, contour)
                                      │
                                      ▼
                        ConfidenceEngine Pipeline
  ┌───────────────────────────────────────────────────────────────────────┐
  │                                                                       │
  │   ┌───────────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
  │   │  GeometryVerifier │  │  YOLOVerifier  │  │ LocalizationVerifier │  │
  │   └─────────┬─────────┘  └───────┬────────┘  └──────────┬──────────┘  │
  │             │                    │                      │             │
  │             └────────────────────┼──────────────────────┘             │
  │                                  ▼                                    │
  │                         [DuplicateVerifier]                           │
  │                                  │                                    │
  │                                  ▼                                    │
  │                    Hard Gate & Disagreement Check                     │
  │                                  │                                    │
  │                                  ▼                                    │
  │                        Weighted Score Fusion                          │
  │                                                                       │
  └──────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
                      Verdict + Explanation + Score
                   ┌─────────────────┼─────────────────┐
                   │                 │                 │
                   ▼                 ▼                 ▼
               VERIFIED           REVIEW/CONFLICT   REJECTED
               (Score &           (Shot Created;    (No Shot;
               Broadcast)        is_valid=False;     Audit Only)
                                 Adjudication)
```

---

## 3. Database Schema Changes

We will introduce two new database models (`LaneConfig` and `VerificationAudit`) and extend the `Shot` table to store V&CE properties directly. These changes will be applied idempotently on startup via `core/database.py`.

### 3.1 `LaneConfig` Model
Holds per-lane configuration parameters for verification sensitivity. A `lane` column value of `NULL` acts as the global system default.

```python
class LaneConfig(Base):
    __tablename__ = "lane_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    lane = Column(Integer, nullable=True, unique=True) # NULL represents system-wide default
    
    # Geometry parameters (recalibration placeholders)
    geom_area_strict_min = Column(Float, default=40.0)
    geom_area_strict_max = Column(Float, default=1500.0)
    geom_area_loose_min = Column(Float, default=15.0)
    geom_area_loose_max = Column(Float, default=5000.0)
    
    geom_circ_strict = Column(Float, default=0.65)
    geom_circ_loose = Column(Float, default=0.45)
    
    geom_aspect_strict_min = Column(Float, default=0.7)
    geom_aspect_strict_max = Column(Float, default=1.4)
    geom_aspect_loose_min = Column(Float, default=0.3)
    geom_aspect_loose_max = Column(Float, default=3.0)
    
    # Duplicate parameters
    duplicate_radius_px = Column(Float, default=15.0)
    duplicate_time_window_sec = Column(Float, default=5.0)
    
    # Localization parameters
    localization_spread_threshold = Column(Float, default=5.0)
    
    # YOLO parameters
    yolo_conf_strict = Column(Float, default=0.25)
    yolo_conf_loose = Column(Float, default=0.10)
    
    # Fusion Weights
    weight_geometry = Column(Float, default=0.40)
    weight_yolo = Column(Float, default=0.40)
    weight_localization = Column(Float, default=0.20)
    
    # Decision Threshold
    threshold_verified = Column(Float, default=0.75)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

### 3.2 `VerificationAudit` Model
Append-only log of every single V&CE evaluation. Adjudications append operator decisions to the existing audit row while preserving the original verdict and explanation.

```python
class VerificationAudit(Base):
    __tablename__ = "verification_audits"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    lane_id = Column(Integer, nullable=False)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    shot_id = Column(String(36), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True) # NULL for REJECTED candidates
    x_raw = Column(Float, nullable=False)
    y_raw = Column(Float, nullable=False)
    
    # Verbose logging
    signals_json = Column(JSON, nullable=False) # Stores individual verifier values/metrics
    verdict = Column(String(50), nullable=False) # VERIFIED, REVIEW, REJECTED, CONFLICT
    confidence_score = Column(Float, nullable=False)
    explanation = Column(String(1024), nullable=False)
    
    # Append-only Adjudication updates (never overwrites original verdict)
    adjudication_decision = Column(String(50), nullable=True) # ACCEPTED, REJECTED
    adjudicated_by = Column(String(100), nullable=True) # Operator ID
    adjudicated_at = Column(DateTime, nullable=True)
```

### 3.3 `Shot` Table Additions
The following columns will be added to the existing `shots` table:
- `verdict = Column(String(50), nullable=True)` (e.g. `VERIFIED`, `REVIEW`, `CONFLICT`)
- `verdict_explanation = Column(String(1024), nullable=True)`
- `confidence_score = Column(Float, nullable=True)`

---

## 4. Verification Logic & Fusion Mathematics

For each candidate detection proposal, V&CE executes a 5-step pipeline:

### Step 1: Compute Verifier Scores
1. **GeometryVerifier Score ($s_{\text{geom}}$)**:
   - Compares candidate's Circularity, Solidity, and Aspect Ratio against `LaneConfig` parameters.
   - For each metric, assign an individual score:
     - Inside strict limits: `1.0` (`strong_pass`)
     - Outside strict but inside loose limits: `0.5` (`weak_pass`)
     - Outside loose limits: `0.0` (`fail`)
   - $s_{\text{geom}}$ is the arithmetic mean of these three metric scores.
   - If any metric is `fail` ($0.0$) or the candidate area lies outside $[geom\_area\_loose\_min, geom\_area\_loose\_max]$, it flags a shape failure.

2. **YOLOVerifier Score ($s_{\text{yolo}}$)**:
   - Evaluates the YOLO ROI confidence output $C_{\text{yolo}}$ (default $0.0$ if no detection overlap is found on the crop):
     - $C_{\text{yolo}} \ge yolo\_conf\_strict$: $s_{\text{yolo}} = 1.0$ (`strong_pass`)
     - $yolo\_conf\_loose \le C_{\text{yolo}} < yolo\_conf\_strict$: $s_{\text{yolo}} = 0.5$ (`weak_pass`)
     - $C_{\text{yolo}} < yolo\_conf\_loose$: $s_{\text{yolo}} = 0.0$ (`fail`)

3. **LocalizationVerifier Score ($s_{\text{loc}}$)**:
   - Evaluates 4 independent centroid estimators (moment centroid, intensity-weighted patch center, fitted ellipse center, and local intensity peak).
   - Computes the maximum Euclidean distance between any pair (spread $D_{\text{spread}}$ in pixels):
     - $D_{\text{spread}} \le localization\_spread\_threshold$: $s_{\text{loc}} = 1.0$ (`strong_pass`)
     - $D_{\text{spread}} > localization\_spread\_threshold$: $s_{\text{loc}} = 0.2$ (`fail`)

---

### Step 2: Hard Gate Evaluation (REJECTED Override)
Before running weighted calculations, check absolute rejection conditions:
1. **Duplicate Check**: If `DuplicateVerifier` confirms a match against any `VERIFIED` shot in the current session (spatial distance $\le duplicate\_radius\_px$ and time difference $\le duplicate\_time\_window\_sec$):
   - **Verdict**: `REJECTED`
   - **Confidence**: `0.0`
   - **Explanation**: `"DuplicateVerifier: Candidate matches existing Shot #{number} within {dist:.1f}px."`
2. **Extreme Geometry Fail**: If $s_{\text{geom}} \le 0.15$ or candidate area is completely outside loose area bounds:
   - **Verdict**: `REJECTED`
   - **Confidence**: `0.0`
   - **Explanation**: `"GeometryVerifier: Extreme geometry failure (area={area:.1f}, circularity={circularity:.2f}, aspect_ratio={aspect_ratio:.2f})."`

*Candidates ending here do not create a Shot row.*

---

### Step 3: Active Disagreement (CONFLICT) Evaluation
Evaluate conflicting high-confidence signals before the weighted sum:
- **Case A (AI Pass, CV Fail)**: YOLO returns a strong pass ($C_{\text{yolo}} \ge yolo\_conf\_strict$), but both Geometry and Localization fail ($s_{\text{geom}} \le 0.5$ and $s_{\text{loc}} = 0.2$):
  - **Verdict**: `CONFLICT`
  - **Confidence**: `0.50`
  - **Explanation**: `"Active Disagreement: YOLO strongly verified hole (conf={conf:.2f}), but CV geometry and localization consensus failed (spread={spread:.1f}px)."`
- **Case B (CV Pass, AI Fail)**: Geometry and Localization return a strong pass ($s_{\text{geom}} = 1.0$ and $s_{\text{loc}} = 1.0$), but YOLO returns a fail ($C_{\text{yolo}} < yolo\_conf\_loose$):
  - **Verdict**: `CONFLICT`
  - **Confidence**: `0.50`
  - **Explanation**: `"Active Disagreement: CV shape and localization are perfect, but YOLO failed to detect a hole (conf={conf:.2f})."`

---

### Step 4: Weighted Fusion & Decision (Two-Band Thresholding)
Fuses the scores using normalized weights (summing to $1.0$):

$$S_{\text{raw}} = (w_{\text{geom}} \times s_{\text{geom}}) + (w_{\text{yolo}} \times s_{\text{yolo}}) + (w_{\text{loc}} \times s_{\text{loc}})$$

#### Soft Penalties:
- If `LocalizationVerifier` is `fail` ($s_{\text{loc}} = 0.2$): $S_{\text{fused}} = S_{\text{raw}} - 0.15$
- If `YOLOVerifier` is `fail` ($s_{\text{yolo}} = 0.0$): $S_{\text{fused}} = S_{\text{raw}} - 0.10$
- Clamp: $C_{\text{final}} = \min(\max(S_{\text{fused}}, 0.0), 1.0)$

#### Two-Band Split:
1. **$C_{\text{final}} \ge threshold\_verified$** (default `0.75`):
   - **Verdict**: `VERIFIED`
   - **Confidence**: $C_{\text{final}}$
2. **$C_{\text{final}} < threshold\_verified$**:
   - **Verdict**: `REVIEW`
   - **Confidence**: $C_{\text{final}}$
   - **Explanation**: `"Failed threshold_verified {threshold_verified:.2f}. Low scoring modules: [Details]."`

> [!NOTE]
> Since we have no physical camera calibration data yet, all parameters are treated as placeholders. `threshold_verified` serves as the primary tuning knob. Manual review rates are expected to exceed 5% initially until live PoE camera frames are recorded and analyzed.

---

### Step 5: Failsafe Execution
The Confidence Engine executes the four-verifier pipeline inside a `try/except` block. If any module raises an exception or times out:
- Catch the error and log the traceback.
- **Verdict**: `REVIEW`
- **Confidence**: `0.45`
- **Explanation**: `"Failsafe triggered: Verifier system encountered a processing exception ([Error Class Name]). degraded to manual review."`

---

## 5. Integration Points

### 5.1 Endpoint & CV Alignment
- Modify `cv_engine.detect_holes` to return **all** raw proposals.
- Modify `/detect`, `/capture/after-fire`, and `/detect` endpoints in `app/main.py` to:
  - Accept an optional `lane` integer query parameter.
  - Query database for specific `lane` config (fallback to `lane=NULL` defaults).
  - Run V&CE on each candidate.
  - For `VERIFIED`: Score the shot and write to DB (`is_valid = True`).
  - For `REVIEW` / `CONFLICT`: Write to DB (`is_valid = False`, `boundary_status = "review_required"`). Defer scoring.
  - For `REJECTED`: Skip DB Shot insertion, only write `VerificationAudit` row.
  - Write `VerificationAudit` in a background/fire-and-forget task to protect the 500ms response window.

### 5.2 Adjudication & Update
- Update `PATCH /shots/{shot_id}`:
  - When approved (`boundary_status` updated to `certain`/`probable` and `is_valid` becomes `True`), check if original verdict was `REVIEW` or `CONFLICT`. If so, score the shot, mark it valid, and update the associated `VerificationAudit` row: `adjudication_decision = "ACCEPTED"`, `adjudicated_by = operator_id`, `adjudicated_at = utcnow()`.
  - When excluded (`is_valid` set to `False`), update the associated `VerificationAudit` row: `adjudication_decision = "REJECTED"`, `adjudicated_by = operator_id`, `adjudicated_at = utcnow()`.
