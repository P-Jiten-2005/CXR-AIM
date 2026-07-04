# Task 4 Report: Hook V&CE into Detection Endpoints

## Executive Summary

The Confidence Engine (V&CE) has been successfully hooked into the backend detection endpoints.
- Early YOLO verification and rejection inside `cv_engine.py:detect_holes` has been disabled to ensure all contour-based candidate proposals are returned.
- Modified the following FastAPI endpoints:
  - `/sessions/{session_id}/detect` (`run_detection`)
  - `/capture/after-fire` (`capture_after_fire`)
  - `/detect` (`run_detect`)
- Implemented asynchronous `VerificationAudit` trail logging using FastAPI's `BackgroundTasks`, keeping API response latency low.
- Updated the tests with unit and integration coverage for the detection endpoints with the optional `lane` parameter. All tests are passing.

---

## Detailed Changes

### 1. `backend/app/services/cv_engine.py`
- Disabled early YOLO verification and ROI classification inside `detect_holes`.
- Modified the function to return all raw proposals (contours, bounding boxes, circularity, solidity, etc.) along with the aligned current frame (`aligned_current`).

### 2. `backend/app/main.py`
- Added the optional query parameter `lane: Optional[int] = Query(None)` to `run_detection`, `capture_after_fire`, and `run_detect` endpoints.
- Implemented `resolve_lane_config` to locate `LaneConfig` on the DB or fall back to default or an in-memory configuration.
- Standardized query of verified existing shots in each endpoint.
- Invoked `ConfidenceEngine.evaluate_candidate` for all detected candidates.
- Processed V&CE verdicts:
  - `VERIFIED`: Saved a `Shot` record with `is_valid = True`, verdict `"VERIFIED"`, and applied PILSS target scoring.
  - `REVIEW` / `CONFLICT`: Saved a `Shot` record with `is_valid = False`, verdict `verdict`, explanation `explanation`, and `boundary_status = "review_required"`. Excluded scoring.
  - `REJECTED`: Skipped creating `Shot` records.
- Dispatched an asynchronous background task (`save_verification_audit`) using FastAPI's `BackgroundTasks` to write the `VerificationAudit` row into the database.
- Ensured WebSocket `SHOT_DETECTED` events are broadcasted for all saved shots (`VERIFIED`, `REVIEW`, and `CONFLICT`).

### 3. `backend/tests/test_detection_pipeline.py`
- Created a new test file containing:
  - `test_detect_endpoint_lane_param`
  - `test_run_detection_endpoint_lane_param`
  - `test_capture_after_fire_endpoint_lane_param`

### 4. `backend/requirements.txt`
- Added `httpx>=0.28.1` to the requirement dependencies to support the `FastAPI.testclient` module.

---

## Verification Results

The entire backend test suite has been run successfully:
```bash
.\venv\Scripts\python.exe -m unittest tests.test_confidence_engine tests.test_db_migrations tests.test_schemas tests.test_detection_pipeline
```

**Output:**
```
Ran 27 tests in 1.245s

OK
```

All 27 unit and integration tests passed, verifying:
1. `ConfidenceEngine` correctly handles geometry, duplicates, localizations, conflicts, failsafes, and timeouts.
2. Database schema migrations for new auditing tables and updated columns are correct.
3. FastAPI routing and optional `lane` parameter resolution on the endpoints are functional.
