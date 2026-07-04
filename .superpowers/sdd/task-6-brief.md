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
