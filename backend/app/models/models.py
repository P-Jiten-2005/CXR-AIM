import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    status = Column(String(50), nullable=False, default="active") # active, completed, paused
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    # Target template + caliber for scoring (ported from PILSS). Nullable/defaulted so
    # existing detection flows are unaffected when scoring is not configured.
    target_type = Column(String(50), nullable=True, default="figure_11")
    bullet_caliber = Column(Float, nullable=True, default=5.56)
    # Fitted template-mm -> observed-mm homography from the zone-alignment engine (per session).
    geometry_homography_json = Column(JSON, nullable=True)
    # Optional session metadata (used by the role-based dashboard UI).
    unit_number = Column(String(100), nullable=True)
    session_date = Column(String(64), nullable=True)
    session_range = Column(String(100), nullable=True)
    drill_type = Column(String(50), nullable=True)
    bullets_per_drill = Column(Integer, nullable=True)

    images = relationship("Image", back_populates="session", cascade="all, delete-orphan")
    shots = relationship("Shot", back_populates="session", cascade="all, delete-orphan")

class Image(Base):
    __tablename__ = "images"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    image_type = Column(String(50), nullable=False) # baseline, capture
    file_path = Column(String(512), nullable=False)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("Session", back_populates="images")
    shots = relationship("Shot", back_populates="image")

class Shot(Base):
    __tablename__ = "shots"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    image_id = Column(String(36), ForeignKey("images.id", ondelete="SET NULL"), nullable=True)
    shot_number = Column(Integer, nullable=False)
    x_raw = Column(Float, nullable=False)
    y_raw = Column(Float, nullable=False)
    x_calibrated = Column(Float, nullable=True)
    y_calibrated = Column(Float, nullable=True)
    diameter_px = Column(Float, nullable=False)
    diameter_mm = Column(Float, nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)
    is_valid = Column(Boolean, default=True, nullable=False)
    detection_method = Column(String(50), nullable=True)
    # --- Scoring fields (ported from PILSS; populated after detection, nullable) ---
    score = Column(Integer, nullable=True)
    decimal_score = Column(Float, nullable=True)
    nearest_ring_value = Column(Integer, nullable=True)
    distance_to_nearest_ring_mm = Column(Float, nullable=True)
    bullseye_id = Column(Integer, nullable=True)
    distance_to_center_mm = Column(Float, nullable=True)
    boundary_status = Column(String(50), nullable=True)
    localization_error_mm = Column(Float, nullable=True, default=0.0)
    verdict = Column(String(50), nullable=True)
    verdict_explanation = Column(String(1024), nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


    session = relationship("Session", back_populates="shots")
    image = relationship("Image", back_populates="shots")
    detection = relationship("Detection", back_populates="shot", uselist=False, cascade="all, delete-orphan")

class Detection(Base):
    __tablename__ = "detections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shot_id = Column(String(36), ForeignKey("shots.id", ondelete="CASCADE"), nullable=False)
    area = Column(Float, nullable=False)
    circularity = Column(Float, nullable=False)
    solidity = Column(Float, nullable=False)
    aspect_ratio = Column(Float, nullable=False)
    raw_contour = Column(JSON, nullable=True) # Point list [[x, y], ...]
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shot = relationship("Shot", back_populates="detection")

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    version_str = Column(String(50), nullable=False, unique=True)
    model_path = Column(String(512), nullable=False)
    precision = Column(Float, nullable=True)
    recall = Column(Float, nullable=True)
    map50 = Column(Float, nullable=True)
    map50_95 = Column(Float, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    training_runs = relationship("TrainingRun", back_populates="model_version")

class TrainingRun(Base):
    __tablename__ = "training_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    model_version_id = Column(String(36), ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="running") # running, completed, failed
    epochs = Column(Integer, nullable=True)
    batch_size = Column(Integer, nullable=True)
    img_size = Column(Integer, nullable=True)
    dataset_size = Column(Integer, nullable=True)
    metrics_json = Column(JSON, nullable=True)
    error_message = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    model_version = relationship("ModelVersion", back_populates="training_runs")

class UnitShooter(Base):
    __tablename__ = "unit_shooters"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    unit_number = Column(String(50), nullable=False)
    shooter_id = Column(String(50), nullable=False)
    shooter_name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="Ready")  # Active, Ready, Pending


class LaneAssignment(Base):
    __tablename__ = "lane_assignments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    lane = Column(Integer, nullable=False)
    target_id = Column(String(50), nullable=False)
    shooter_id = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session = relationship("Session")


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

