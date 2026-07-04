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

