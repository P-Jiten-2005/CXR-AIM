import unittest
import numpy as np
import cv2
import app.services.confidence_engine
from app.services.confidence_engine import ConfidenceEngine, GeometryVerifier, DuplicateVerifier, LocalizationVerifier
from app.schemas.schemas import LaneConfigBase

class MockAIVerifier:
    def __init__(self, is_verified=True, yolo_conf=0.8, class_name="hole"):
        self.is_verified = is_verified
        self.yolo_conf = yolo_conf
        self.class_name = class_name
        self.called_with = None

    def verify_candidate_roi(self, img, cX, cY, diameter_px, *args, **kwargs):
        self.called_with = (img, cX, cY, diameter_px)
        return self.is_verified, self.yolo_conf, self.class_name

class TestConfidenceEngine(unittest.TestCase):
    def setUp(self):
        self.config = LaneConfigBase()
        self.mock_ai = MockAIVerifier()
        app.services.confidence_engine.ai_verifier = self.mock_ai

    def test_geometry_verifier_strong_pass(self):
        # Strict ranges: circularity >= 0.65, solidity >= 0.80, aspect_ratio between 0.7 and 1.4
        # Area loose: 15.0 <= area <= 5000.0
        status, score = GeometryVerifier.evaluate(200.0, 0.8, 0.95, 1.0, self.config)
        self.assertEqual(status, "strong_pass")
        self.assertEqual(score, 1.0)

    def test_geometry_verifier_weak_pass(self):
        # Loose ranges: circularity loose (0.45 <= circ < 0.65), solidity loose (0.65 <= solidity < 0.80),
        # aspect ratio loose (0.3 <= aspect < 0.7 or 1.4 < aspect <= 3.0)
        status, score = GeometryVerifier.evaluate(200.0, 0.5, 0.7, 2.0, self.config)
        self.assertEqual(status, "weak_pass")
        self.assertEqual(score, 0.5)

    def test_geometry_verifier_fail_out_of_loose(self):
        # Circularity below loose -> geom_score has 0.0, yields "fail" status
        status, score = GeometryVerifier.evaluate(200.0, 0.2, 0.95, 1.0, self.config)
        self.assertEqual(status, "fail")
        self.assertLess(score, 1.0)

    def test_geometry_verifier_fail_area_out_of_bounds(self):
        # Area below loose limit (15.0) -> fails even if shape parameters are perfect
        status, score = GeometryVerifier.evaluate(10.0, 0.8, 0.95, 1.0, self.config)
        self.assertEqual(status, "fail")

    def test_duplicate_verifier_neutral(self):
        verified_shots = [
            {"shot_number": 1, "x_raw": 100.0, "y_raw": 100.0, "created_at_ts": 10.0}
        ]
        # Dist is large, so not duplicate
        status, info = DuplicateVerifier.evaluate(200.0, 200.0, 11.0, verified_shots, self.config)
        self.assertEqual(status, "neutral")
        self.assertEqual(info, {})

    def test_duplicate_verifier_duplicate(self):
        verified_shots = [
            {"shot_number": 1, "x_raw": 100.0, "y_raw": 100.0, "created_at_ts": 10.0, "id": "shot_1"}
        ]
        # Distance within duplicate_radius_px (15.0) and time within duplicate_time_window_sec (5.0)
        status, info = DuplicateVerifier.evaluate(105.0, 105.0, 12.0, verified_shots, self.config)
        self.assertEqual(status, "duplicate")
        self.assertEqual(info["matched_shot_number"], 1)
        self.assertEqual(info["shot_id"], "shot_1")
        self.assertLess(info["dist"], 15.0)

    def test_localization_verifier_strong_pass(self):
        # Create a simple square contour representing a hole
        c = np.array([[[10, 10]], [[10, 20]], [[20, 20]], [[20, 10]]], dtype=np.int32)
        # Create a gray image where the ROI area is dark (bullet hole interior)
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255
        gray_img[10:21, 10:21] = 50 # Dark hole
        gray_img[15, 15] = 10 # True intensity peak center

        status, score, info = LocalizationVerifier.evaluate(c, gray_img, self.config)
        self.assertEqual(status, "strong_pass")
        self.assertEqual(score, 1.0)
        self.assertLessEqual(info["spread"], self.config.localization_spread_threshold)

    def test_localization_verifier_fail_spread(self):
        # Create a contour and a gray image that creates a large mismatch between intensity weighted centroid and normal center
        c = np.array([[[10, 10]], [[10, 30]], [[30, 30]], [[30, 10]]], dtype=np.int32)
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255
        # Put a very dark spot at the extreme bottom right corner of the bounding box
        gray_img[28:31, 28:31] = 0

        status, score, info = LocalizationVerifier.evaluate(c, gray_img, self.config)
        self.assertEqual(status, "fail")
        self.assertEqual(score, 0.2)
        self.assertGreater(info["spread"], self.config.localization_spread_threshold)

    def test_confidence_engine_duplicate_rejection(self):
        candidate = {"x_raw": 105.0, "y_raw": 105.0, "area": 100.0, "circularity": 0.8, "solidity": 0.9, "aspect_ratio": 1.0, "diameter_px": 10.0, "raw_contour_np": [[[10,10]]]}
        verified_shots = [{"shot_number": 1, "x_raw": 100.0, "y_raw": 100.0, "created_at_ts": 10.0, "id": "shot_1"}]
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255

        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "REJECTED")
        self.assertEqual(score, 0.0)
        self.assertIn("DuplicateVerifier", explanation)
        self.assertEqual(signals, {"duplicate": "duplicate"})

    def test_confidence_engine_geometry_rejection(self):
        # Geometry status is "fail" and s_geom <= 0.15 (very bad geometry)
        candidate = {"x_raw": 150.0, "y_raw": 150.0, "area": 100.0, "circularity": 0.1, "solidity": 0.1, "aspect_ratio": 5.0, "diameter_px": 10.0, "raw_contour_np": [[[10,10]]]}
        verified_shots = []
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255

        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "REJECTED")
        self.assertEqual(score, 0.0)
        self.assertIn("GeometryVerifier", explanation)
        self.assertEqual(signals, {"geometry": "fail"})

    def test_confidence_engine_conflict_yolo_strong_cv_fail(self):
        # YOLO conf >= config.yolo_conf_strict (0.25), but CV geometry and localization consensus failed
        # Make localization fail by using a spread out gray image
        c = np.array([[[10, 10]], [[10, 30]], [[30, 30]], [[30, 10]]], dtype=np.int32)
        candidate = {
            "x_raw": 150.0, "y_raw": 150.0, 
            "area": 1000.0, "circularity": 0.2, "solidity": 0.8, "aspect_ratio": 1.0,
            "diameter_px": 10.0, 
            "raw_contour_np": c.tolist()
        }
        verified_shots = []
        app.services.confidence_engine.ai_verifier = MockAIVerifier(is_verified=True, yolo_conf=0.9, class_name="hole") # strong YOLO
        # localization fails
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255
        gray_img[28:31, 28:31] = 0

        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "CONFLICT")
        self.assertEqual(score, 0.50)
        self.assertIn("Active Disagreement", explanation)
        self.assertEqual(signals["yolo"], 0.9)
        self.assertEqual(signals["geometry"], "fail")
        self.assertEqual(signals["localization"], "fail")

    def test_confidence_engine_conflict_cv_strong_yolo_fail(self):
        # CV shape (GeometryVerifier strong_pass) and localization (LocalizationVerifier strong_pass) are perfect,
        # but YOLO failed to detect a hole (conf < yolo_conf_loose (0.10))
        c = np.array([[[10, 10]], [[10, 20]], [[20, 20]], [[20, 10]]], dtype=np.int32)
        candidate = {
            "x_raw": 150.0, "y_raw": 150.0, 
            "area": 200.0, "circularity": 0.8, "solidity": 0.95, "aspect_ratio": 1.0,
            "diameter_px": 10.0, 
            "raw_contour_np": c.tolist()
        }
        verified_shots = []
        app.services.confidence_engine.ai_verifier = MockAIVerifier(is_verified=False, yolo_conf=0.05, class_name="false_positive")
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255
        gray_img[10:21, 10:21] = 50 # Perfect dark hole
        gray_img[15, 15] = 10 # True intensity peak center

        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "CONFLICT")
        self.assertEqual(score, 0.50)
        self.assertIn("Active Disagreement", explanation)
        self.assertEqual(signals["yolo"], 0.05)
        self.assertEqual(signals["geometry"], "strong_pass")
        self.assertEqual(signals["localization"], "strong_pass")

    def test_duplicate_verifier_sqlalchemy_object(self):
        class MockSQLAShot:
            def __init__(self, shot_number, x_raw, y_raw, created_at, id):
                self.shot_number = shot_number
                self.x_raw = x_raw
                self.y_raw = y_raw
                self.created_at = created_at
                self.id = id

        import datetime
        dt = datetime.datetime(2026, 7, 4, 12, 0, 0)
        verified_shots = [MockSQLAShot(1, 100.0, 100.0, dt, "shot_1")]
        # Distance within duplicate_radius_px (15.0) and time within duplicate_time_window_sec (5.0)
        status, info = DuplicateVerifier.evaluate(105.0, 105.0, dt.timestamp() + 2.0, verified_shots, self.config)
        self.assertEqual(status, "duplicate")
        self.assertEqual(info["matched_shot_number"], 1)

    def test_geometry_verifier_circularity_above_one(self):
        # Circularity slightly above 1.0 (digital contour artifact) should still pass
        status, score = GeometryVerifier.evaluate(200.0, 1.05, 0.95, 1.0, self.config)
        self.assertEqual(status, "strong_pass")
        self.assertEqual(score, 1.0)

    def test_confidence_engine_area_out_of_bounds_rejection(self):
        # Candidate shape is perfect but area is outside loose bounds -> REJECTED
        candidate = {"x_raw": 150.0, "y_raw": 150.0, "area": 10.0, "circularity": 0.8, "solidity": 0.9, "aspect_ratio": 1.0, "diameter_px": 10.0, "raw_contour_np": [[[10,10]]]}
        verified_shots = []
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255

        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "REJECTED")

    def test_confidence_engine_failsafe_loc_error(self):
        # YOLO is strong, geometry is weak, localization fails with zero moments (e.g. empty contour)
        # Should trigger the failsafe block due to empty contour exception (returns REVIEW with 0.45 score)
        candidate = {
            "x_raw": 150.0, "y_raw": 150.0,
            "area": 100.0, "circularity": 0.2, "solidity": 0.8, "aspect_ratio": 1.0,
            "diameter_px": 10.0,
            "raw_contour_np": [] # Will cause empty contour ValueError exception
        }
        verified_shots = []
        app.services.confidence_engine.ai_verifier = MockAIVerifier(is_verified=True, yolo_conf=0.9, class_name="hole")
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255

        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "REVIEW")
        self.assertEqual(score, 0.45)
        self.assertIn("error", signals)

    def test_confidence_engine_failsafe(self):
        # Triggers exception in evaluation -> degraded to manual review
        candidate = None # None will throw TypeError when accessed like candidate["x_raw"]
        verified_shots = []
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255

        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "REVIEW")
        self.assertEqual(score, 0.45)
        self.assertIn("Failsafe triggered", explanation)
        self.assertIn("error", signals)

    def test_confidence_engine_timeout(self):
        # Simulate a slow verifier by sleeping inside verify_candidate_roi
        import time as pytime
        class SlowAIVerifier:
            def verify_candidate_roi(self, img, cX, cY, diameter_px, *args, **kwargs):
                pytime.sleep(0.6) # Exceeds 0.45s timeout
                return True, 0.9, "hole"
                
        app.services.confidence_engine.ai_verifier = SlowAIVerifier()
        
        candidate = {
            "x_raw": 150.0, "y_raw": 150.0,
            "area": 100.0, "circularity": 0.8, "solidity": 0.9, "aspect_ratio": 1.0,
            "diameter_px": 10.0,
            "raw_contour_np": [[[10,10]]]
        }
        verified_shots = []
        gray_img = np.ones((100, 100), dtype=np.uint8) * 255
        
        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate, verified_shots, self.config, gray_img, timestamp=12.0
        )
        self.assertEqual(verdict, "REVIEW")
        self.assertEqual(score, 0.45)
        self.assertIn("timed out", explanation)

if __name__ == '__main__':
    unittest.main()
