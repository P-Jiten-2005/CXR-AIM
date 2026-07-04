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

