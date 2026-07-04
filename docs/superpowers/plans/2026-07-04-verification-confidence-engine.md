# Verification & Confidence Engine (V&CE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a robust Verification & Confidence Engine (V&CE) between raw candidate detection and scoring, supporting per-lane config overrides and append-only audits.

**Architecture:** Candidate proposals from `cv_engine.detect_holes` are evaluated by Geometry, YOLO, Duplicate, and Localization verifiers. The Confidence Engine fuses these signals using configurable weights and soft penalties, assigning a `VERIFIED`, `REVIEW`, `CONFLICT`, or `REJECTED` verdict. Only `VERIFIED` automatically scores and saves; `REVIEW`/`CONFLICT` flag for operator review; `REJECTED` are suppressed and logged only.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (Async), SQLite/aiosqlite, OpenCV

## Global Constraints
- Target latency for the entire verdict pipeline is under 500ms.
- Audit trail is append-only; adjudications update existing records' `adjudication_decision`, `adjudicated_by`, and `adjudicated_at` without overwriting the original `verdict` or `explanation`.
- `CONFLICT` is stored literally as `"CONFLICT"` in `Shot.verdict` and `VerificationAudit.verdict`.
- If any verifier throws or times out, the failsafe must degrade the verdict to `REVIEW` with a status score of `0.45` and log the exception.

---

### Task 1: Database Models & Additive Migrations

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/core/database.py`
- Create: `backend/tests/test_db_migrations.py`

**Interfaces:**
- Consumes: None
- Produces: `LaneConfig` and `VerificationAudit` models in ORM, new columns on `Shot` (`verdict`, `verdict_explanation`, `confidence_score`).

- [ ] **Step 1: Write the failing test**
  Create `backend/tests/test_db_migrations.py` with:
  ```python
  import unittest
  from sqlalchemy import select, inspect
  from app.core.database import AsyncSessionLocal, engine
  from app.models import models
  import asyncio

  class TestDatabaseMigrations(unittest.IsolatedAsyncioTestCase):
      async def test_columns_exist(self):
          async with engine.connect() as conn:
              # We inspect the columns in the shots table
              def inspect_cols(connection):
                  inspector = inspect(connection)
                  return [col["name"] for col in inspector.get_columns("shots")]
              columns = await conn.run_sync(inspect_cols)
              self.assertIn("verdict", columns)
              self.assertIn("verdict_explanation", columns)
              self.assertIn("confidence_score", columns)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_db_migrations.py`
  Expected: FAIL with missing columns or table not found.

- [ ] **Step 3: Modify models.py and database.py**
  Add `LaneConfig` and `VerificationAudit` models to `backend/app/models/models.py`:
  ```python
  class LaneConfig(Base):
      __tablename__ = "lane_configs"
      id = Column(String(36), primary_key=True, default=generate_uuid)
      lane = Column(Integer, nullable=True, unique=True)
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
      duplicate_radius_px = Column(Float, default=15.0)
      duplicate_time_window_sec = Column(Float, default=5.0)
      localization_spread_threshold = Column(Float, default=5.0)
      yolo_conf_strict = Column(Float, default=0.25)
      yolo_conf_loose = Column(Float, default=0.10)
      weight_geometry = Column(Float, default=0.40)
      weight_yolo = Column(Float, default=0.40)
      weight_localization = Column(Float, default=0.20)
      threshold_verified = Column(Float, default=0.75)
      created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
      updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

  class VerificationAudit(Base):
      __tablename__ = "verification_audits"
      id = Column(String(36), primary_key=True, default=generate_uuid)
      timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
      lane_id = Column(Integer, nullable=False)
      session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
      shot_id = Column(String(36), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True)
      x_raw = Column(Float, nullable=False)
      y_raw = Column(Float, nullable=False)
      signals_json = Column(JSON, nullable=False)
      verdict = Column(String(50), nullable=False)
      confidence_score = Column(Float, nullable=False)
      explanation = Column(String(1024), nullable=False)
      adjudication_decision = Column(String(50), nullable=True)
      adjudicated_by = Column(String(100), nullable=True)
      adjudicated_at = Column(DateTime, nullable=True)
  ```
  Add the columns to `Shot` class in `backend/app/models/models.py`:
  ```python
  verdict = Column(String(50), nullable=True)
  verdict_explanation = Column(String(1024), nullable=True)
  confidence_score = Column(Float, nullable=True)
  ```
  Update `_ADDITIVE_COLUMNS` in `backend/app/core/database.py`:
  ```python
  _ADDITIVE_COLUMNS = {
      "sessions": [...],
      "shots": [
          ("score", "INTEGER"),
          ("decimal_score", "FLOAT"),
          ("nearest_ring_value", "INTEGER"),
          ("distance_to_nearest_ring_mm", "FLOAT"),
          ("bullseye_id", "INTEGER"),
          ("distance_to_center_mm", "FLOAT"),
          ("boundary_status", "VARCHAR(50)"),
          ("localization_error_mm", "FLOAT DEFAULT 0.0"),
          ("verdict", "VARCHAR(50)"),
          ("verdict_explanation", "VARCHAR(1024)"),
          ("confidence_score", "FLOAT"),
      ],
  }
  ```
  Ensure `run_additive_migrations()` also calls `Base.metadata.create_all` via run_sync to create `lane_configs` and `verification_audits` tables if they do not exist:
  ```python
  async def run_additive_migrations():
      # existing table_info check...
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)
      # existing ALTER TABLE logic...
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_db_migrations.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/models/models.py backend/app/core/database.py backend/tests/test_db_migrations.py
  git commit -m "feat: add LaneConfig, VerificationAudit, and Shot columns"
  ```

---

### Task 2: Pydantic Schemas

**Files:**
- Modify: `backend/app/schemas/schemas.py`
- Create: `backend/tests/test_schemas.py`

**Interfaces:**
- Consumes: None
- Produces: `ShotResponse` updates, `LaneConfigResponse`, `LaneConfigCreate`, `VerificationAuditResponse`.

- [ ] **Step 1: Write the failing test**
  Create `backend/tests/test_schemas.py` with:
  ```python
  import unittest
  from app.schemas import schemas
  from datetime import datetime

  class TestSchemas(unittest.TestCase):
      def test_shot_response_vce_fields(self):
          # Test if new V&CE fields are present in ShotResponse
          shot = schemas.ShotResponse(
              id="uuid", session_id="sess", shot_number=1, x_raw=10.0, y_raw=20.0,
              diameter_px=8.0, confidence=0.8, is_valid=True, created_at=datetime.utcnow(),
              verdict="VERIFIED", verdict_explanation="All clear", confidence_score=0.9
          )
          self.assertEqual(shot.verdict, "VERIFIED")
          self.assertEqual(shot.confidence_score, 0.9)
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_schemas.py`
  Expected: FAIL with ValidationError (unexpected fields).

- [ ] **Step 3: Modify schemas.py**
  Add columns to `ShotResponse` in `backend/app/schemas/schemas.py`:
  ```python
  verdict: Optional[str] = None
  verdict_explanation: Optional[str] = None
  confidence_score: Optional[float] = None
  ```
  Add schemas for `LaneConfig` and `VerificationAudit` in `backend/app/schemas/schemas.py`:
  ```python
  class LaneConfigBase(BaseModel):
      lane: Optional[int] = None
      geom_area_strict_min: float = 40.0
      geom_area_strict_max: float = 1500.0
      geom_area_loose_min: float = 15.0
      geom_area_loose_max: float = 5000.0
      geom_circ_strict: float = 0.65
      geom_circ_loose: float = 0.45
      geom_aspect_strict_min: float = 0.7
      geom_aspect_strict_max: float = 1.4
      geom_aspect_loose_min: float = 0.3
      geom_aspect_loose_max: float = 3.0
      duplicate_radius_px: float = 15.0
      duplicate_time_window_sec: float = 5.0
      localization_spread_threshold: float = 5.0
      yolo_conf_strict: float = 0.25
      yolo_conf_loose: float = 0.10
      weight_geometry: float = 0.40
      weight_yolo: float = 0.40
      weight_localization: float = 0.20
      threshold_verified: float = 0.75

  class LaneConfigCreate(LaneConfigBase):
      pass

  class LaneConfigResponse(LaneConfigBase):
      id: str
      created_at: datetime
      updated_at: datetime
      class Config:
          from_attributes = True

  class VerificationAuditResponse(BaseModel):
      id: str
      timestamp: datetime
      lane_id: int
      session_id: str
      shot_id: Optional[str] = None
      x_raw: float
      y_raw: float
      signals_json: Any
      verdict: str
      confidence_score: float
      explanation: str
      adjudication_decision: Optional[str] = None
      adjudicated_by: Optional[str] = None
      adjudicated_at: Optional[datetime] = None
      class Config:
          from_attributes = True
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_schemas.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/schemas/schemas.py backend/tests/test_schemas.py
  git commit -m "feat: add schema definitions for V&CE metrics and configurations"
  ```

---

### Task 3: Implement V&CE Verifier & Fusion Engine

**Files:**
- Create: `backend/app/services/confidence_engine.py`
- Create: `backend/tests/test_confidence_engine.py`

**Interfaces:**
- Consumes: `ai_verifier.verify_candidate_roi` from `app.services.ai_verifier`
- Produces: `confidence_engine.evaluate_candidate(candidate, session_shots, lane_config, img)` returning `(verdict, score, explanation, signals_dict)`.

- [ ] **Step 1: Write the failing test**
  Create `backend/tests/test_confidence_engine.py` testing verifier scores, hard gates, active disagreement, and failsafe behavior:
  ```python
  import unittest
  import numpy as np
  from app.services.confidence_engine import ConfidenceEngine, GeometryVerifier, DuplicateVerifier, LocalizationVerifier
  from app.schemas.schemas import LaneConfigBase

  class TestConfidenceEngine(unittest.TestCase):
      def test_geometry_verifier(self):
          config = LaneConfigBase()
          # Test strong pass
          result = GeometryVerifier.evaluate(200.0, 0.8, 0.95, 1.0, config)
          self.assertEqual(result, ("strong_pass", 1.0))
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_confidence_engine.py`
  Expected: FAIL (module not found).

- [ ] **Step 3: Implement verifiers and fusion logic in confidence_engine.py**
  Write the logic for `GeometryVerifier`, `DuplicateVerifier`, `LocalizationVerifier`, and `ConfidenceEngine` exactly as defined in the design spec:
  ```python
  import numpy as np
  import cv2
  import logging
  from typing import Tuple, Dict, Any, List

  logger = logging.getLogger("app.confidence_engine")

  class GeometryVerifier:
      @staticmethod
      def evaluate(area: float, circularity: float, solidity: float, aspect_ratio: float, config: Any) -> Tuple[str, float]:
          scores = []
          # Circularity
          if config.geom_circ_strict <= circularity <= 1.0:
              scores.append(1.0)
          elif config.geom_circ_loose <= circularity < config.geom_circ_strict:
              scores.append(0.5)
          else:
              scores.append(0.0)

          # Solidity
          if 0.80 <= solidity <= 1.0: # strict
              scores.append(1.0)
          elif 0.65 <= solidity < 0.80: # loose
              scores.append(0.5)
          else:
              scores.append(0.0)

          # Aspect Ratio
          if config.geom_aspect_strict_min <= aspect_ratio <= config.geom_aspect_strict_max:
              scores.append(1.0)
          elif config.geom_aspect_loose_min <= aspect_ratio <= config.geom_aspect_loose_max:
              scores.append(0.5)
          else:
              scores.append(0.0)

          geom_score = float(np.mean(scores))
          is_fail = any(s == 0.0 for s in scores) or not (config.geom_area_loose_min <= area <= config.geom_area_loose_max)
          
          if is_fail:
              return "fail", geom_score
          elif all(s == 1.0 for s in scores):
              return "strong_pass", geom_score
          else:
              return "weak_pass", geom_score

  class DuplicateVerifier:
      @staticmethod
      def evaluate(cX: float, cY: float, timestamp: float, verified_shots: List[Dict[str, Any]], config: Any) -> Tuple[str, Dict[str, Any]]:
          for s in verified_shots:
              dist = np.sqrt((cX - s["x_raw"])**2 + (cY - s["y_raw"])**2)
              t_diff = abs(timestamp - s.get("created_at_ts", timestamp))
              if dist <= config.duplicate_radius_px and t_diff <= config.duplicate_time_window_sec:
                  return "duplicate", {"matched_shot_number": s["shot_number"], "dist": dist, "shot_id": s.get("id")}
          return "neutral", {}

  class LocalizationVerifier:
      @staticmethod
      def evaluate(c: np.ndarray, gray_img: np.ndarray, config: Any) -> Tuple[str, float, Dict[str, Any]]:
          # 1. Moment based centroid
          M = cv2.moments(c)
          if M["m00"] == 0:
              return "fail", 0.0, {"error": "zero moments"}
          cX_m = M["m10"] / M["m00"]
          cY_m = M["m01"] / M["m00"]

          # 2. Intensity-weighted centroid
          x, y, w, h = cv2.boundingRect(c)
          roi = gray_img[y:y+h, x:x+w]
          y_indices, x_indices = np.indices(roi.shape)
          weights = 255.0 - roi.astype(np.float32) # Darker pixels are bullet hole interiors -> higher weight
          total_w = weights.sum()
          if total_w > 0:
              cX_w = x + (x_indices * weights).sum() / total_w
              cY_w = y + (y_indices * weights).sum() / total_w
          else:
              cX_w, cY_w = cX_m, cY_m

          # 3. Ellipse fit
          if len(c) >= 5:
              try:
                  ellipse = cv2.fitEllipse(c)
                  cX_e, cY_e = ellipse[0]
              except Exception:
                  cX_e, cY_e = cX_m, cY_m
          else:
              cX_e, cY_e = cX_m, cY_m

          # 4. Intensity peak center
          min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(roi)
          cX_p = x + min_loc[0]
          cY_p = y + min_loc[1]

          estimators = np.array([[cX_m, cY_m], [cX_w, cY_w], [cX_e, cY_e], [cX_p, cY_p]])
          dists = []
          for i in range(4):
              for j in range(i+1, 4):
                  dists.append(np.linalg.norm(estimators[i] - estimators[j]))
          max_spread = float(np.max(dists))

          status = "strong_pass" if max_spread <= config.localization_spread_threshold else "fail"
          score = 1.0 if status == "strong_pass" else 0.2
          return status, score, {"spread": max_spread, "estimators": estimators.tolist()}

  class ConfidenceEngine:
      @staticmethod
      def evaluate_candidate(
          candidate: Dict[str, Any],
          verified_shots: List[Dict[str, Any]],
          config: Any,
          gray_img: np.ndarray,
          ai_verifier: Any,
          timestamp: float
      ) -> Tuple[str, float, str, Dict[str, Any]]:
          try:
              # 1. Duplicate check
              dup_status, dup_info = DuplicateVerifier.evaluate(candidate["x_raw"], candidate["y_raw"], timestamp, verified_shots, config)
              if dup_status == "duplicate":
                  return "REJECTED", 0.0, f"DuplicateVerifier: Candidate matches existing Shot #{dup_info['matched_shot_number']} within {dup_info['dist']:.1f}px.", {"duplicate": dup_status}

              # 2. Geometry check
              geom_status, s_geom = GeometryVerifier.evaluate(
                  candidate["area"], candidate["circularity"], candidate["solidity"], candidate["aspect_ratio"], config
              )
              if geom_status == "fail" and s_geom <= 0.15:
                  return "REJECTED", 0.0, f"GeometryVerifier: Extreme geometry failure (area={candidate['area']:.1f}, circularity={candidate['circularity']:.2f}, aspect_ratio={candidate['aspect_ratio']:.2f}).", {"geometry": geom_status}

              # 3. YOLO check
              # Run YOLO crop logic
              is_verified, yolo_conf, _ = ai_verifier.verify_candidate_roi(
                  cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR), candidate["x_raw"], candidate["y_raw"], candidate["diameter_px"]
              )
              s_yolo = 1.0 if yolo_conf >= config.yolo_conf_strict else (0.5 if yolo_conf >= config.yolo_conf_loose else 0.0)

              # 4. Localization check
              loc_status, s_loc, loc_info = LocalizationVerifier.evaluate(np.array(candidate["raw_contour_np"]), gray_img, config)

              # 5. Active Disagreement (CONFLICT)
              is_yolo_strong = yolo_conf >= config.yolo_conf_strict
              is_yolo_fail = yolo_conf < config.yolo_conf_loose
              is_geom_fail = geom_status == "fail"
              is_loc_fail = loc_status == "fail"

              if is_yolo_strong and (is_geom_fail and is_loc_fail):
                  return "CONFLICT", 0.50, f"Active Disagreement: YOLO strongly verified hole (conf={yolo_conf:.2f}), but CV geometry and localization consensus failed (spread={loc_info['spread']:.1f}px).", {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status}
              if (geom_status == "strong_pass" and loc_status == "strong_pass") and is_yolo_fail:
                  return "CONFLICT", 0.50, f"Active Disagreement: CV shape and localization are perfect, but YOLO failed to detect a hole (conf={yolo_conf:.2f}).", {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status}

              # 6. Weighted sum
              w_sum = config.weight_geometry + config.weight_yolo + config.weight_localization
              w_g = config.weight_geometry / w_sum
              w_y = config.weight_yolo / w_sum
              w_l = config.weight_localization / w_sum

              raw_score = (w_g * s_geom) + (w_y * s_yolo) + (w_l * s_loc)
              if loc_status == "fail":
                  raw_score -= 0.15
              if s_yolo == 0.0:
                  raw_score -= 0.10

              fused_score = min(max(raw_score, 0.0), 1.0)
              verdict = "VERIFIED" if fused_score >= config.threshold_verified else "REVIEW"
              explanation = f"Verification score {fused_score:.2f} meets threshold." if verdict == "VERIFIED" else f"Failed threshold_verified {config.threshold_verified:.2f}. Low scoring modules: geom={s_geom:.2f}, yolo={yolo_conf:.2f}, loc={s_loc:.2f}"
              return verdict, fused_score, explanation, {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status, "spread": loc_info.get("spread")}
          except Exception as e:
              logger.error(f"Confidence Engine Failsafe: {e}", exc_info=True)
              return "REVIEW", 0.45, f"Failsafe triggered: Verifier system encountered a processing exception ({type(e).__name__}). degraded to manual review.", {"error": str(e)}
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_confidence_engine.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/services/confidence_engine.py backend/tests/test_confidence_engine.py
  git commit -m "feat: implement V&CE verifiers and ConfidenceEngine fusion layer"
  ```

---

### Task 4: Hook V&CE into Detection Endpoints

**Files:**
- Modify: `backend/app/services/cv_engine.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_detection_pipeline.py`

**Interfaces:**
- Consumes: `ConfidenceEngine.evaluate_candidate`
- Produces: Modified endpoints (returns candidates with V&CE verdicts and logs audits).

- [ ] **Step 1: Write the failing test**
  Create `backend/tests/test_detection_pipeline.py` testing detection endpoints with new optional `lane` param:
  ```python
  import unittest
  from fastapi.testclient import TestClient
  from app.main import app

  class TestDetectionPipeline(unittest.TestCase):
      def test_detect_endpoint_lane_param(self):
          client = TestClient(app)
          # Querying detect with a lane parameter
          response = client.post("/api/v1/detect?lane=1")
          # Expecting status 400 because no session exists, but check that it compiles and routes
          self.assertIn(response.status_code, [400, 404])
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_detection_pipeline.py`
  Expected: FAIL or compilation error in endpoints.

- [ ] **Step 3: Modify cv_engine.py and main.py**
  In `backend/app/services/cv_engine.py:detect_holes`:
  - Do NOT filter out candidates using AI verification inside `detect_holes`.
  - Return all raw proposals as a list of dictionaries, enclosing their contours and bounding boxes:
  ```python
  # Instead of ai_verifier.verify_candidate_roi checks at line 301, return raw metrics:
  new_holes.append({
      "x_raw": float(cX),
      "y_raw": float(cY),
      "diameter_px": float(equiv_diameter),
      "area": float(area),
      "circularity": float(circularity),
      "solidity": float(solidity),
      "aspect_ratio": float(aspect_ratio),
      "raw_contour": raw_contour_pts,
      "raw_contour_np": c # keep numpy contour for localization verifier
  })
  ```
  In `backend/app/main.py`:
  - Update `run_detection`, `capture_after_fire`, and `run_detect` endpoints:
    - Add `lane: Optional[int] = Query(None)` parameter.
    - Inside each endpoint:
      - Resolve `LaneConfig` by querying:
        `lane_config = await db.execute(select(models.LaneConfig).where(models.LaneConfig.lane == lane))`
        If not found, fallback to default config:
        `lane_config = await db.execute(select(models.LaneConfig).where(models.LaneConfig.lane == None))`
        If still not found, create a default in-memory configuration object.
      - Query verified existing shots:
        `shots_result = await db.execute(select(models.Shot).where(models.Shot.session_id == session_id).where(models.Shot.verdict == "VERIFIED"))`
      - Run `ConfidenceEngine.evaluate_candidate` on each candidate.
      - Process results:
        - If `VERIFIED`: Create `Shot`, mark `is_valid = True`, `verdict = "VERIFIED"`, call `apply_scoring_to_shot`.
        - If `REVIEW` or `CONFLICT`: Create `Shot`, mark `is_valid = False`, `boundary_status = "review_required"`, `verdict = verdict`, `verdict_explanation = explanation`. Do **NOT** run scoring.
        - If `REJECTED`: Skip Shot record creation.
      - Add a background task (`BackgroundTasks`) to save the `VerificationAudit` row asynchronously to DB, keeping API response latency under 500ms.
      - Broadcast WebSocket updates:
        - Broadcast `SHOT_DETECTED` for `VERIFIED`, `REVIEW`, and `CONFLICT` shots.

- [ ] **Step 4: Run test to verify it passes**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_detection_pipeline.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/services/cv_engine.py backend/app/main.py backend/tests/test_detection_pipeline.py
  git commit -m "feat: hook V&CE logic into all backend detection and capture routes"
  ```

---

### Task 5: Implement Adjudication & Update logic

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_adjudication.py`

**Interfaces:**
- Consumes: None
- Produces: Updated `PATCH /shots/{shot_id}` route with V&CE adjudication logs.

- [ ] **Step 1: Write the failing test**
  Create `backend/tests/test_adjudication.py` testing update shot adjudication logging:
  ```python
  import unittest
  from fastapi.testclient import TestClient
  from app.main import app

  class TestAdjudication(unittest.TestCase):
      def test_adjudication_patch_update(self):
          client = TestClient(app)
          # PATCH a shot with validation updates
          response = client.patch("/api/v1/shots/dummy_id", json={"boundary_status": "certain"})
          self.assertEqual(response.status_code, 404) # Shot doesn't exist but confirms route works
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_adjudication.py`
  Expected: FAIL or compilation errors.

- [ ] **Step 3: Modify update_shot in main.py**
  In `update_shot`:
  - Check if the updated shot is being approved (`boundary_status` is updated to something other than `review_required` and `is_valid` is not explicitly set to `False`):
    - If its original verdict was `REVIEW` or `CONFLICT`, execute `apply_scoring_to_shot(shot, session)` and mark `is_valid = True`.
    - Query the associated `VerificationAudit` row and record: `adjudication_decision = "ACCEPTED"`, `adjudicated_by = "operator"`, `adjudicated_at = datetime.utcnow()`.
  - Check if the updated shot is being excluded (`is_valid` is explicitly set to `False`):
    - Set `is_valid = False`.
    - Query the associated `VerificationAudit` row and record: `adjudication_decision = "REJECTED"`, `adjudicated_by = "operator"`, `adjudicated_at = datetime.utcnow()`.
  - Save changes to DB and commit.
  - Broadcast `SHOT_UPDATED` WebSocket event.

- [ ] **Step 4: Run test to verify it passes**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_adjudication.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/main.py backend/tests/test_adjudication.py
  git commit -m "feat: implement append-only adjudication updates in the PATCH shot route"
  ```

---

### Task 6: Implement Lane Config & Audit API routes

**Files:**
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_config_routes.py`

**Interfaces:**
- Consumes: None
- Produces: `POST /api/v1/lanes/{lane}/config`, `GET /api/v1/lanes/{lane}/config`, `DELETE /api/v1/lanes/{lane}/config`, `GET /api/v1/verification/audit`.

- [ ] **Step 1: Write the failing test**
  Create `backend/tests/test_config_routes.py` testing config setup, fallback, and audit filtering:
  ```python
  import unittest
  from fastapi.testclient import TestClient
  from app.main import app

  class TestConfigRoutes(unittest.TestCase):
      def test_lane_config_flow(self):
          client = TestClient(app)
          # Retrieve configuration for lane 99
          response = client.get("/api/v1/lanes/99/config")
          self.assertEqual(response.status_code, 200) # Should return default config if none explicitly set
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_config_routes.py`
  Expected: FAIL with status 404 (routes not implemented).

- [ ] **Step 3: Implement new routes in main.py**
  Add the following endpoints to `backend/app/main.py`:
  - `GET /api/v1/lanes/{lane}/config`: Retrieves the specific configuration for a lane. If it does not exist, returns the global default config (`lane=None`). If that doesn't exist, instantiates a default.
  - `POST /api/v1/lanes/{lane}/config`: Creates or updates a lane's configuration parameters.
  - `DELETE /api/v1/lanes/{lane}/config`: Deletes the configuration for a lane, causing it to fall back to default immediately.
  - `GET /api/v1/verification/audit`: Retrieves list of audits, supporting optional filter parameters: `lane_id` (Integer), `verdict` (String), `start_time` / `end_time` (ISO-DateTime).

- [ ] **Step 4: Run test to verify it passes**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_config_routes.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/main.py backend/tests/test_config_routes.py
  git commit -m "feat: implement lane config management and audit retrieval routes"
  ```
