import unittest
from app.schemas import schemas
from datetime import datetime

class TestSchemas(unittest.TestCase):
    def test_shot_response_vce_fields(self):
        # Test if new V&CE fields are present in ShotResponse
        shot = schemas.ShotResponse(
            id="uuid", session_id="sess", shot_number=1, x_raw=10.0, y_raw=20.0,
            diameter_px=8.0, confidence=0.8, is_valid=True, created_at=datetime.now(),
            verdict="VERIFIED", verdict_explanation="All clear", confidence_score=0.9
        )
        self.assertEqual(shot.verdict, "VERIFIED")
        self.assertEqual(shot.confidence_score, 0.9)

    def test_lane_config_create_defaults(self):
        config = schemas.LaneConfigCreate()
        self.assertIsNone(config.lane)
        self.assertEqual(config.geom_area_strict_min, 40.0)
        self.assertEqual(config.threshold_verified, 0.75)

    def test_lane_config_response(self):
        now = datetime.now()
        config = schemas.LaneConfigResponse(
            id="cfg_1",
            lane=2,
            geom_area_strict_min=45.0,
            geom_area_strict_max=1200.0,
            geom_area_loose_min=20.0,
            geom_area_loose_max=4000.0,
            geom_circ_strict=0.7,
            geom_circ_loose=0.5,
            geom_aspect_strict_min=0.8,
            geom_aspect_strict_max=1.3,
            geom_aspect_loose_min=0.4,
            geom_aspect_loose_max=2.5,
            duplicate_radius_px=12.0,
            duplicate_time_window_sec=6.0,
            localization_spread_threshold=4.5,
            yolo_conf_strict=0.3,
            yolo_conf_loose=0.15,
            weight_geometry=0.35,
            weight_yolo=0.45,
            weight_localization=0.2,
            threshold_verified=0.8,
            created_at=now,
            updated_at=now
        )
        self.assertEqual(config.id, "cfg_1")
        self.assertEqual(config.lane, 2)
        self.assertEqual(config.weight_geometry, 0.35)

    def test_verification_audit_response(self):
        now = datetime.now()
        audit = schemas.VerificationAuditResponse(
            id="audit_1",
            timestamp=now,
            lane_id=3,
            session_id="sess_123",
            shot_id="shot_456",
            x_raw=100.5,
            y_raw=200.5,
            signals_json={"geom_score": 0.8},
            verdict="VERIFIED",
            confidence_score=0.85,
            explanation="Good shot",
            adjudication_decision="APPROVED",
            adjudicated_by="admin",
            adjudicated_at=now
        )
        self.assertEqual(audit.id, "audit_1")
        self.assertEqual(audit.signals_json, {"geom_score": 0.8})
        self.assertEqual(audit.adjudication_decision, "APPROVED")

