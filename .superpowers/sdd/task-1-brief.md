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

