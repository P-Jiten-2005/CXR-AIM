import os
import shutil
import cv2
import numpy as np
import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("app.main")

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import engine, Base, get_db
from app.models import models
from app.schemas import schemas
from app.services.cv_engine import cv_engine
from app.services.confidence_engine import ConfidenceEngine
from app.services.ws_manager import ws_manager
from app.services.camera_service import camera_service
from app.services import scoring_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite/PostgreSQL schema dynamically on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add any missing additive columns to pre-existing tables (scoring/target fields)
    from app.core.database import run_additive_migrations
    try:
        await run_additive_migrations()
    except Exception as e:
        logger.error(f"Additive migration step failed (non-fatal): {e}")

    # Load the active model version from the database on startup
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.ai_verifier import ai_verifier
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(models.ModelVersion).where(models.ModelVersion.is_active == True)
            )
            active_model = result.scalars().first()
            if active_model and os.path.exists(active_model.model_path):
                ai_verifier.load_model(active_model.model_path)
                logger.info(f"Loaded active model version from DB: {active_model.version_str} ({active_model.model_path})")
            else:
                logger.info("No active model found in DB or file doesn't exist, using default.")
    except Exception as e:
        logger.error(f"Failed to load active model on startup: {e}")
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the upload directory to serve captured frames to the dashboard canvas
app.mount("/static/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


async def check_and_reload_active_model(db: AsyncSession):
    try:
        from app.services.ai_verifier import ai_verifier
        result = await db.execute(
            select(models.ModelVersion).where(models.ModelVersion.is_active == True)
        )
        active_model = result.scalars().first()
        if active_model and os.path.exists(active_model.model_path):
            if ai_verifier.model_path != active_model.model_path:
                logger.info(f"Model version change detected in database. Reloading verifier with: {active_model.model_path}")
                ai_verifier.load_model(active_model.model_path)
        elif not active_model and ai_verifier.model_path != "yolov8s.pt":
            logger.info("No active model found in DB, resetting verifier to default yolov8s.pt")
            ai_verifier.load_model("yolov8s.pt")
    except Exception as e:
        logger.error(f"Failed to check and reload active model: {e}")


# --- Scoring helpers (additive; do not affect detection) ---

def apply_scoring_to_shot(shot, session) -> None:
    """Populate scoring fields on a freshly-detected Shot using the session's target template.
    Runs after detection; never raises (scoring_service swallows errors)."""
    try:
        target = scoring_service.load_target(getattr(session, "target_type", None))
        caliber = getattr(session, "bullet_caliber", None) or 5.56
        result = scoring_service.score_warped_shot(
            x_warped=shot.x_raw,
            y_warped=shot.y_raw,
            diameter_px_warped=shot.diameter_px,
            target=target,
            bullet_caliber_mm=caliber,
            geometry_homography_mm=getattr(session, "geometry_homography_json", None),
        )
        for key, value in result.items():
            setattr(shot, key, value)
    except Exception as e:
        logger.error(f"apply_scoring_to_shot failed: {e}")


async def resolve_lane_config(db: AsyncSession, lane: Optional[int]) -> models.LaneConfig:
    if lane is not None:
        result = await db.execute(
            select(models.LaneConfig).where(models.LaneConfig.lane == lane)
        )
        lane_config = result.scalars().first()
        if lane_config:
            return lane_config

    # fallback to default config in DB (where lane is None)
    result = await db.execute(
        select(models.LaneConfig).where(models.LaneConfig.lane == None)
    )
    lane_config = result.scalars().first()
    if lane_config:
        return lane_config

    # still not found, create in-memory default configuration object
    return models.LaneConfig(
        lane=lane,
        geom_area_strict_min=40.0,
        geom_area_strict_max=1500.0,
        geom_area_loose_min=15.0,
        geom_area_loose_max=5000.0,
        geom_circ_strict=0.65,
        geom_circ_loose=0.45,
        geom_aspect_strict_min=0.7,
        geom_aspect_strict_max=1.4,
        geom_aspect_loose_min=0.3,
        geom_aspect_loose_max=3.0,
        duplicate_radius_px=15.0,
        duplicate_time_window_sec=5.0,
        localization_spread_threshold=5.0,
        yolo_conf_strict=0.25,
        yolo_conf_loose=0.10,
        weight_geometry=0.40,
        weight_yolo=0.40,
        weight_localization=0.20,
        threshold_verified=0.75
    )


async def save_verification_audit(
    session_id: str,
    shot_id: Optional[str],
    lane_id: int,
    x_raw: float,
    y_raw: float,
    verdict: str,
    confidence_score: float,
    explanation: str,
    signals: dict
):
    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            audit = models.VerificationAudit(
                session_id=session_id,
                shot_id=shot_id,
                lane_id=lane_id,
                x_raw=x_raw,
                y_raw=y_raw,
                verdict=verdict,
                confidence_score=confidence_score,
                explanation=explanation,
                signals_json=signals
            )
            db.add(audit)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save verification audit in background task: {e}")


def build_shot_response(shot, det) -> schemas.ShotResponse:
    """Builds a ShotResponse including scoring fields, from a Shot (+ optional Detection)."""
    return schemas.ShotResponse(
        id=shot.id,
        session_id=shot.session_id,
        image_id=shot.image_id,
        shot_number=shot.shot_number,
        x_raw=shot.x_raw,
        y_raw=shot.y_raw,
        x_calibrated=shot.x_calibrated,
        y_calibrated=shot.y_calibrated,
        diameter_px=shot.diameter_px,
        diameter_mm=shot.diameter_mm,
        confidence=shot.confidence,
        is_valid=shot.is_valid,
        detection_method=shot.detection_method,
        score=shot.score,
        decimal_score=shot.decimal_score,
        nearest_ring_value=shot.nearest_ring_value,
        distance_to_nearest_ring_mm=shot.distance_to_nearest_ring_mm,
        bullseye_id=shot.bullseye_id,
        distance_to_center_mm=shot.distance_to_center_mm,
        boundary_status=shot.boundary_status,
        localization_error_mm=shot.localization_error_mm,
        verdict=shot.verdict,
        verdict_explanation=shot.verdict_explanation,
        confidence_score=shot.confidence_score,
        created_at=shot.created_at,
        detection=schemas.DetectionResponse(
            id=det.id,
            area=det.area,
            circularity=det.circularity,
            solidity=det.solidity,
            aspect_ratio=det.aspect_ratio,
            raw_contour=det.raw_contour,
        ) if det else None,
    )


# --- HTTP Endpoints ---

@app.post(f"{settings.API_V1_STR}/sessions", response_model=schemas.SessionResponse)
async def create_session(session_in: schemas.SessionCreate, db: AsyncSession = Depends(get_db)):
    """
    Creates a new shooting session. If there's an existing 'active' session,
    it marks it as 'completed' first.
    """
    # Deactivate existing sessions
    await db.execute(
        update(models.Session)
        .where(models.Session.status == "active")
        .values(status="completed", updated_at=datetime.utcnow())
    )
    
    # Reset camera service calibration/homography state for the new session
    camera_service.reset_calibration()
    
    # Create new session
    session = models.Session(
        name=session_in.name,
        description=session_in.description,
        status="active",
        target_type=session_in.target_type or "figure_11",
        bullet_caliber=session_in.bullet_caliber or 5.56,
        unit_number=session_in.unit_number,
        session_date=session_in.session_date,
        session_range=session_in.session_range,
        drill_type=session_in.drill_type,
        bullets_per_drill=session_in.bullets_per_drill,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


# --- Target configuration & scoring endpoints ---

@app.get(f"{settings.API_V1_STR}/targets")
async def list_targets():
    """Lists available target templates for the scoring/settings panel."""
    return scoring_service.list_targets()


@app.get(f"{settings.API_V1_STR}/targets/{{target_id}}")
async def get_target(target_id: str):
    """Returns the full JSON definition of a target template."""
    data = scoring_service.get_target_raw(target_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Target configuration not found")
    return data


@app.post(f"{settings.API_V1_STR}/targets")
async def create_target(target_data: dict):
    """Creates/saves a target template JSON (optional base64 preview image)."""
    try:
        return scoring_service.create_target(target_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write target config: {e}")


@app.put(f"{settings.API_V1_STR}/sessions/{{session_id}}/target", response_model=schemas.SessionResponse)
async def update_session_target(
    session_id: str,
    update_in: schemas.SessionTargetUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Sets the scoring target template and/or bullet caliber for a session."""
    result = await db.execute(select(models.Session).where(models.Session.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if update_in.target_type is not None and update_in.target_type != session.target_type:
        session.target_type = update_in.target_type
        # Different template invalidates any previously fitted zone alignment.
        session.geometry_homography_json = None
    if update_in.bullet_caliber is not None:
        session.bullet_caliber = update_in.bullet_caliber
    session.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return session


@app.get(f"{settings.API_V1_STR}/sessions/{{session_id}}/projected-zones")
async def get_projected_zones(session_id: str, db: AsyncSession = Depends(get_db)):
    """Returns the session's target scoring geometry projected into 1000x1000 warped-pixel
    coordinates so the dashboard can overlay it on the warped target view."""
    result = await db.execute(select(models.Session).where(models.Session.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        target = scoring_service.load_target(getattr(session, "target_type", None))
        return scoring_service.compute_projected_zones(
            target, geometry_homography_mm=getattr(session, "geometry_homography_json", None)
        )
    except Exception as e:
        logger.error(f"Failed to compute projected zones: {e}")
        return {"warped_size_px": 1000.0, "target_name": None, "scoring_regions": [], "bullseyes": []}


@app.post(f"{settings.API_V1_STR}/sessions/{{session_id}}/detect-zones")
async def detect_zones(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Target Geometry Alignment: detect the real printed scoring zones/rings in the session's
    warped baseline, fit a template-mm -> observed-mm homography, store it on the session, and
    return the fit diagnostics. Subsequent projected-zones and scoring use this alignment.
    """
    from app.services import zone_geometry

    result = await db.execute(select(models.Session).where(models.Session.id == session_id))
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    baseline_res = await db.execute(
        select(models.Image)
        .where(models.Image.session_id == session_id)
        .where(models.Image.image_type == "baseline")
    )
    baseline_image = baseline_res.scalars().first()
    if not baseline_image:
        raise HTTPException(status_code=400, detail="No baseline captured. Capture 'Before Fire' first.")

    baseline_path = baseline_image.file_path
    if baseline_path.startswith("/static/uploads/") or baseline_path.startswith("static/uploads/"):
        baseline_path = os.path.join(settings.UPLOAD_DIR, os.path.basename(baseline_path))

    target = scoring_service.load_target(getattr(session, "target_type", None))
    fit = zone_geometry.compute_geometry_homography(baseline_path, target)

    # Persist (or clear) the fitted homography for this session.
    session.geometry_homography_json = fit["geometry_homography_mm"] if fit["success"] else None
    session.updated_at = datetime.utcnow()
    await db.commit()

    # Return the diagnostics plus the freshly aligned zone overlay.
    projected = scoring_service.compute_projected_zones(
        target, geometry_homography_mm=session.geometry_homography_json
    )

    # Refresh the calibration/homography diagnostic view with the aligned zones.
    try:
        debug_path = os.path.join(settings.UPLOAD_DIR, f"debug_calibration_{session_id}.jpg")
        scoring_service.generate_calibration_debug_image(
            baseline_path, debug_path, target, geometry_homography_mm=session.geometry_homography_json
        )
    except Exception as e:
        logger.warning(f"Calibration debug refresh failed: {e}")

    await ws_manager.broadcast_to_session(session_id, {
        "event": "ZONES_ALIGNED",
        "data": {"success": fit["success"], "message": fit["message"]}
    })
    return {**fit, "projected_zones": projected, "calibration_debug_url": f"/static/uploads/debug_calibration_{session_id}.jpg?t={int(time.time())}"}


@app.get(f"{settings.API_V1_STR}/sessions/active", response_model=Optional[schemas.SessionResponse])
async def get_active_session(db: AsyncSession = Depends(get_db)):
    """
    Retrieves the currently active session, if any exists.
    """
    result = await db.execute(
        select(models.Session).where(models.Session.status == "active")
    )
    return result.scalars().first()


@app.get(f"{settings.API_V1_STR}/sessions/{{session_id}}/baseline", response_model=Optional[schemas.ImageResponse])
async def get_session_baseline(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieves the baseline image details if it exists.
    """
    result = await db.execute(
        select(models.Image)
        .where(models.Image.session_id == session_id)
        .where(models.Image.image_type == "baseline")
    )
    db_image = result.scalars().first()
    if not db_image:
        return None
    
    filename = os.path.basename(db_image.file_path)
    return schemas.ImageResponse(
        id=db_image.id,
        session_id=db_image.session_id,
        image_type=db_image.image_type,
        file_path=f"/static/uploads/{filename}?t={int(time.time())}",
        metadata_json=db_image.metadata_json,
        created_at=db_image.created_at
    )


@app.post(f"{settings.API_V1_STR}/sessions/{{session_id}}/baseline", response_model=schemas.ImageResponse)
async def upload_baseline(
    session_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads and stores the baseline (reference) image for a shooting session.
    """
    # Verify session exists
    session_result = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )
    session = session_result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Save file to uploads folder
    file_ext = os.path.splitext(file.filename)[1]
    file_name = f"baseline_{session_id}{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, file_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Save reference in database
    image = models.Image(
        session_id=session_id,
        image_type="baseline",
        file_path=file_path,
        metadata_json={"filename": file.filename, "content_type": file.content_type}
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)
    
    # Broadcast session update
    await ws_manager.broadcast_to_session(session_id, {
        "event": "BASELINE_UPLOADED",
        "data": {
            "image_id": image.id,
            "file_path": f"/static/uploads/{file_name}"
        }
    })

    return image


@app.post(f"{settings.API_V1_STR}/sessions/{{session_id}}/detect", response_model=schemas.DetectionPipelineResponse)
async def run_detection(
    session_id: str,
    file: UploadFile = File(...),
    lane: Optional[int] = Query(None),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Uploads the current frame, runs the OpenCV differencing pipeline against the session's
    baseline image, registers new bullet holes in the database, and broadcasts updates over WebSockets.
    """
    # 1. Fetch Session & baseline image
    session_result = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )
    session = session_result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    baseline_result = await db.execute(
        select(models.Image)
        .where(models.Image.session_id == session_id)
        .where(models.Image.image_type == "baseline")
    )
    baseline_image = baseline_result.scalars().first()
    if not baseline_image:
        raise HTTPException(status_code=400, detail="No baseline image uploaded for this session")

    # self-healing for corrupted baseline path
    baseline_path = baseline_image.file_path
    if baseline_path.startswith("/static/uploads/") or baseline_path.startswith("static/uploads/"):
        filename = os.path.basename(baseline_path)
        baseline_path = os.path.join(settings.UPLOAD_DIR, filename)
        baseline_image.file_path = baseline_path

    # 2. Save current frame to disk
    file_ext = os.path.splitext(file.filename)[1]
    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    file_name = f"capture_{session_id}_{timestamp_str}{file_ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, file_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    capture_image = models.Image(
        session_id=session_id,
        image_type="capture",
        file_path=file_path,
        metadata_json={"filename": file.filename}
    )
    db.add(capture_image)
    await db.flush() # Generate ID for capture_image

    # 3. Resolve LaneConfig and query verified existing shots
    lane_config = await resolve_lane_config(db, lane)
    shots_result = await db.execute(
        select(models.Shot).where(models.Shot.session_id == session_id).where(models.Shot.verdict == "VERIFIED")
    )
    verified_shots = shots_result.scalars().all()
    existing_shots = [
        {"x_raw": s.x_raw, "y_raw": s.y_raw, "diameter_px": s.diameter_px} 
        for s in verified_shots
    ]

    # 4. Count current shots to establish shot numbering sequence
    current_count_result = await db.execute(
        select(func.count(models.Shot.id)).where(models.Shot.session_id == session_id)
    )
    shot_sequence_counter = current_count_result.scalar() or 0

    # 5. Run CV Engine Detection
    new_hole_detections, aligned_img = cv_engine.detect_holes(
        baseline_path=baseline_path,
        current_path=capture_image.file_path,
        existing_shots=existing_shots
    )

    new_shots_saved = []

    # 6. Save new shots & detailed metrics
    for detection in new_hole_detections:
        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate=detection,
            session_shots=verified_shots,
            lane_config=lane_config,
            img=aligned_img
        )

        if verdict == "REJECTED":
            if background_tasks:
                background_tasks.add_task(
                    save_verification_audit,
                    session_id,
                    None,
                    lane if lane is not None else 0,
                    detection["x_raw"],
                    detection["y_raw"],
                    verdict,
                    score,
                    explanation,
                    signals
                )
            continue

        shot_sequence_counter += 1
        is_valid = (verdict == "VERIFIED")
        boundary_status = "review_required" if verdict in ["REVIEW", "CONFLICT"] else None
        
        new_shot = models.Shot(
            session_id=session_id,
            image_id=capture_image.id,
            shot_number=shot_sequence_counter,
            x_raw=detection["x_raw"],
            y_raw=detection["y_raw"],
            x_calibrated=None, # Future: ArUco scale
            y_calibrated=None, # Future: ArUco scale
            diameter_px=detection["diameter_px"],
            diameter_mm=None, # Future: scaled mm
            confidence=score,
            is_valid=is_valid,
            detection_method=detection.get("verification_method", "opencv"),
            verdict=verdict,
            verdict_explanation=explanation,
            confidence_score=score,
            boundary_status=boundary_status
        )
        db.add(new_shot)
        await db.flush() # Generate new_shot.id

        if verdict == "VERIFIED":
            # Score the shot against the session's target template (additive; never blocks)
            apply_scoring_to_shot(new_shot, session)

        new_detection_record = models.Detection(
            shot_id=new_shot.id,
            area=detection["area"],
            circularity=detection["circularity"],
            solidity=detection["solidity"],
            aspect_ratio=detection["aspect_ratio"],
            raw_contour=detection["raw_contour"]
        )
        db.add(new_detection_record)
        await db.flush()

        if background_tasks:
            background_tasks.add_task(
                save_verification_audit,
                session_id,
                new_shot.id,
                lane if lane is not None else 0,
                detection["x_raw"],
                detection["y_raw"],
                verdict,
                score,
                explanation,
                signals
            )

        # Keep reference to shape contour in response payload
        new_shots_saved.append((new_shot, new_detection_record))

    await db.commit()

    # 7. Construct response list & WebSocket broadcasts
    response_shots = []
    for shot, det in new_shots_saved:
        shot_data = build_shot_response(shot, det)
        response_shots.append(shot_data)

        # Broadcast each shot to live UI clients immediately
        await ws_manager.broadcast_to_session(session_id, {
            "event": "SHOT_DETECTED",
            "data": shot_data.dict()
        })

    return {
        "shots_detected": response_shots,
        "new_shots_count": len(response_shots),
        "current_frame_url": f"/static/uploads/{file_name}?t={int(time.time())}"
    }


@app.get(f"{settings.API_V1_STR}/sessions/{{session_id}}/shots", response_model=List[schemas.ShotResponse])
async def get_session_shots(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Fetches all shots recorded in the session, sorted by sequence number.
    """
    result = await db.execute(
        select(models.Shot)
        .where(models.Shot.session_id == session_id)
        .options(selectinload(models.Shot.detection))
        .order_by(models.Shot.shot_number.asc())
    )
    return result.scalars().all()


@app.get(f"{settings.API_V1_STR}/sessions/{{session_id}}/statistics", response_model=schemas.StatisticsResponse)
async def get_session_statistics(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Calculates aggregated statistics for the shooting session.
    """
    session_result = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )
    session = session_result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    stats_query = select(
        func.count(models.Shot.id).label("total"),
        func.avg(models.Shot.diameter_px).label("avg_dia"),
        func.max(models.Shot.diameter_px).label("max_dia"),
        func.min(models.Shot.diameter_px).label("min_dia"),
        func.max(models.Shot.created_at).label("last_shot")
    ).where(models.Shot.session_id == session_id).where(models.Shot.is_valid == True)

    result = await db.execute(stats_query)
    row = result.first()

    return schemas.StatisticsResponse(
        total_shots=row.total or 0,
        average_diameter_px=round(row.avg_dia or 0.0, 2),
        largest_diameter_px=round(row.max_dia or 0.0, 2),
        smallest_diameter_px=round(row.min_dia or 0.0, 2),
        last_shot_time=row.last_shot,
        session_status=session.status,
        camera_status="online" if camera_service.is_running else "offline"
    )


@app.get(f"{settings.API_V1_STR}/sessions/{{session_id}}/export")
async def export_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Exports the full session as a downloadable JSON: session metadata + every shot with its
    score, position (px + mm), angle from center, diameter, confidence, detection method,
    boundary status, timestamp, and detection shape metrics.
    """
    import math
    from fastapi.responses import JSONResponse

    session_result = await db.execute(select(models.Session).where(models.Session.id == session_id))
    session = session_result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    shots_result = await db.execute(
        select(models.Shot)
        .where(models.Shot.session_id == session_id)
        .options(selectinload(models.Shot.detection))
        .order_by(models.Shot.shot_number.asc())
    )
    shots = shots_result.scalars().all()

    # Target center in mm (for the shot angle).
    try:
        target = scoring_service.load_target(getattr(session, "target_type", None))
        cx_mm, cy_mm = target.width_mm / 2.0, target.height_mm / 2.0
    except Exception:
        cx_mm, cy_mm = None, None

    valid = [s for s in shots if s.is_valid]
    scored = [s for s in valid if s.score is not None]

    shot_records = []
    for s in shots:
        angle_deg = None
        radial_mm = None
        if cx_mm is not None and s.x_calibrated is not None and s.y_calibrated is not None:
            dx, dy = s.x_calibrated - cx_mm, s.y_calibrated - cy_mm
            angle_deg = round(math.degrees(math.atan2(dy, dx)), 2)
            radial_mm = round(math.hypot(dx, dy), 2)
        det = s.detection
        shot_records.append({
            "shot_number": s.shot_number,
            "score": s.score,
            "decimal_score": s.decimal_score,
            "nearest_ring_value": s.nearest_ring_value,
            "bullseye_id": s.bullseye_id,
            "boundary_status": s.boundary_status,
            "is_valid": s.is_valid,
            "confidence": s.confidence,
            "detection_method": s.detection_method,
            "position": {
                "x_raw_px": s.x_raw, "y_raw_px": s.y_raw,
                "x_mm": s.x_calibrated, "y_mm": s.y_calibrated,
                "angle_deg": angle_deg, "radial_distance_mm": radial_mm,
                "distance_to_center_mm": s.distance_to_center_mm,
                "distance_to_nearest_ring_mm": s.distance_to_nearest_ring_mm,
            },
            "diameter_px": s.diameter_px,
            "diameter_mm": s.diameter_mm,
            "localization_error_mm": s.localization_error_mm,
            "timestamp": s.created_at.isoformat() if s.created_at else None,
            "detection_metrics": {
                "area": det.area, "circularity": det.circularity,
                "solidity": det.solidity, "aspect_ratio": det.aspect_ratio,
            } if det else None,
        })

    total_score = sum((s.decimal_score if s.decimal_score is not None else (s.score or 0)) for s in scored)
    export = {
        "export_version": "1.0",
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "session": {
            "id": session.id, "name": session.name, "description": session.description,
            "status": session.status,
            "target_type": session.target_type, "bullet_caliber_mm": session.bullet_caliber,
            "unit_number": session.unit_number, "session_date": session.session_date,
            "session_range": session.session_range, "drill_type": session.drill_type,
            "bullets_per_drill": session.bullets_per_drill,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "zone_alignment_applied": session.geometry_homography_json is not None,
        },
        "summary": {
            "total_shots": len(shots),
            "valid_shots": len(valid),
            "scored_shots": len(scored),
            "total_score": round(total_score, 1),
            "missed_shots": len([s for s in valid if (s.score or 0) == 0]),
        },
        "shots": shot_records,
    }

    fname = f"session_{(session.name or session.id)[:40].replace(' ', '_')}_{session.id[:8]}.json"
    return JSONResponse(
        content=export,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.delete(f"{settings.API_V1_STR}/sessions/{{session_id}}/shots")
async def clear_session_shots(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Deletes all shot and detection records for the session, allowing a clean slate.
    """
    # Delete all shots (cascades to detections in DB)
    await db.execute(
        models.Shot.__table__.delete().where(models.Shot.session_id == session_id)
    )
    await db.commit()
    
    # Broadcast to websocket that shots were cleared
    await ws_manager.broadcast_to_session(session_id, {
        "event": "SHOTS_CLEARED",
        "data": {}
    })
    return {"success": True}


@app.delete(f"{settings.API_V1_STR}/sessions/{{session_id}}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Deletes the shooting session and cleans up its database records and uploads.
    """
    result = await db.execute(
        select(models.Session).where(models.Session.id == session_id)
    )
    session = result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(session)
    await db.commit()
    return {"success": True}


# --- WebSocket Route ---

@app.websocket("/ws/session/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Handles real-time dashboard subscriptions. Clients connect to this socket
    to receive live telemetry messages when shots are detected.
    """
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            # Maintain connection, handle client pings
            data = await websocket.receive_text()
            # Simple Echo/Heartbeat support
            await websocket.send_text(f"heartbeat: {data}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket, session_id)


# --- Camera & Capture Integration Endpoints ---

def gen_camera_frames():
    while True:
        time.sleep(0.04) # ~25 FPS
        frame = camera_service.get_latest_frame_jpeg()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(placeholder, "AWAITING CAMERA CONNECT...", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            ret, jpeg = cv2.imencode('.jpg', placeholder)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

@app.get("/camera/stream")
@app.get(f"{settings.API_V1_STR}/camera/stream")
async def get_camera_stream():
    return StreamingResponse(gen_camera_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


def gen_tag_frames():
    """Diagnostic stream: live frames with AprilTag/paper-quad detection drawn on top."""
    while True:
        time.sleep(0.06)  # tag detection is heavier than a plain frame -> ~16 FPS
        frame = camera_service.get_tag_feed_jpeg()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(placeholder, "AWAITING CAMERA CONNECT...", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            ret, jpeg = cv2.imencode('.jpg', placeholder)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')


@app.get("/camera/tag_stream")
@app.get(f"{settings.API_V1_STR}/camera/tag_stream")
async def get_tag_stream():
    """Live diagnostic 'Tag Feed' — the camera feed annotated with detected AprilTags and the
    recovered paper quad, so the operator can tell if tag detection (not the camera) is failing."""
    return StreamingResponse(gen_tag_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/camera/tag_debug")
@app.get(f"{settings.API_V1_STR}/camera/tag_debug")
async def get_tag_debug():
    """JSON snapshot of the current tag detection state (count + ids + whether paper locked)."""
    return camera_service.get_tag_debug_info()


@app.post("/camera/connect")
@app.post(f"{settings.API_V1_STR}/camera/connect")
async def camera_connect(source: str = "0", session_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    # Resolve active session or create a new one
    if not session_id:
        result = await db.execute(
            select(models.Session).where(models.Session.status == "active")
        )
        session = result.scalars().first()
        if session:
            session_id = session.id
        else:
            session = models.Session(
                name="Default Session",
                description="Live capture session"
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            session_id = session.id
    
    success = camera_service.start_camera(source)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to connect to camera source: {source}")
    
    camera_service.set_active_session(session_id)
    return {
        "success": True,
        "session_id": session_id,
        "warning": camera_service.connect_warning,
        "resolution": f"{camera_service.actual_width}x{camera_service.actual_height}",
    }


@app.post("/camera/disconnect")
@app.post(f"{settings.API_V1_STR}/camera/disconnect")
async def camera_disconnect():
    camera_service.stop_camera()
    return {"success": True}


# --- Additive controls (camera zoom, AI-verifier config, shot review) ---

@app.post("/camera/zoom")
@app.post(f"{settings.API_V1_STR}/camera/zoom")
async def camera_zoom(factor: float = 1.0):
    """Sets the digital zoom factor applied to the live capture loop (1.0 = no zoom)."""
    camera_service.zoom_factor = max(1.0, min(float(factor), 5.0))
    return {"success": True, "zoom_factor": camera_service.zoom_factor}


@app.get("/config/ai-verifier")
@app.get(f"{settings.API_V1_STR}/config/ai-verifier")
async def get_ai_verifier_config():
    """Returns whether YOLO/SAHI verification is active or bypassed."""
    from app.services.ai_verifier import ai_verifier, YOLO_AVAILABLE
    return {"enabled": bool(ai_verifier.enabled), "yolo_available": YOLO_AVAILABLE,
            "active_model_path": ai_verifier.model_path}


@app.post("/config/ai-verifier")
@app.post(f"{settings.API_V1_STR}/config/ai-verifier")
async def set_ai_verifier_config(enabled: bool = True):
    """Enables/bypasses the YOLO/SAHI verification layer (OpenCV candidates always still run)."""
    from app.services.ai_verifier import ai_verifier
    ai_verifier.enabled = bool(enabled)
    logger.info(f"AI verifier set to {'ENABLED' if ai_verifier.enabled else 'BYPASSED'}")
    return {"success": True, "enabled": ai_verifier.enabled}


@app.get("/shots/review", response_model=List[schemas.ShotResponse])
@app.get(f"{settings.API_V1_STR}/shots/review")
async def get_shots_for_review(db: AsyncSession = Depends(get_db)):
    """Lists shots flagged for manual review (line-break boundary cases) in the active session."""
    result = await db.execute(select(models.Session).where(models.Session.status == "active"))
    session = result.scalars().first()
    if not session:
        return []
    shots_res = await db.execute(
        select(models.Shot)
        .where(models.Shot.session_id == session.id)
        .where(models.Shot.boundary_status == "review_required")
        .options(selectinload(models.Shot.detection))
        .order_by(models.Shot.shot_number.asc())
    )
    return [build_shot_response(s, s.detection) for s in shots_res.scalars().all()]


@app.patch("/shots/{shot_id}", response_model=schemas.ShotResponse)
@app.patch(f"{settings.API_V1_STR}/shots/{{shot_id}}")
async def update_shot(shot_id: str, update_in: schemas.ShotUpdate, db: AsyncSession = Depends(get_db)):
    """Manually update a shot's validity / boundary decision (operator review)."""
    result = await db.execute(
        select(models.Shot).where(models.Shot.id == shot_id).options(selectinload(models.Shot.detection))
    )
    shot = result.scalars().first()
    if not shot:
        raise HTTPException(status_code=404, detail="Shot not found")

    is_approved = (
        update_in.boundary_status is not None
        and update_in.boundary_status != "review_required"
        and update_in.is_valid is not False
    )
    is_excluded = update_in.is_valid is False

    if is_approved:
        if shot.verdict in ["REVIEW", "CONFLICT"]:
            result_session = await db.execute(
                select(models.Session).where(models.Session.id == shot.session_id)
            )
            session = result_session.scalars().first()
            if session:
                apply_scoring_to_shot(shot, session)
            shot.is_valid = True
        else:
            if update_in.is_valid is not None:
                shot.is_valid = update_in.is_valid

        shot.boundary_status = update_in.boundary_status

        # Query and update associated VerificationAudit
        audit_res = await db.execute(
            select(models.VerificationAudit).where(models.VerificationAudit.shot_id == shot.id)
        )
        audit = audit_res.scalars().first()
        if audit:
            audit.adjudication_decision = "ACCEPTED"
            audit.adjudicated_by = "operator"
            audit.adjudicated_at = datetime.utcnow()

    elif is_excluded:
        shot.is_valid = False
        if update_in.boundary_status is not None:
            shot.boundary_status = update_in.boundary_status

        # Query and update associated VerificationAudit
        audit_res = await db.execute(
            select(models.VerificationAudit).where(models.VerificationAudit.shot_id == shot.id)
        )
        audit = audit_res.scalars().first()
        if audit:
            audit.adjudication_decision = "REJECTED"
            audit.adjudicated_by = "operator"
            audit.adjudicated_at = datetime.utcnow()

    else:
        # Standard PATCH updates
        if update_in.is_valid is not None:
            shot.is_valid = update_in.is_valid
        if update_in.boundary_status is not None:
            shot.boundary_status = update_in.boundary_status

    await db.commit()
    await db.refresh(shot)

    shot_response = build_shot_response(shot, shot.detection)
    await ws_manager.broadcast_to_session(shot.session_id, {
        "event": "SHOT_UPDATED",
        "data": shot_response.dict(),
    })
    return shot_response


# --- Camera endpoint aliases (compat for the role-based dashboard UI) ---
# These map the dashboard's camera verb names onto the existing capture pipeline.
# They are thin wrappers — detection/OpenCV/YOLO logic is unchanged.

@app.post(f"{settings.API_V1_STR}/camera/start")
async def camera_start(source: str = "0", session_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await camera_connect(source=source, session_id=session_id, db=db)


@app.post(f"{settings.API_V1_STR}/camera/stop")
async def camera_stop():
    return await camera_disconnect()


@app.get(f"{settings.API_V1_STR}/camera/ping")
async def camera_ping():
    return {
        "online": camera_service.is_running,
        "resolution": f"{camera_service.actual_width}x{camera_service.actual_height}",
    }


@app.post(f"{settings.API_V1_STR}/camera/calibrate")
async def camera_calibrate(session_id: Optional[str] = None, bypass_apriltag: bool = False, db: AsyncSession = Depends(get_db)):
    """Calibrates the target homography for the session (alias used by the dashboard)."""
    if not session_id:
        result = await db.execute(select(models.Session).where(models.Session.status == "active"))
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=400, detail="No active session found.")
        session_id = session.id
    if not camera_service.is_running or camera_service.current_frame is None:
        raise HTTPException(status_code=400, detail="Camera is not connected or streaming.")
    success = camera_service.calibrate_homography(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="Calibration failed — ensure the target and AprilTags are visible.")
    return {"success": True, "method": camera_service.calibration_method}


@app.post(f"{settings.API_V1_STR}/camera/before_fire")
async def camera_before_fire_alias(session_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await capture_before_fire(session_id=session_id, db=db)


@app.post(f"{settings.API_V1_STR}/camera/fire", response_model=schemas.CaptureAfterFireResponse)
async def camera_fire_alias(session_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await capture_after_fire(session_id=session_id, db=db)


@app.post("/capture/before-fire")
@app.post(f"{settings.API_V1_STR}/capture/before-fire")
async def capture_before_fire(session_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    if not session_id:
        result = await db.execute(
            select(models.Session).where(models.Session.status == "active")
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=400, detail="No active session found. Create a session first.")
        session_id = session.id
    else:
        result = await db.execute(
            select(models.Session).where(models.Session.id == session_id)
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

    if not camera_service.is_running or camera_service.current_frame is None:
        raise HTTPException(status_code=400, detail="Camera is not connected or streaming.")

    # Snapshot any existing good calibration so a transient fresh-calibration failure can't
    # clobber it with the center-crop fallback (the cause of the partial "only the down part"
    # baseline). We re-calibrate on Before Fire to track target movement, but a degraded
    # fallback result is rejected in favour of the prior real (AprilTag/contour) homography.
    prev_method = camera_service.calibration_method
    prev_M = camera_service.homography_matrix
    prev_session = camera_service.active_session_id

    success = camera_service.calibrate_homography(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to calibrate target baseline. Ensure target paper is in frame.")

    if (camera_service.calibration_method == "fallback_crop"
            and prev_method in ("apriltag", "paper")
            and prev_session == session_id
            and prev_M is not None):
        with camera_service.lock:
            camera_service.homography_matrix = prev_M
            camera_service.calibration_method = prev_method
        logger.warning(
            "Before Fire: fresh calibration degraded to center-crop; kept prior "
            f"'{prev_method}' homography for session {session_id} instead."
        )

    rectified = camera_service.capture_before_fire(session_id)
    if rectified is None:
        raise HTTPException(status_code=400, detail="Failed to capture reference image before fire.")

    file_path = os.path.join(settings.UPLOAD_DIR, f"baseline_{session_id}.jpg")

    # Update/insert baseline image in DB
    img_result = await db.execute(
        select(models.Image)
        .where(models.Image.session_id == session_id)
        .where(models.Image.image_type == "baseline")
    )
    existing_img = img_result.scalars().first()

    if not existing_img:
        image = models.Image(
            session_id=session_id,
            image_type="baseline",
            file_path=file_path,
            metadata_json={"source": "camera_before_fire"}
        )
        db.add(image)
        await db.commit()
    else:
        existing_img.file_path = file_path
        existing_img.created_at = datetime.utcnow()
        await db.commit()

    # A new baseline already contains every previously-detected hole, so all prior shot
    # records are now stale. Clear them so After Fire only ever reports holes created
    # *after* this baseline (matches the Before Fire -> shoot -> After Fire workflow).
    await db.execute(
        models.Shot.__table__.delete().where(models.Shot.session_id == session_id)
    )
    # The zone alignment is specific to the previous baseline image; invalidate it so the
    # user re-runs "Align Zones" against the new baseline.
    await db.execute(
        update(models.Session).where(models.Session.id == session_id).values(geometry_homography_json=None)
    )
    await db.commit()
    await ws_manager.broadcast_to_session(session_id, {
        "event": "SHOTS_CLEARED",
        "data": {"reason": "new_baseline"}
    })

    # Generate the calibration/homography diagnostic view (AprilTags + template zones) for the new baseline.
    try:
        target = scoring_service.load_target(getattr(session, "target_type", None))
        debug_path = os.path.join(settings.UPLOAD_DIR, f"debug_calibration_{session_id}.jpg")
        scoring_service.generate_calibration_debug_image(file_path, debug_path, target, geometry_homography_mm=None)
    except Exception as e:
        logger.warning(f"Calibration debug generation failed: {e}")

    file_url = f"/static/uploads/baseline_{session_id}.jpg?t={int(time.time())}"

    # Broadcast updated baseline to websocket
    await ws_manager.broadcast_to_session(session_id, {
        "event": "BASELINE_UPLOADED",
        "data": {
            "file_path": file_url,
            "method": camera_service.calibration_method
        }
    })

    return {
        "success": True,
        "method": camera_service.calibration_method,
        "file_path": file_url
    }


@app.post("/capture/after-fire", response_model=schemas.CaptureAfterFireResponse)
@app.post(f"{settings.API_V1_STR}/capture/after-fire", response_model=schemas.CaptureAfterFireResponse)
async def capture_after_fire(
    session_id: Optional[str] = None,
    lane: Optional[int] = Query(None),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    if not session_id:
        result = await db.execute(
            select(models.Session).where(models.Session.status == "active")
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=400, detail="No active session found.")
        session_id = session.id
    else:
        result = await db.execute(
            select(models.Session).where(models.Session.id == session_id)
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

    # Ensure verifier active model is synchronized with the DB state
    await check_and_reload_active_model(db)

    if not camera_service.is_running or camera_service.current_frame is None:
        raise HTTPException(status_code=400, detail="Camera is not connected or streaming.")

    # Fetch baseline image
    baseline_result = await db.execute(
        select(models.Image)
        .where(models.Image.session_id == session_id)
        .where(models.Image.image_type == "baseline")
    )
    baseline_image = baseline_result.scalars().first()
    if not baseline_image:
        raise HTTPException(status_code=400, detail="No baseline image captured. Capture 'Before Fire' first.")

    baseline_path = baseline_image.file_path
    if baseline_path.startswith("/static/uploads/") or baseline_path.startswith("static/uploads/"):
        filename = os.path.basename(baseline_path)
        baseline_path = os.path.join(settings.UPLOAD_DIR, filename)

    # Capture after fire frame
    with camera_service.lock:
        frame = camera_service.current_frame.copy()

    rectified_current = camera_service.rectify_frame(frame)
    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    current_filename = f"capture_{session_id}_{timestamp_str}.jpg"
    current_path = os.path.join(settings.UPLOAD_DIR, current_filename)
    cv2.imwrite(current_path, rectified_current, [int(cv2.IMWRITE_JPEG_QUALITY), 100])

    diff_filename = f"difference_{session_id}_{timestamp_str}.jpg"
    diff_path = os.path.join(settings.UPLOAD_DIR, diff_filename)

    # Register capture image in DB
    capture_image = models.Image(
        session_id=session_id,
        image_type="capture",
        file_path=current_path,
        metadata_json={"type": "capture_after_fire"}
    )
    db.add(capture_image)
    await db.flush()

    # 3. Resolve LaneConfig and query verified existing shots
    lane_config = await resolve_lane_config(db, lane)
    shots_result = await db.execute(
        select(models.Shot).where(models.Shot.session_id == session_id).where(models.Shot.verdict == "VERIFIED")
    )
    verified_shots = shots_result.scalars().all()
    existing_shots = [
        {"x_raw": s.x_raw, "y_raw": s.y_raw, "diameter_px": s.diameter_px}
        for s in verified_shots
    ]

    # Get current sequence count
    current_count_result = await db.execute(
        select(func.count(models.Shot.id)).where(models.Shot.session_id == session_id)
    )
    shot_sequence_counter = current_count_result.scalar() or 0

    # Run detection pipeline and save difference image
    new_hole_detections, aligned_img = cv_engine.detect_holes(
        baseline_path=baseline_path,
        current_path=current_path,
        existing_shots=existing_shots,
        align=True,
        save_diff_path=diff_path
    )

    # Register difference image in DB
    diff_image = models.Image(
        session_id=session_id,
        image_type="difference",
        file_path=diff_path,
        metadata_json={"type": "difference_image"}
    )
    db.add(diff_image)
    await db.flush()

    new_shots_saved = []
    for detection in new_hole_detections:
        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate=detection,
            session_shots=verified_shots,
            lane_config=lane_config,
            img=aligned_img
        )

        if verdict == "REJECTED":
            if background_tasks:
                background_tasks.add_task(
                    save_verification_audit,
                    session_id,
                    None,
                    lane if lane is not None else 0,
                    detection["x_raw"],
                    detection["y_raw"],
                    verdict,
                    score,
                    explanation,
                    signals
                )
            continue

        shot_sequence_counter += 1
        is_valid = (verdict == "VERIFIED")
        boundary_status = "review_required" if verdict in ["REVIEW", "CONFLICT"] else None

        new_shot = models.Shot(
            session_id=session_id,
            image_id=capture_image.id,
            shot_number=shot_sequence_counter,
            x_raw=detection["x_raw"],
            y_raw=detection["y_raw"],
            diameter_px=detection["diameter_px"],
            confidence=score,
            is_valid=is_valid,
            detection_method=detection.get("verification_method", "opencv"),
            verdict=verdict,
            verdict_explanation=explanation,
            confidence_score=score,
            boundary_status=boundary_status
        )
        db.add(new_shot)
        await db.flush()

        if verdict == "VERIFIED":
            # Score the shot against the session's target template (additive; never blocks)
            apply_scoring_to_shot(new_shot, session)

        new_detection_record = models.Detection(
            shot_id=new_shot.id,
            area=detection["area"],
            circularity=detection["circularity"],
            solidity=detection["solidity"],
            aspect_ratio=detection["aspect_ratio"],
            raw_contour=detection["raw_contour"]
        )
        db.add(new_detection_record)
        await db.flush()

        if background_tasks:
            background_tasks.add_task(
                save_verification_audit,
                session_id,
                new_shot.id,
                lane if lane is not None else 0,
                detection["x_raw"],
                detection["y_raw"],
                verdict,
                score,
                explanation,
                signals
            )

        new_shots_saved.append((new_shot, new_detection_record))

    await db.commit()

    response_shots = []
    for shot, det in new_shots_saved:
        shot_data = build_shot_response(shot, det)
        response_shots.append(shot_data)

        # Broadcast each shot to live UI clients immediately
        await ws_manager.broadcast_to_session(session_id, {
            "event": "SHOT_DETECTED",
            "data": shot_data.dict()
        })

    baseline_filename = os.path.basename(baseline_path)
    baseline_url = f"/static/uploads/{baseline_filename}"
    current_url = f"/static/uploads/{current_filename}"
    difference_url = f"/static/uploads/{diff_filename}"

    # Broadcast image details (CURRENT_IMAGE_UPDATED for legacy clients; FRAME_UPDATED for the dashboard)
    await ws_manager.broadcast_to_session(session_id, {
        "event": "CURRENT_IMAGE_UPDATED",
        "data": {
            "baseline_url": baseline_url,
            "current_url": current_url,
            "difference_url": difference_url
        }
    })
    await ws_manager.broadcast_to_session(session_id, {
        "event": "FRAME_UPDATED",
        "data": {"current_frame_url": current_url, "difference_url": difference_url}
    })

    return {
        "baseline_url": baseline_url,
        "current_url": current_url,
        "current_frame_url": current_url,
        "difference_url": difference_url,
        "shots_detected": response_shots,
        "new_shots_count": len(response_shots)
    }


@app.post("/detect", response_model=schemas.DetectionPipelineResponse)
@app.post(f"{settings.API_V1_STR}/detect", response_model=schemas.DetectionPipelineResponse)
async def run_detect(
    session_id: Optional[str] = None,
    lane: Optional[int] = Query(None),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """Runs detection comparing latest baseline image and latest capture image for the session."""
    if not session_id:
        result = await db.execute(
            select(models.Session).where(models.Session.status == "active")
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=400, detail="No active session found.")
        session_id = session.id
    else:
        result = await db.execute(
            select(models.Session).where(models.Session.id == session_id)
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

    # Ensure verifier active model is synchronized with the DB state
    await check_and_reload_active_model(db)

    # Fetch baseline image
    baseline_res = await db.execute(
        select(models.Image)
        .where(models.Image.session_id == session_id)
        .where(models.Image.image_type == "baseline")
    )
    baseline_image = baseline_res.scalars().first()
    if not baseline_image:
        raise HTTPException(status_code=400, detail="No baseline image found.")

    # Fetch latest capture image
    capture_res = await db.execute(
        select(models.Image)
        .where(models.Image.session_id == session_id)
        .where(models.Image.image_type == "capture")
        .order_by(models.Image.created_at.desc())
    )
    capture_image = capture_res.scalars().first()
    if not capture_image:
        raise HTTPException(status_code=400, detail="No capture image found.")

    baseline_path = baseline_image.file_path
    if baseline_path.startswith("/static/uploads/") or baseline_path.startswith("static/uploads/"):
        filename = os.path.basename(baseline_path)
        baseline_path = os.path.join(settings.UPLOAD_DIR, filename)

    current_path = capture_image.file_path
    if current_path.startswith("/static/uploads/") or current_path.startswith("static/uploads/"):
        filename = os.path.basename(current_path)
        current_path = os.path.join(settings.UPLOAD_DIR, filename)

    # 3. Resolve LaneConfig and query verified existing shots
    lane_config = await resolve_lane_config(db, lane)
    shots_res = await db.execute(
        select(models.Shot).where(models.Shot.session_id == session_id).where(models.Shot.verdict == "VERIFIED")
    )
    verified_shots = shots_res.scalars().all()
    existing_shots = [
        {"x_raw": s.x_raw, "y_raw": s.y_raw, "diameter_px": s.diameter_px}
        for s in verified_shots
    ]

    # Get sequence count
    count_res = await db.execute(
        select(func.count(models.Shot.id)).where(models.Shot.session_id == session_id)
    )
    shot_counter = count_res.scalar() or 0

    # Define difference path
    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    diff_filename = f"difference_{session_id}_{timestamp_str}.jpg"
    diff_path = os.path.join(settings.UPLOAD_DIR, diff_filename)

    # Run detection
    new_holes, aligned_img = cv_engine.detect_holes(
        baseline_path=baseline_path,
        current_path=current_path,
        existing_shots=existing_shots,
        align=True,
        save_diff_path=diff_path
    )

    # Register difference image in database
    diff_image = models.Image(
        session_id=session_id,
        image_type="difference",
        file_path=diff_path,
        metadata_json={"type": "difference_image"}
    )
    db.add(diff_image)
    await db.flush()

    new_shots_saved = []
    for hole in new_holes:
        verdict, score, explanation, signals = ConfidenceEngine.evaluate_candidate(
            candidate=hole,
            session_shots=verified_shots,
            lane_config=lane_config,
            img=aligned_img
        )

        if verdict == "REJECTED":
            if background_tasks:
                background_tasks.add_task(
                    save_verification_audit,
                    session_id,
                    None,
                    lane if lane is not None else 0,
                    hole["x_raw"],
                    hole["y_raw"],
                    verdict,
                    score,
                    explanation,
                    signals
                )
            continue

        shot_counter += 1
        is_valid = (verdict == "VERIFIED")
        boundary_status = "review_required" if verdict in ["REVIEW", "CONFLICT"] else None

        new_shot = models.Shot(
            session_id=session_id,
            image_id=capture_image.id,
            shot_number=shot_counter,
            x_raw=hole["x_raw"],
            y_raw=hole["y_raw"],
            diameter_px=hole["diameter_px"],
            confidence=score,
            is_valid=is_valid,
            detection_method=hole.get("verification_method", "opencv"),
            verdict=verdict,
            verdict_explanation=explanation,
            confidence_score=score,
            boundary_status=boundary_status
        )
        db.add(new_shot)
        await db.flush()

        if verdict == "VERIFIED":
            # Score the shot against the session's target template (additive; never blocks)
            apply_scoring_to_shot(new_shot, session)

        new_det = models.Detection(
            shot_id=new_shot.id,
            area=hole["area"],
            circularity=hole["circularity"],
            solidity=hole["solidity"],
            aspect_ratio=hole["aspect_ratio"],
            raw_contour=hole["raw_contour"]
        )
        db.add(new_det)
        await db.flush()

        if background_tasks:
            background_tasks.add_task(
                save_verification_audit,
                session_id,
                new_shot.id,
                lane if lane is not None else 0,
                hole["x_raw"],
                hole["y_raw"],
                verdict,
                score,
                explanation,
                signals
            )

        new_shots_saved.append((new_shot, new_det))

    await db.commit()

    response_shots = []
    for shot, det in new_shots_saved:
        shot_data = build_shot_response(shot, det)
        response_shots.append(shot_data)

        # Broadcast event
        await ws_manager.broadcast_to_session(session_id, {
            "event": "SHOT_DETECTED",
            "data": shot_data.dict()
        })

    baseline_filename = os.path.basename(baseline_path)
    baseline_url = f"/static/uploads/{baseline_filename}"
    current_url = f"/static/uploads/{os.path.basename(current_path)}"
    difference_url = f"/static/uploads/{diff_filename}"

    # Broadcast updated images
    await ws_manager.broadcast_to_session(session_id, {
        "event": "CURRENT_IMAGE_UPDATED",
        "data": {
            "baseline_url": baseline_url,
            "current_url": current_url,
            "difference_url": difference_url
        }
    })

    return {
        "shots_detected": response_shots,
        "new_shots_count": len(response_shots),
        "current_frame_url": current_url
    }


# --- Model Management, Training, & Telemetry Routes ---

@app.post("/train", response_model=schemas.TrainingRunResponse)
@app.post(f"{settings.API_V1_STR}/train", response_model=schemas.TrainingRunResponse)
async def start_training(
    run_in: Optional[schemas.TrainingRunCreate] = None,
    db: AsyncSession = Depends(get_db)
):
    """Launches the YOLOv8s target training pipeline in the background."""
    epochs = run_in.epochs if (run_in and run_in.epochs) else 5
    batch_size = run_in.batch_size if (run_in and run_in.batch_size) else 8
    img_size = run_in.img_size if (run_in and run_in.img_size) else 640
    device_choice = (run_in.device if (run_in and run_in.device) else "auto").lower()

    # Resolve the requested device to a concrete YOLO device string.
    # "0" = first CUDA GPU, "cpu" = processor. "auto"/"gpu" fall back gracefully.
    import torch
    cuda_ok = torch.cuda.is_available()
    if device_choice in ("gpu", "cuda", "0"):
        if not cuda_ok:
            raise HTTPException(
                status_code=400,
                detail="GPU requested but no CUDA-capable GPU is available. Install the CUDA build of PyTorch or choose CPU."
            )
        resolved_device = "0"
    elif device_choice == "cpu":
        resolved_device = "cpu"
    else:  # auto
        resolved_device = "0" if cuda_ok else "cpu"
    logger.info(f"Training device choice '{device_choice}' resolved to '{resolved_device}' (cuda_available={cuda_ok})")

    # 1. Create a running training run database record
    run = models.TrainingRun(
        status="running",
        epochs=epochs,
        batch_size=batch_size,
        img_size=img_size,
        created_at=datetime.utcnow()
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    
    # 2. Resolve paths for the train.py script
    base_dir = os.path.abspath(os.path.dirname(__file__))
    root_dir = os.path.abspath(os.path.join(base_dir, "..", ".."))
    
    import subprocess
    import sys
    
    python_exe = sys.executable
    venv_bin = "Scripts" if os.name == "nt" else "bin"
    venv_exe = "python.exe" if os.name == "nt" else "python"
    local_venv = os.path.join(root_dir, "backend", "venv", venv_bin, venv_exe)
    if os.path.exists(local_venv):
        python_exe = local_venv
        
    train_script = os.path.join(root_dir, "train.py")
    
    cmd = [
        python_exe,
        train_script,
        "--epochs", str(epochs),
        "--batch", str(batch_size),
        "--img-size", str(img_size),
        "--device", resolved_device,
        "--run-id", str(run.id)
    ]
    
    logger.info(f"Spawning training subprocess in background: {' '.join(cmd)}")
    subprocess.Popen(cmd, cwd=root_dir)
    
    return run


@app.get("/shots", response_model=List[schemas.ShotResponse])
@app.get(f"{settings.API_V1_STR}/shots", response_model=List[schemas.ShotResponse])
async def get_active_session_shots(db: AsyncSession = Depends(get_db)):
    """Retrieves all shots for the currently active shooting session."""
    result = await db.execute(
        select(models.Session).where(models.Session.status == "active")
    )
    session = result.scalars().first()
    if not session:
        return []
    return await get_session_shots(session_id=session.id, db=db)


@app.get("/statistics", response_model=schemas.StatisticsResponse)
@app.get(f"{settings.API_V1_STR}/statistics", response_model=schemas.StatisticsResponse)
async def get_active_session_statistics(db: AsyncSession = Depends(get_db)):
    """Retrieves analytics and statistics summary for the active session."""
    result = await db.execute(
        select(models.Session).where(models.Session.status == "active")
    )
    session = result.scalars().first()
    if not session:
        return schemas.StatisticsResponse(
            total_shots=0,
            average_diameter_px=0.0,
            largest_diameter_px=0.0,
            smallest_diameter_px=0.0,
            last_shot_time=None,
            session_status="inactive",
            camera_status="offline"
        )
    return await get_session_statistics(session_id=session.id, db=db)


@app.get("/models", response_model=List[schemas.ModelVersionResponse])
@app.get(f"{settings.API_V1_STR}/models", response_model=List[schemas.ModelVersionResponse])
async def get_all_model_versions(db: AsyncSession = Depends(get_db)):
    """Lists all trained/available model versions."""
    result = await db.execute(
        select(models.ModelVersion).order_by(models.ModelVersion.created_at.desc())
    )
    return result.scalars().all()


def _device_info():
    """Reports which compute devices are available for training/inference."""
    info = {"cuda_available": False, "gpu_name": None, "devices": [{"value": "cpu", "label": "CPU"}]}
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            info["cuda_available"] = True
            info["gpu_name"] = name
            info["devices"].insert(0, {"value": "gpu", "label": f"GPU — {name}"})
    except Exception as e:
        logger.warning(f"Device detection failed: {e}")
    return info


@app.get("/training/devices")
@app.get(f"{settings.API_V1_STR}/training/devices")
async def get_training_devices():
    """Lists compute devices the dashboard can offer for training (CPU always, GPU if available)."""
    return _device_info()


@app.get("/health")
@app.get(f"{settings.API_V1_STR}/health")
async def health_check():
    """System health check showing active configurations, models, and device info."""
    from app.services.ai_verifier import ai_verifier, YOLO_AVAILABLE
    dev = _device_info()
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "camera_status": "online" if camera_service.is_running else "offline",
        "yolo_available": YOLO_AVAILABLE,
        "active_model_path": ai_verifier.model_path if ai_verifier else None,
        "device": ai_verifier.device if ai_verifier else "cpu",
        "cuda_available": dev["cuda_available"],
        "gpu_name": dev["gpu_name"]
    }


@app.get(f"{settings.API_V1_STR}/models/active", response_model=Optional[schemas.ModelVersionResponse])
async def get_active_model_version(db: AsyncSession = Depends(get_db)):
    """Retrieves details of the currently active YOLOv8s model version."""
    # Synchronize the in-memory AI verifier active weights with the database
    await check_and_reload_active_model(db)
    result = await db.execute(
        select(models.ModelVersion).where(models.ModelVersion.is_active == True)
    )
    return result.scalars().first()


@app.get(f"{settings.API_V1_STR}/training/runs", response_model=List[schemas.TrainingRunResponse])
async def get_all_training_runs(db: AsyncSession = Depends(get_db)):
    """Lists all historical and running background training executions."""
    result = await db.execute(
        select(models.TrainingRun).order_by(models.TrainingRun.created_at.desc())
    )
    return result.scalars().all()


@app.get("/training/dataset-stats")
@app.get(f"{settings.API_V1_STR}/training/dataset-stats")
async def get_dataset_stats():
    import json
    import subprocess
    import sys
    from pathlib import Path
    
    base_dir = os.path.abspath(os.path.dirname(__file__))
    root_dir = os.path.abspath(os.path.join(base_dir, "..", ".."))
    report_path = Path(root_dir) / "datasets" / "dataset_report.json"
    
    if not report_path.exists():
        try:
            python_exe = sys.executable
            venv_bin = "Scripts" if os.name == "nt" else "bin"
            venv_exe = "python.exe" if os.name == "nt" else "python"
            local_venv = os.path.join(root_dir, "backend", "venv", venv_bin, venv_exe)
            if os.path.exists(local_venv):
                python_exe = local_venv
            
            pipeline_script = os.path.join(root_dir, "dataset_pipeline.py")
            logger.info(f"Running dataset pipeline in background via subprocess: {python_exe} {pipeline_script}")
            
            res = subprocess.run([python_exe, pipeline_script], cwd=root_dir, capture_output=True, text=True)
            if res.returncode != 0:
                logger.error(f"Dataset pipeline subprocess failed with code {res.returncode}: {res.stderr}")
        except Exception as e:
            logger.error(f"Failed to run dataset pipeline on demand: {e}")
            
    if report_path.exists():
        try:
            with open(report_path, "r") as f:
                return json.load(f)
        except Exception as e:
            return {"error": f"Failed to read dataset report: {e}"}
            
    return {
        "total_raw_images": 0,
        "total_valid_images": 0,
        "split_counts": {"train": 0, "val": 0, "test": 0},
        "class_counts": {"bullet_hole": 0, "paper_tear": 0, "false_positive": 0}
    }


# =====================================================================================
# Unit roster + session-creation wizard endpoints (ported from PILSS).
# These power the role-based dashboard: CSV shooter import, unit rosters, the multi-step
# session creation wizard, and lane assignments. Detection endpoints above are unchanged.
# =====================================================================================
import csv
import io


@app.post(f"{settings.API_V1_STR}/units/upload-csv")
async def upload_unit_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        csv_text = content.decode("latin-1")

    f = io.StringIO(csv_text)
    reader = csv.DictReader(f)

    headers = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []
    unit_col = next((h for h in headers if h == "unit_number"), None)
    id_col = next((h for h in headers if h == "shooter_id"), None)
    name_col = next((h for h in headers if h == "shooter_name"), None)

    if not (unit_col and id_col and name_col):
        f.seek(0)
        reader = csv.reader(f)
        try:
            row_1 = next(reader)
        except StopIteration:
            raise HTTPException(status_code=400, detail="CSV file is empty")

        rows_to_insert = []
        if len(row_1) >= 3 and row_1[0].strip().lower() in ("unit_number", "shooter_id", "shooter_name"):
            pass
        else:
            if len(row_1) >= 3:
                rows_to_insert.append(row_1)

        for row in reader:
            if len(row) >= 3:
                rows_to_insert.append(row)

        parsed_data = []
        for r in rows_to_insert:
            status = r[3].strip() if len(r) > 3 else "Ready"
            parsed_data.append({
                "unit_number": r[0].strip(),
                "shooter_id": r[1].strip(),
                "shooter_name": r[2].strip(),
                "status": status
            })
    else:
        key_map = {
            "unit_number": next(h for h in reader.fieldnames or [] if h.strip().lower() == "unit_number"),
            "shooter_id": next(h for h in reader.fieldnames or [] if h.strip().lower() == "shooter_id"),
            "shooter_name": next(h for h in reader.fieldnames or [] if h.strip().lower() == "shooter_name"),
            "status": next((h for h in reader.fieldnames or [] if h.strip().lower() == "status"), None)
        }

        parsed_data = []
        for row in reader:
            unit_val = row.get(key_map["unit_number"], "").strip()
            id_val = row.get(key_map["shooter_id"], "").strip()
            name_val = row.get(key_map["shooter_name"], "").strip()
            status_val = row.get(key_map["status"], "Ready").strip() if key_map["status"] else "Ready"

            if unit_val and id_val and name_val:
                parsed_data.append({
                    "unit_number": unit_val,
                    "shooter_id": id_val,
                    "shooter_name": name_val,
                    "status": status_val if status_val else "Ready"
                })

    if not parsed_data:
        raise HTTPException(status_code=400, detail="No valid shooter records found in CSV (required columns: unit_number, shooter_id, shooter_name)")

    from sqlalchemy import delete

    units_to_update = list({p["unit_number"] for p in parsed_data})

    for u in units_to_update:
        await db.execute(delete(models.UnitShooter).where(models.UnitShooter.unit_number == u))

    for item in parsed_data:
        db.add(models.UnitShooter(
            unit_number=item["unit_number"],
            shooter_id=item["shooter_id"],
            shooter_name=item["shooter_name"],
            status=item["status"]
        ))

    await db.commit()
    return {"message": f"Successfully imported {len(parsed_data)} shooters across {len(units_to_update)} units", "units": units_to_update}


@app.get(f"{settings.API_V1_STR}/units/{{unit_number}}/shooters")
async def get_unit_shooters(unit_number: str, db: AsyncSession = Depends(get_db)):
    # If there is an active session for this unit, return the lane-assigned roster.
    active_sess_res = await db.execute(
        select(models.Session).where(models.Session.unit_number == unit_number, models.Session.status == "active")
    )
    active_sess = active_sess_res.scalars().first()

    if active_sess:
        la_res = await db.execute(
            select(models.LaneAssignment).where(models.LaneAssignment.session_id == active_sess.id)
        )
        assignments = la_res.scalars().all()

        if assignments:
            shooter_res = await db.execute(
                select(models.UnitShooter).where(models.UnitShooter.unit_number == unit_number)
            )
            shooters = shooter_res.scalars().all()
            shooter_name_map = {s.shooter_id: s.shooter_name for s in shooters}

            result = []
            for la in assignments:
                name = shooter_name_map.get(la.shooter_id, f"Shooter {la.shooter_id}")
                result.append({
                    "id": la.shooter_id,
                    "name": name,
                    "status": "Active",
                    "unit_number": unit_number,
                    "lane": la.lane,
                    "target_id": la.target_id
                })
            return result

    res = await db.execute(select(models.UnitShooter).where(models.UnitShooter.unit_number == unit_number))
    shooters = res.scalars().all()

    if shooters:
        return [
            {"id": s.shooter_id, "name": s.shooter_name, "status": s.status, "unit_number": s.unit_number}
            for s in shooters
        ]

    normalized = unit_number.strip()
    return [
        {"id": f"{normalized}-01", "name": f"Shooter {normalized}-A", "status": "Active", "unit_number": normalized},
        {"id": f"{normalized}-02", "name": f"Shooter {normalized}-B", "status": "Ready", "unit_number": normalized},
        {"id": f"{normalized}-03", "name": f"Shooter {normalized}-C", "status": "Pending", "unit_number": normalized},
    ]


@app.post("/api/sessions", response_model=schemas.NewSessionResponse)
@app.post(f"{settings.API_V1_STR}/sessions/setup", response_model=schemas.NewSessionResponse)
async def create_session_new(session_in: schemas.NewSessionCreate, db: AsyncSession = Depends(get_db)):
    # Resolve targetType (may be a display name or an id) against the available templates.
    target_type_db = None
    for t in scoring_service.list_targets():
        if t["id"].lower() == session_in.targetType.lower() or str(t.get("name", "")).lower() == session_in.targetType.lower():
            target_type_db = t["id"]
            break

    if not target_type_db:
        target_map = {
            "Figure Eleven": "figure_eleven",
            "ISSF 10m Air Rifle": "issf_10m_air_rifle",
            "Real Figure 11": "real_figure_11",
        }
        target_type_db = target_map.get(session_in.targetType) or session_in.targetType.lower().replace(" ", "_")

    try:
        caliber_val = float(session_in.caliber)
    except Exception:
        caliber_val = 5.56

    session = models.Session(
        name=f"Session Unit {session_in.unitNumber}",
        description=f"Drill: {session_in.drillType}, Caliber: {session_in.caliber}",
        status="setup",
        target_type=target_type_db,
        bullet_caliber=caliber_val,
        session_range=str(session_in.range),
        drill_type=session_in.drillType,
        bullets_per_drill=session_in.roundsPerShooter,
        unit_number=session_in.unitNumber,
        session_date=session_in.sessionDate or datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return schemas.NewSessionResponse(sessionId=session.id, unitNumber=session.unit_number)


@app.get("/api/units/{unit_number}/personnel")
@app.get(f"{settings.API_V1_STR}/units/{{unit_number}}/personnel")
async def get_unit_personnel(unit_number: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.UnitShooter).where(models.UnitShooter.unit_number == unit_number))
    shooters = res.scalars().all()

    if shooters:
        return [{"id": s.shooter_id, "name": s.shooter_name} for s in shooters]

    normalized = unit_number.strip()
    names = ["Kumar", "Singh", "Ali", "Khan", "Das", "Sharma", "Patil", "Mehta", "Nair",
             "Verma", "Rao", "Joshi", "Reddy", "Gowda", "Bose", "Sen", "Roy", "Gill"]
    personnel = []
    for i in range(18):
        p_name = f"Pvt {names[i % len(names)]}"
        if i >= len(names):
            p_name += f" {i // len(names) + 1}"
        personnel.append({"id": f"P{i+1:03d}", "name": p_name})
    return personnel


@app.post("/api/sessions/{session_id}/lane-assignments")
@app.post(f"{settings.API_V1_STR}/sessions/{{session_id}}/lane-assignments")
async def save_lane_assignments(
    session_id: str,
    assignments: List[schemas.LaneAssignmentCreateItem],
    db: AsyncSession = Depends(get_db)
):
    session_res = await db.execute(select(models.Session).where(models.Session.id == session_id))
    session = session_res.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from sqlalchemy import delete
    await db.execute(delete(models.LaneAssignment).where(models.LaneAssignment.session_id == session_id))

    for item in assignments:
        db.add(models.LaneAssignment(
            session_id=session_id,
            lane=item.lane,
            target_id=item.targetId,
            shooter_id=item.shooterId
        ))

    await db.commit()
    return {"success": True}


@app.get("/api/sessions/{session_id}/lane-assignments", response_model=List[schemas.LaneAssignmentResponseItem])
@app.get(f"{settings.API_V1_STR}/sessions/{{session_id}}/lane-assignments", response_model=List[schemas.LaneAssignmentResponseItem])
async def get_lane_assignments(session_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(models.LaneAssignment).where(models.LaneAssignment.session_id == session_id))
    assignments = res.scalars().all()

    session_res = await db.execute(select(models.Session).where(models.Session.id == session_id))
    session = session_res.scalars().first()

    shooter_name_map = {}
    if session and session.unit_number:
        shooter_res = await db.execute(
            select(models.UnitShooter).where(models.UnitShooter.unit_number == session.unit_number)
        )
        for s in shooter_res.scalars().all():
            shooter_name_map[s.shooter_id] = s.shooter_name

    result = []
    for la in assignments:
        name = shooter_name_map.get(la.shooter_id) or f"Shooter {la.shooter_id}"
        result.append(schemas.LaneAssignmentResponseItem(
            lane=la.lane, targetId=la.target_id, shooterId=la.shooter_id, shooterName=name
        ))
    return result


@app.post("/api/sessions/{session_id}/start")
@app.post(f"{settings.API_V1_STR}/sessions/{{session_id}}/start")
async def start_session_endpoint(session_id: str, db: AsyncSession = Depends(get_db)):
    session_res = await db.execute(select(models.Session).where(models.Session.id == session_id))
    session = session_res.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    la_res = await db.execute(select(models.LaneAssignment).where(models.LaneAssignment.session_id == session_id))
    if len(la_res.scalars().all()) < 1:
        raise HTTPException(status_code=400, detail="Cannot start session. Minimum 1 assigned shooter required.")

    await db.execute(
        update(models.Session)
        .where(models.Session.status == "active")
        .values(status="completed", updated_at=datetime.utcnow())
    )

    session.status = "active"
    session.updated_at = datetime.utcnow()
    await db.commit()

    return {"success": True, "status": "ACTIVE"}

