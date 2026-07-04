from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any

class SessionBase(BaseModel):
    name: str
    description: Optional[str] = None

class SessionCreate(SessionBase):
    target_type: Optional[str] = "figure_11"
    bullet_caliber: Optional[float] = 5.56
    unit_number: Optional[str] = None
    session_date: Optional[str] = None
    session_range: Optional[str] = None
    drill_type: Optional[str] = None
    bullets_per_drill: Optional[int] = None

class SessionResponse(SessionBase):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime
    target_type: Optional[str] = None
    bullet_caliber: Optional[float] = None
    unit_number: Optional[str] = None
    session_date: Optional[str] = None
    session_range: Optional[str] = None
    drill_type: Optional[str] = None
    bullets_per_drill: Optional[int] = None

    class Config:
        from_attributes = True

class SessionTargetUpdate(BaseModel):
    target_type: Optional[str] = None
    bullet_caliber: Optional[float] = None

class ImageResponse(BaseModel):
    id: str
    session_id: str
    image_type: str
    file_path: str
    metadata_json: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DetectionResponse(BaseModel):
    id: str
    area: float
    circularity: float
    solidity: float
    aspect_ratio: float
    raw_contour: Optional[List[List[int]]] = None

    class Config:
        from_attributes = True

class ShotResponse(BaseModel):
    id: str
    session_id: str
    image_id: Optional[str] = None
    shot_number: int
    x_raw: float
    y_raw: float
    x_calibrated: Optional[float] = None
    y_calibrated: Optional[float] = None
    diameter_px: float
    diameter_mm: Optional[float] = None
    confidence: float
    is_valid: bool
    detection_method: Optional[str] = None
    # --- Scoring fields (populated after detection) ---
    score: Optional[int] = None
    decimal_score: Optional[float] = None
    nearest_ring_value: Optional[int] = None
    distance_to_nearest_ring_mm: Optional[float] = None
    bullseye_id: Optional[int] = None
    distance_to_center_mm: Optional[float] = None
    boundary_status: Optional[str] = None
    localization_error_mm: Optional[float] = None
    verdict: Optional[str] = None
    verdict_explanation: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: datetime
    detection: Optional[DetectionResponse] = None

    class Config:
        from_attributes = True

class ShotUpdate(BaseModel):
    is_valid: Optional[bool] = None
    boundary_status: Optional[str] = None

class StatisticsResponse(BaseModel):
    total_shots: int
    average_diameter_px: float
    largest_diameter_px: float
    smallest_diameter_px: float
    last_shot_time: Optional[datetime] = None
    session_status: str
    camera_status: str

class DetectionPipelineResponse(BaseModel):
    shots_detected: List[ShotResponse]
    new_shots_count: int
    current_frame_url: Optional[str] = None

class ModelVersionResponse(BaseModel):
    id: str
    version_str: str
    model_path: str
    precision: Optional[float] = None
    recall: Optional[float] = None
    map50: Optional[float] = None
    map50_95: Optional[float] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TrainingRunCreate(BaseModel):
    epochs: Optional[int] = 50
    batch_size: Optional[int] = 8
    img_size: Optional[int] = 640
    # "auto" -> use GPU if available else CPU; "gpu"/"0" -> force GPU; "cpu" -> force CPU
    device: Optional[str] = "auto"

class TrainingRunResponse(BaseModel):
    id: str
    model_version_id: Optional[str] = None
    status: str
    epochs: Optional[int] = None
    batch_size: Optional[int] = None
    img_size: Optional[int] = None
    dataset_size: Optional[int] = None
    metrics_json: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CaptureAfterFireResponse(BaseModel):
    baseline_url: Optional[str] = None
    current_url: Optional[str] = None
    current_frame_url: Optional[str] = None  # alias of current_url for the dashboard UI
    difference_url: Optional[str] = None
    shots_detected: List[ShotResponse]
    new_shots_count: int


# --- Unit roster + session-creation wizard (ported from PILSS) ---
class UnitShooterBase(BaseModel):
    unit_number: str
    shooter_id: str
    shooter_name: str
    status: Optional[str] = "Ready"

class UnitShooterCreate(UnitShooterBase):
    pass

class UnitShooterResponse(UnitShooterBase):
    id: str

    class Config:
        from_attributes = True


class NewSessionCreate(BaseModel):
    unitNumber: str
    targetType: str
    range: Any
    drillType: str
    roundsPerShooter: int
    caliber: str
    sessionDate: Optional[str] = None


class NewSessionResponse(BaseModel):
    sessionId: str
    unitNumber: str


class LaneAssignmentCreateItem(BaseModel):
    lane: int
    targetId: str
    shooterId: str


class LaneAssignmentResponseItem(BaseModel):
    lane: int
    targetId: str
    shooterId: str
    shooterName: Optional[str] = None


class LaneConfigBase(BaseModel):
    lane: Optional[int] = None
    geom_area_strict_min: float = 40.0
    geom_area_strict_max: float = 1500.0
    geom_area_loose_min: float = 15.0
    geom_area_loose_max: float = 5000.0
    geom_circ_strict: float = 0.65
    geom_circ_loose: float = 0.45
    geom_aspect_strict_min: float = 0.7
    geom_aspect_strict_max: float = 1.4
    geom_aspect_loose_min: float = 0.3
    geom_aspect_loose_max: float = 3.0
    duplicate_radius_px: float = 15.0
    duplicate_time_window_sec: float = 5.0
    localization_spread_threshold: float = 5.0
    yolo_conf_strict: float = 0.25
    yolo_conf_loose: float = 0.10
    weight_geometry: float = 0.40
    weight_yolo: float = 0.40
    weight_localization: float = 0.20
    threshold_verified: float = 0.75


class LaneConfigCreate(LaneConfigBase):
    pass


class LaneConfigResponse(LaneConfigBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VerificationAuditResponse(BaseModel):
    id: str
    timestamp: datetime
    lane_id: int
    session_id: str
    shot_id: Optional[str] = None
    x_raw: float
    y_raw: float
    signals_json: Any
    verdict: str
    confidence_score: float
    explanation: str
    adjudication_decision: Optional[str] = None
    adjudicated_by: Optional[str] = None
    adjudicated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

