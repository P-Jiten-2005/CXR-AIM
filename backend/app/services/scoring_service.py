"""
Scoring service for CXR-AIM.

Bridges the current warp-then-detect pipeline (shots detected in a 1000x1000 warped
target image) to the ported PILSS scoring engine. Detection is untouched: this layer
runs *after* a shot is registered, converting its warped-pixel coordinates to target
millimetres by linear scaling, then computing the official score.

The warp maps the physical target sheet (width_mm x height_mm) onto the full
WARPED_SIZE_PX square, so the mapping is a simple per-axis linear scale.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional

import cv2
import numpy as np

from app.scoring.target_definition import TargetDefinition
from app.scoring.scoring_engine import ScoringEngine
from app.scoring.boundary_verification import BoundaryVerificationEngine

logger = logging.getLogger("app.scoring_service")

# Current pipeline warps every capture to a 1000x1000 canvas.
WARPED_SIZE_PX = 1000.0

# configs/targets lives at <backend_root>/configs/targets
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGETS_DIR = os.path.join(_BACKEND_ROOT, "configs", "targets")
DEFAULT_TARGET = "figure_11"

_scoring_engine = ScoringEngine()
_boundary_engine = BoundaryVerificationEngine()

# Small cache so repeated scoring within one capture doesn't re-read disk.
_target_cache: Dict[str, TargetDefinition] = {}


def list_targets() -> List[Dict[str, Any]]:
    """Lists available target templates (summary form) for the dashboard selector."""
    targets = []
    if not os.path.isdir(TARGETS_DIR):
        return targets
    for fname in sorted(os.listdir(TARGETS_DIR)):
        if not fname.endswith(".json"):
            continue
        target_id = fname[:-5]
        try:
            t = TargetDefinition.load_from_json(os.path.join(TARGETS_DIR, fname))
            targets.append({
                "id": target_id,
                "name": t.name,
                "width_mm": t.width_mm,
                "height_mm": t.height_mm,
                "bullet_compatibility": t.bullet_compatibility,
                "decimal_scoring_supported": t.decimal_scoring_supported,
                "has_rings": bool(t.bullseyes),
                "has_zones": bool(t.scoring_regions),
                "preview_url": t.preview_url,
            })
        except Exception as e:
            logger.error(f"Failed to load target config {fname}: {e}")
    return targets


def get_target_raw(target_id: str) -> Optional[Dict[str, Any]]:
    """Returns the raw JSON dict of a target config, or None if missing."""
    path = os.path.join(TARGETS_DIR, f"{target_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def load_target(target_type: Optional[str]) -> TargetDefinition:
    """Loads a TargetDefinition by id, falling back to the default template."""
    target_type = target_type or DEFAULT_TARGET
    if target_type in _target_cache:
        return _target_cache[target_type]
    path = os.path.join(TARGETS_DIR, f"{target_type}.json")
    if not os.path.exists(path):
        logger.warning(f"Target '{target_type}' not found; falling back to '{DEFAULT_TARGET}'.")
        path = os.path.join(TARGETS_DIR, f"{DEFAULT_TARGET}.json")
    target = TargetDefinition.load_from_json(path)
    _target_cache[target_type] = target
    return target


def create_target(data: Dict[str, Any]) -> Dict[str, Any]:
    """Saves a new/updated target config JSON (optionally with a base64 preview image)."""
    import re
    import base64
    from app.core.config import settings

    name = data.get("name")
    if not name:
        raise ValueError("Target name is required")

    target_id = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_")) or f"target_{int(__import__('time').time())}"
    os.makedirs(TARGETS_DIR, exist_ok=True)

    preview_url = None
    b64 = data.get("preview_image_base64")
    if b64:
        try:
            if "," in b64:
                b64 = b64.split(",")[1]
            img_bytes = base64.b64decode(b64)
            fname = f"target_preview_{target_id}.png"
            with open(os.path.join(settings.UPLOAD_DIR, fname), "wb") as f:
                f.write(img_bytes)
            preview_url = f"/static/uploads/{fname}"
        except Exception as e:
            logger.error(f"Failed to save target preview image: {e}")

    config = {k: v for k, v in data.items() if k != "preview_image_base64"}
    config["preview_url"] = preview_url
    with open(os.path.join(TARGETS_DIR, f"{target_id}.json"), "w") as f:
        json.dump(config, f, indent=2)

    _target_cache.pop(target_id, None)
    return {"success": True, "id": target_id, "name": name, "preview_url": preview_url}


def warped_to_mm(x_w: float, y_w: float, target: TargetDefinition) -> tuple:
    """Linear map from 1000x1000 warped pixels to target-space millimetres."""
    x_mm = (x_w / WARPED_SIZE_PX) * target.width_mm
    y_mm = (y_w / WARPED_SIZE_PX) * target.height_mm
    return x_mm, y_mm


def _apply_homography(h_mm: Optional[list], x_mm: float, y_mm: float) -> tuple:
    """Apply a 3x3 homography (as nested list) to an (x_mm, y_mm) point. Identity if None."""
    if not h_mm:
        return x_mm, y_mm
    try:
        H = np.array(h_mm, dtype=np.float32)
        pt = np.array([[[x_mm, y_mm]]], dtype=np.float32)
        out = cv2.perspectiveTransform(pt, H)
        return float(out[0][0][0]), float(out[0][0][1])
    except Exception:
        return x_mm, y_mm


def _inverse_homography(h_mm: Optional[list]):
    if not h_mm:
        return None
    try:
        return np.linalg.inv(np.array(h_mm, dtype=np.float32)).tolist()
    except Exception:
        return None


def score_warped_shot(
    x_warped: float,
    y_warped: float,
    diameter_px_warped: float,
    target: TargetDefinition,
    bullet_caliber_mm: float = 5.56,
    geometry_homography_mm: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Scores a single shot given its coordinates in the 1000x1000 warped image.
    Returns a dict of scoring fields ready to persist on a Shot row. Never raises;
    on any failure returns zeros so detection/registration is never blocked.

    If geometry_homography_mm (template-mm -> observed-mm) is supplied, the observed
    impact is mapped back into template space (via the inverse) before scoring, so the
    score reflects the real printed geometry rather than the ideal template.
    """
    try:
        # Observed mm from the warped pixel (linear).
        obs_x_mm, obs_y_mm = warped_to_mm(x_warped, y_warped, target)
        # Map observed -> template space for scoring against the template rings/regions.
        inv = _inverse_homography(geometry_homography_mm)
        x_mm, y_mm = _apply_homography(inv, obs_x_mm, obs_y_mm) if inv else (obs_x_mm, obs_y_mm)

        # Average per-axis scale to convert the warped-pixel diameter to mm.
        x_scale = target.width_mm / WARPED_SIZE_PX
        y_scale = target.height_mm / WARPED_SIZE_PX
        diameter_mm = diameter_px_warped * (x_scale + y_scale) / 2.0
        bullet_radius_mm = max(bullet_caliber_mm, 0.1) / 2.0

        scores = _scoring_engine.score_shot(
            impact_x_mm=x_mm,
            impact_y_mm=y_mm,
            bullet_radius_mm=bullet_radius_mm,
            target=target,
        )

        # Localization uncertainty ~ half a warped pixel in mm (used for line-break confidence).
        localization_error_mm = max(x_scale, y_scale) * 0.5
        boundary = _boundary_engine.verify_boundary(
            distance_to_nearest_ring_mm=scores["distance_to_nearest_ring_mm"],
            localization_error_mm=localization_error_mm if localization_error_mm > 0 else 0.3,
        )

        return {
            "x_calibrated": float(obs_x_mm),
            "y_calibrated": float(obs_y_mm),
            "diameter_mm": float(diameter_mm),
            "score": scores["score"],
            "decimal_score": scores["decimal_score"],
            "nearest_ring_value": scores["nearest_ring_value"],
            "distance_to_nearest_ring_mm": scores["distance_to_nearest_ring_mm"],
            "bullseye_id": scores["bullseye_id"],
            "distance_to_center_mm": scores["distance_to_center_mm"],
            "boundary_status": boundary["status"],
            "localization_error_mm": float(localization_error_mm),
        }
    except Exception as e:
        logger.error(f"Scoring failed for shot at ({x_warped:.1f},{y_warped:.1f}): {e}")
        return {
            "x_calibrated": None, "y_calibrated": None, "diameter_mm": None,
            "score": None, "decimal_score": None, "nearest_ring_value": None,
            "distance_to_nearest_ring_mm": None, "bullseye_id": None,
            "distance_to_center_mm": None, "boundary_status": None,
            "localization_error_mm": 0.0,
        }


def generate_calibration_debug_image(
    warped_baseline_path: str,
    output_path: str,
    target: TargetDefinition,
    geometry_homography_mm: Optional[list] = None,
) -> bool:
    """
    Renders a 'Calibration / Homography' diagnostic image: the warped 1000x1000 baseline with
    detected AprilTags marked and the (optionally geometry-aligned) scoring zones drawn on top.
    Lets the operator visually confirm the homography + zone alignment. Returns True on success.
    """
    try:
        img = cv2.imread(warped_baseline_path)
        if img is None:
            return False
        if img.shape[0] != int(WARPED_SIZE_PX) or img.shape[1] != int(WARPED_SIZE_PX):
            img = cv2.resize(img, (int(WARPED_SIZE_PX), int(WARPED_SIZE_PX)))

        # AprilTag detections (proves the calibration/warp)
        try:
            from app.services.apriltag_service import detect_tags
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            for tag in detect_tags(gray):
                quad = tag["corners"].astype(np.int32).reshape((-1, 1, 2))
                cv2.polylines(img, [quad], True, (255, 255, 0), 2)
                cx, cy = int(tag["center"][0]), int(tag["center"][1])
                cv2.putText(img, f"ID {tag['id']}", (cx - 18, cy - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
        except Exception as e:
            logger.warning(f"AprilTag overlay for calibration debug failed: {e}")

        # Aligned scoring zones (geometry homography applied if present)
        zones = compute_projected_zones(target, geometry_homography_mm=geometry_homography_mm)
        for region in zones["scoring_regions"]:
            pts = np.array(region["polygon"], dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(img, [pts], True, (180, 105, 255), 2)
            lx, ly = int(region["polygon"][0][0]), int(region["polygon"][0][1])
            cv2.putText(img, f"{region.get('name') or 'Zone'} ({region['value']})", (lx + 4, ly + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 105, 255), 1, cv2.LINE_AA)
        for b in zones["bullseyes"]:
            for ring in b["rings"]:
                pts = np.array(ring["polygon"], dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(img, [pts], True, (100, 200, 100), 1)
            cx, cy = int(b["center_pixel"][0]), int(b["center_pixel"][1])
            cv2.circle(img, (cx, cy), 3, (0, 0, 255), -1)

        tag_status = "ALIGNED TO PRINT" if geometry_homography_mm else "TEMPLATE (not aligned)"
        cv2.putText(img, f"CALIBRATION / HOMOGRAPHY  -  zones: {tag_status}", (12, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2, cv2.LINE_AA)

        cv2.imwrite(output_path, img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        return True
    except Exception as e:
        logger.error(f"generate_calibration_debug_image failed: {e}")
        return False


def compute_projected_zones(target: TargetDefinition, geometry_homography_mm: Optional[list] = None) -> Dict[str, Any]:
    """
    Projects the target's scoring geometry into 1000x1000 warped-pixel coordinates so the
    dashboard can overlay it directly on the warped baseline/overlay canvas.

    If geometry_homography_mm (template-mm -> observed-mm) is supplied, each template point is
    first mapped through it, so the overlaid zones land exactly on the real printed geometry
    (corrected for print scale, stretch and offset) rather than the ideal template position.
    """
    def mm_to_warped(x_mm: float, y_mm: float):
        # template-mm -> observed-mm (if aligned) -> warped px
        ox, oy = _apply_homography(geometry_homography_mm, x_mm, y_mm)
        return [
            (ox / target.width_mm) * WARPED_SIZE_PX,
            (oy / target.height_mm) * WARPED_SIZE_PX,
        ]

    scoring_regions = []
    for region in target.scoring_regions:
        scoring_regions.append({
            "id": region.id,
            "name": region.name,
            "value": region.value,
            "polygon": [
                mm_to_warped(region.x_min_mm, region.y_min_mm),
                mm_to_warped(region.x_max_mm, region.y_min_mm),
                mm_to_warped(region.x_max_mm, region.y_max_mm),
                mm_to_warped(region.x_min_mm, region.y_max_mm),
            ],
        })

    bullseyes = []
    for b in target.bullseyes:
        rings = []
        for ring in b.rings:
            theta = np.linspace(0, 2 * np.pi, 48)
            polygon = [
                mm_to_warped(b.center_x_mm + ring.outer_radius_mm * np.cos(t),
                             b.center_y_mm + ring.outer_radius_mm * np.sin(t))
                for t in theta
            ]
            rings.append({"value": ring.value, "outer_radius_mm": ring.outer_radius_mm, "polygon": polygon})
        bullseyes.append({
            "id": b.id,
            "center_pixel": mm_to_warped(b.center_x_mm, b.center_y_mm),
            "rings": rings,
        })

    return {
        "warped_size_px": WARPED_SIZE_PX,
        "target_name": target.name,
        "scoring_regions": scoring_regions,
        "bullseyes": bullseyes,
    }
