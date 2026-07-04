import unittest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.core.database import AsyncSessionLocal
from app.models import models

class TestAdjudication(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.created_ids = {
            "session": [],
            "shot": [],
            "audit": []
        }

    async def asyncTearDown(self):
        # Clean up database entries created during the tests
        async with AsyncSessionLocal() as db:
            for audit_id in self.created_ids["audit"]:
                await db.execute(
                    models.VerificationAudit.__table__.delete().where(models.VerificationAudit.id == audit_id)
                )
            for shot_id in self.created_ids["shot"]:
                await db.execute(
                    models.Shot.__table__.delete().where(models.Shot.id == shot_id)
                )
            for session_id in self.created_ids["session"]:
                await db.execute(
                    models.Session.__table__.delete().where(models.Session.id == session_id)
                )
            await db.commit()

    async def create_test_entities(self, db, verdict="REVIEW", boundary_status="review_required", is_valid=True):
        session = models.Session(
            name="Test Adjudication Session",
            description="Test description",
            status="active",
            target_type="figure_11",
            bullet_caliber=5.56
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        self.created_ids["session"].append(session.id)

        shot = models.Shot(
            session_id=session.id,
            shot_number=1,
            x_raw=100.0,
            y_raw=150.0,
            diameter_px=10.0,
            confidence=0.8,
            is_valid=is_valid,
            verdict=verdict,
            boundary_status=boundary_status
        )
        db.add(shot)
        await db.commit()
        await db.refresh(shot)
        self.created_ids["shot"].append(shot.id)

        audit = models.VerificationAudit(
            session_id=session.id,
            shot_id=shot.id,
            lane_id=1,
            x_raw=100.0,
            y_raw=150.0,
            signals_json={"geom_circ": 0.8},
            verdict=verdict,
            confidence_score=0.8,
            explanation="Test explanation",
            adjudication_decision=None,
            adjudicated_by=None,
            adjudicated_at=None
        )
        db.add(audit)
        await db.commit()
        await db.refresh(audit)
        self.created_ids["audit"].append(audit.id)

        return session, shot, audit

    async def test_adjudication_patch_update_not_found(self):
        response = self.client.patch("/api/v1/shots/dummy_id", json={"boundary_status": "certain"})
        self.assertEqual(response.status_code, 404)

    async def test_adjudication_approve_review_shot(self):
        async with AsyncSessionLocal() as db:
            session, shot, audit = await self.create_test_entities(db, verdict="REVIEW", boundary_status="review_required", is_valid=True)
            shot_id = shot.id
            audit_id = audit.id

        # Perform the PATCH request to approve the shot (setting boundary_status other than review_required and not setting is_valid=False)
        response = self.client.patch(
            f"/api/v1/shots/{shot_id}",
            json={"boundary_status": "certain"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["boundary_status"], "certain")
        self.assertEqual(data["is_valid"], True)
        self.assertIsNotNone(data["score"]) # Should have run apply_scoring_to_shot

        # Verify database states
        async with AsyncSessionLocal() as db:
            # Check shot update
            updated_shot_res = await db.execute(
                select(models.Shot).where(models.Shot.id == shot_id)
            )
            updated_shot = updated_shot_res.scalars().first()
            self.assertEqual(updated_shot.boundary_status, "certain")
            self.assertEqual(updated_shot.is_valid, True)
            self.assertIsNotNone(updated_shot.score)

            # Check verification audit update
            updated_audit_res = await db.execute(
                select(models.VerificationAudit).where(models.VerificationAudit.id == audit_id)
            )
            updated_audit = updated_audit_res.scalars().first()
            self.assertEqual(updated_audit.adjudication_decision, "ACCEPTED")
            self.assertEqual(updated_audit.adjudicated_by, "operator")
            self.assertIsNotNone(updated_audit.adjudicated_at)

    async def test_adjudication_exclude_shot(self):
        async with AsyncSessionLocal() as db:
            session, shot, audit = await self.create_test_entities(db, verdict="REVIEW", boundary_status="review_required", is_valid=True)
            shot_id = shot.id
            audit_id = audit.id

        # Perform PATCH request to exclude the shot (setting is_valid=False)
        response = self.client.patch(
            f"/api/v1/shots/{shot_id}",
            json={"is_valid": False}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["is_valid"], False)

        # Verify database states
        async with AsyncSessionLocal() as db:
            # Check shot update
            updated_shot_res = await db.execute(
                select(models.Shot).where(models.Shot.id == shot_id)
            )
            updated_shot = updated_shot_res.scalars().first()
            self.assertEqual(updated_shot.is_valid, False)

            # Check verification audit update
            updated_audit_res = await db.execute(
                select(models.VerificationAudit).where(models.VerificationAudit.id == audit_id)
            )
            updated_audit = updated_audit_res.scalars().first()
            self.assertEqual(updated_audit.adjudication_decision, "REJECTED")
            self.assertEqual(updated_audit.adjudicated_by, "operator")
            self.assertIsNotNone(updated_audit.adjudicated_at)

    async def test_adjudication_approve_non_review_shot_no_scoring(self):
        async with AsyncSessionLocal() as db:
            session, shot, audit = await self.create_test_entities(db, verdict="STRONG_PASS", boundary_status="certain", is_valid=True)
            shot_id = shot.id
            audit_id = audit.id

        # PATCH to change status, but since it is not REVIEW or CONFLICT, scoring should not trigger (or not update it)
        response = self.client.patch(
            f"/api/v1/shots/{shot_id}",
            json={"boundary_status": "certain"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["boundary_status"], "certain")

        # Verify verification audit is still updated
        async with AsyncSessionLocal() as db:
            updated_audit_res = await db.execute(
                select(models.VerificationAudit).where(models.VerificationAudit.id == audit_id)
            )
            updated_audit = updated_audit_res.scalars().first()
            self.assertEqual(updated_audit.adjudication_decision, "ACCEPTED")
            self.assertEqual(updated_audit.adjudicated_by, "operator")
