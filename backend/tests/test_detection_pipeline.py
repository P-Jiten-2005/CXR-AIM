import unittest
from io import BytesIO
from fastapi.testclient import TestClient
from app.main import app

class TestDetectionPipeline(unittest.TestCase):
    def test_detect_endpoint_lane_param(self):
        client = TestClient(app)
        # Querying detect with a lane parameter
        response = client.post("/api/v1/detect?lane=1")
        # Expecting status 200 (if active session & images exist) or 400/404
        self.assertIn(response.status_code, [200, 400, 404])

    def test_run_detection_endpoint_lane_param(self):
        client = TestClient(app)
        # Querying session detect with a lane parameter
        # Pass a dummy file to avoid 422 Unprocessable Entity
        file_data = {"file": ("test.jpg", BytesIO(b"dummy image data"), "image/jpeg")}
        response = client.post("/api/v1/sessions/test-session-id/detect?lane=1", files=file_data)
        # Expecting status 404 because "test-session-id" does not exist
        self.assertEqual(response.status_code, 404)

    def test_capture_after_fire_endpoint_lane_param(self):
        client = TestClient(app)
        # Querying capture after fire with a lane parameter
        response = client.post("/api/v1/capture/after-fire?lane=1")
        # Expecting status 400 because no active session exists or camera is not streaming
        self.assertIn(response.status_code, [400, 404])
