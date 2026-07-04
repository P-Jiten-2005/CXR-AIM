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

