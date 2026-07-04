import unittest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.core.database import AsyncSessionLocal
from app.models import models
from app.schemas import schemas

class TestConfigRoutes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.created_configs = []
        self.created_audits = []
        self.created_sessions = []
        self.created_shots = []

    async def asyncTearDown(self):
        # Clean up database entries created during the tests
        async with AsyncSessionLocal() as db:
            for audit_id in self.created_audits:
                await db.execute(
                    models.VerificationAudit.__table__.delete().where(models.VerificationAudit.id == audit_id)
                )
            for shot_id in self.created_shots:
                await db.execute(
                    models.Shot.__table__.delete().where(models.Shot.id == shot_id)
                )
            for session_id in self.created_sessions:
                await db.execute(
                    models.Session.__table__.delete().where(models.Session.id == session_id)
                )
            for config_id in self.created_configs:
                await db.execute(
                    models.LaneConfig.__table__.delete().where(models.LaneConfig.id == config_id)
                )
            await db.commit()

    async def test_lane_config_flow(self):
        # 1. Retrieve configuration for lane 99 (does not exist yet)
        response = self.client.get("/api/v1/lanes/99/config")
        self.assertEqual(response.status_code, 200)
        config_data = response.json()
        self.assertEqual(config_data["lane"], 99)
        # Should match default geom_area_strict_min = 40.0
        self.assertEqual(config_data["geom_area_strict_min"], 40.0)

        # 2. Update configuration for lane 99
        payload = {
            "geom_area_strict_min": 50.0,
            "geom_area_strict_max": 2000.0,
            "geom_area_loose_min": 20.0,
            "geom_area_loose_max": 6000.0,
            "geom_circ_strict": 0.70,
            "geom_circ_loose": 0.50,
            "geom_aspect_strict_min": 0.8,
            "geom_aspect_strict_max": 1.3,
            "geom_aspect_loose_min": 0.4,
            "geom_aspect_loose_max": 2.5,
            "duplicate_radius_px": 20.0,
            "duplicate_time_window_sec": 6.0,
            "localization_spread_threshold": 6.0,
            "yolo_conf_strict": 0.30,
            "yolo_conf_loose": 0.15,
            "weight_geometry": 0.30,
            "weight_yolo": 0.50,
            "weight_localization": 0.20,
            "threshold_verified": 0.80
        }
        response = self.client.post("/api/v1/lanes/99/config", json=payload)
        self.assertEqual(response.status_code, 200)
        saved_data = response.json()
        self.assertEqual(saved_data["lane"], 99)
        self.assertEqual(saved_data["geom_area_strict_min"], 50.0)
        self.assertIn("id", saved_data)
        self.created_configs.append(saved_data["id"])

        # 3. Retrieve config again, should return updated values
        response = self.client.get("/api/v1/lanes/99/config")
        self.assertEqual(response.status_code, 200)
        config_data = response.json()
        self.assertEqual(config_data["geom_area_strict_min"], 50.0)

        # 4. Delete configuration for lane 99
        response = self.client.delete("/api/v1/lanes/99/config")
        self.assertEqual(response.status_code, 200)
        
        # 5. Retrieve configuration again, should fall back to default (geom_area_strict_min = 40.0)
        response = self.client.get("/api/v1/lanes/99/config")
        self.assertEqual(response.status_code, 200)
        config_data = response.json()
        self.assertEqual(config_data["geom_area_strict_min"], 40.0)

    async def test_verification_audit_filtering(self):
        # Create a test session and shots/audits directly in the database
        async with AsyncSessionLocal() as db:
            session = models.Session(
                name="Test Audit Session",
                description="Test description",
                status="active",
                target_type="figure_11",
                bullet_caliber=5.56
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            self.created_sessions.append(session.id)

            shot = models.Shot(
                session_id=session.id,
                shot_number=1,
                x_raw=100.0,
                y_raw=150.0,
                diameter_px=10.0,
                confidence=0.8,
                is_valid=True
            )
            db.add(shot)
            await db.commit()
            await db.refresh(shot)
            self.created_shots.append(shot.id)

            # Audit 1: lane 1, verdict VERIFIED, timestamp now - 10 min
            audit1 = models.VerificationAudit(
                session_id=session.id,
                shot_id=shot.id,
                lane_id=1,
                x_raw=100.0,
                y_raw=150.0,
                signals_json={"geom_circ": 0.8},
                verdict="VERIFIED",
                confidence_score=0.85,
                explanation="Test verified",
                timestamp=datetime.utcnow() - timedelta(minutes=10)
            )
            # Audit 2: lane 2, verdict REVIEW, timestamp now - 5 mins
            audit2 = models.VerificationAudit(
                session_id=session.id,
                shot_id=shot.id,
                lane_id=2,
                x_raw=110.0,
                y_raw=160.0,
                signals_json={"geom_circ": 0.5},
                verdict="REVIEW",
                confidence_score=0.65,
                explanation="Test review required",
                timestamp=datetime.utcnow() - timedelta(minutes=5)
            )
            # Audit 3: lane 1, verdict BYPASSED, timestamp 1 day ago
            audit3 = models.VerificationAudit(
                session_id=session.id,
                shot_id=shot.id,
                lane_id=1,
                x_raw=120.0,
                y_raw=170.0,
                signals_json={"geom_circ": 0.9},
                verdict="BYPASSED",
                confidence_score=0.95,
                explanation="Test bypassed",
                timestamp=datetime.utcnow() - timedelta(days=1)
            )

            db.add_all([audit1, audit2, audit3])
            await db.commit()
            await db.refresh(audit1)
            await db.refresh(audit2)
            await db.refresh(audit3)

            self.created_audits.extend([audit1.id, audit2.id, audit3.id])

        # Test filtering by lane_id
        response = self.client.get("/api/v1/verification/audit?lane_id=1")
        self.assertEqual(response.status_code, 200)
        audits = response.json()
        self.assertEqual(len(audits), 2)
        self.assertTrue(all(a["lane_id"] == 1 for a in audits))

        # Test filtering by verdict
        response = self.client.get("/api/v1/verification/audit?verdict=REVIEW")
        self.assertEqual(response.status_code, 200)
        audits = response.json()
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["verdict"], "REVIEW")

        # Test filtering by start_time / end_time
        # start_time = now - 15 mins, end_time = now
        start_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
        end_time = datetime.utcnow().isoformat()
        response = self.client.get(f"/api/v1/verification/audit?start_time={start_time}&end_time={end_time}")
        self.assertEqual(response.status_code, 200)
        audits = response.json()
        # Should include audit1 and audit2 (created 10 and 5 mins ago), but not audit3 (1 day ago)
        self.assertEqual(len(audits), 2)
        audit_ids = [a["id"] for a in audits]
        self.assertIn(audit1.id, audit_ids)
        self.assertIn(audit2.id, audit_ids)
