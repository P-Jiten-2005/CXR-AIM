"""
Target Geometry Alignment Engine (ported & adapted from PILSS).

Detects the actual printed scoring geometry (rectangular zones and/or concentric rings)
in the rectified 1000x1000 warped baseline image, matches it against the user-defined
digital target template, and fits a homography that maps ideal template-mm coordinates to
the observed real-world-mm coordinates.

This corrects for print scaling, paper stretch, assembly offsets and small perspective
residue so the scoring zones overlay exactly on the real target instead of assuming
"real target == digital template".

Adapted for the current pipeline: the baseline is already warped to WARPED_SIZE_PX, so
detection runs directly on it (no raw-image corners needed).
"""

import math
import logging
from typing import Optional, List, Dict, Any, Tuple

import cv2
import numpy as np

logger = logging.getLogger("app.zone_geometry")

WARPED_SIZE_PX = 1000.0


# ---------------------------------------------------------------------------
# Quad (rectangular zone) detection
# ---------------------------------------------------------------------------

def _order_quad_points(points: np.ndarray) -> np.ndarray:
    """Order a 4-point contour as TL, TR, BR, BL."""
    pts = np.array(points, dtype=np.float32).reshape(4, 2)
    ordered = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)
    ordered[0] = pts[np.argmin(s)]   # top-left
    ordered[2] = pts[np.argmax(s)]   # bottom-right
    ordered[1] = pts[np.argmin(diff)]  # top-right
    ordered[3] = pts[np.argmax(diff)]  # bottom-left
    return ordered


def _dedupe_quad_candidates(candidates: list) -> list:
    """Suppress repeated detections of the same rectangle across threshold sweeps."""
    deduped = []
    for cand in candidates:
        if not any(
            abs(cand["cx"] - e["cx"]) < 12.0 and abs(cand["cy"] - e["cy"]) < 12.0
            and abs(cand["w"] - e["w"]) < 18.0 and abs(cand["h"] - e["h"]) < 18.0
            for e in deduped
        ):
            deduped.append(cand)
    return deduped


def _detect_scoring_zone_quads(gray: np.ndarray) -> list:
    """Detect candidate 4-corner scoring rectangles in a rectified baseline image."""
    candidates = []
    h, w = gray.shape[:2]
    min_area = 400.0
    max_area = 0.95 * float(h * w)

    for th_val in range(50, 221, 5):
        for thresh_mode in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
            _, thresh = cv2.threshold(gray, th_val, 255, thresh_mode)
            contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < min_area or area > max_area:
                    continue
                hull = cv2.convexHull(contour)
                hull_peri = cv2.arcLength(hull, True)
                if hull_peri <= 0:
                    continue
                matched_approx = None
                for eps_coeff in (0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04):
                    approx = cv2.approxPolyDP(hull, eps_coeff * hull_peri, True)
                    if len(approx) == 4:
                        matched_approx = approx
                        break
                if matched_approx is None:
                    continue
                ordered = _order_quad_points(matched_approx.reshape(4, 2))
                TL, TR, BR, BL = ordered[0], ordered[1], ordered[2], ordered[3]
                w_actual = (np.linalg.norm(TR - TL) + np.linalg.norm(BR - BL)) / 2.0
                h_actual = (np.linalg.norm(BL - TL) + np.linalg.norm(BR - TR)) / 2.0
                if h_actual <= 0 or w_actual <= 0:
                    continue
                cx = (TL[0] + TR[0] + BR[0] + BL[0]) / 4.0
                cy = (TL[1] + TR[1] + BR[1] + BL[1]) / 4.0
                if not (0.05 * w <= cx <= 0.95 * w and 0.05 * h <= cy <= 0.95 * h):
                    continue
                aspect_ratio = w_actual / h_actual
                if not (0.3 <= aspect_ratio <= 2.2):
                    continue
                candidates.append({
                    "quad": ordered, "area": float(area),
                    "cx": float(cx), "cy": float(cy),
                    "w": float(w_actual), "h": float(h_actual),
                    "aspect_ratio": float(aspect_ratio),
                })
    return _dedupe_quad_candidates(candidates)


def _match_quad_to_region(cand: dict, region: Any, target_width_mm: float, target_height_mm: float) -> float:
    """Lower score = better match between a detected quad and a theoretical region."""
    th_w = max(region.x_max_mm - region.x_min_mm, 1e-3)
    th_h = max(region.y_max_mm - region.y_min_mm, 1e-3)
    th_cx = (region.x_min_mm + region.x_max_mm) / 2.0
    th_cy = (region.y_min_mm + region.y_max_mm) / 2.0
    th_area = th_w * th_h

    sx = target_width_mm / WARPED_SIZE_PX
    sy = target_height_mm / WARPED_SIZE_PX
    obs_w_mm = cand["w"] * sx
    obs_h_mm = cand["h"] * sy
    obs_area = obs_w_mm * obs_h_mm
    obs_cx_mm = cand["cx"] * sx
    obs_cy_mm = cand["cy"] * sy

    center_dist_mm = float(np.hypot(obs_cx_mm - th_cx, obs_cy_mm - th_cy))
    if center_dist_mm > 15.0:
        return 999.0
    size_score = (abs(obs_w_mm - th_w) / th_w + abs(obs_h_mm - th_h) / th_h + abs(obs_area - th_area) / th_area)
    center_score = center_dist_mm / max(target_width_mm, target_height_mm, 1.0)
    aspect_score = abs(cand["aspect_ratio"] - (th_w / th_h))
    return float((1.5 * size_score) + (1.0 * center_score) + (0.5 * aspect_score))


# ---------------------------------------------------------------------------
# Ellipse (ring) detection
# ---------------------------------------------------------------------------

def _dedupe_ellipse_candidates(candidates: list) -> list:
    deduped = []
    for cand in candidates:
        cx, cy = cand["center"]
        a_min, a_maj = cand["axes"]
        if not any(
            abs(cx - e["center"][0]) < 12.0 and abs(cy - e["center"][1]) < 12.0
            and abs(a_min - e["axes"][0]) < 18.0 and abs(a_maj - e["axes"][1]) < 18.0
            for e in deduped
        ):
            deduped.append(cand)
    return deduped


def _detect_scoring_zone_ellipses(gray: np.ndarray) -> list:
    """Detect candidate circular/elliptical scoring rings in a rectified baseline image."""
    candidates = []
    h, w = gray.shape[:2]
    min_area = 50.0
    max_area = 0.85 * float(h * w)
    for th_val in range(50, 221, 5):
        for thresh_mode in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
            _, thresh = cv2.threshold(gray, th_val, 255, thresh_mode)
            contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                if len(contour) < 5:
                    continue
                area = cv2.contourArea(contour)
                if area < min_area or area > max_area:
                    continue
                try:
                    (cx, cy), (axis_minor, axis_major), angle = cv2.fitEllipse(contour)
                except Exception:
                    continue
                if axis_major <= 0 or axis_minor <= 0:
                    continue
                ellipse_area = np.pi * (axis_minor / 2.0) * (axis_major / 2.0)
                if abs(area - ellipse_area) / ellipse_area > 0.25:
                    continue
                if (axis_minor / axis_major) < 0.55:
                    continue
                candidates.append({
                    "center": (cx, cy), "axes": (axis_minor, axis_major),
                    "angle": angle, "area": area, "aspect_ratio": axis_minor / axis_major,
                })
    return _dedupe_ellipse_candidates(candidates)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_geometry_homography(warped_baseline_path: str, target: Any) -> Dict[str, Any]:
    """
    Detect the real printed scoring geometry on the warped baseline and fit a homography
    mapping template-mm -> observed-mm.

    Returns a dict:
        {
          "success": bool,
          "geometry_homography_mm": 3x3 list | None,
          "matched_regions": int, "matched_rings": int,
          "reprojection_error_mm": float | None,
          "message": str,
        }
    """
    result = {
        "success": False, "geometry_homography_mm": None,
        "matched_regions": 0, "matched_rings": 0,
        "reprojection_error_mm": None, "message": "",
    }
    try:
        img = cv2.imread(warped_baseline_path)
        if img is None:
            result["message"] = "Baseline image could not be read."
            return result

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if gray.shape[0] != int(WARPED_SIZE_PX) or gray.shape[1] != int(WARPED_SIZE_PX):
            gray = cv2.resize(gray, (int(WARPED_SIZE_PX), int(WARPED_SIZE_PX)))

        scale_x = target.width_mm / WARPED_SIZE_PX
        scale_y = target.height_mm / WARPED_SIZE_PX

        template_pts: List[List[float]] = []
        observed_pts: List[List[float]] = []
        rotation_angles: List[float] = []
        matched_regions = 0
        matched_rings = 0

        # Part A: rectangular scoring regions
        regions = getattr(target, "scoring_regions", None) or []
        if regions:
            cands = _detect_scoring_zone_quads(gray)
            pairings = []
            for region in regions:
                for idx, cand in enumerate(cands):
                    score = _match_quad_to_region(cand, region, target.width_mm, target.height_mm)
                    if score <= 2.0:
                        pairings.append((score, region, idx, cand))
            pairings.sort(key=lambda x: x[0])
            used_regions, used_cands = set(), set()
            for score, region, idx, cand in pairings:
                if region.id in used_regions or idx in used_cands:
                    continue
                used_regions.add(region.id)
                used_cands.add(idx)
                matched_regions += 1
                template_quad = np.array([
                    [region.x_min_mm, region.y_min_mm], [region.x_max_mm, region.y_min_mm],
                    [region.x_max_mm, region.y_max_mm], [region.x_min_mm, region.y_max_mm],
                ], dtype=np.float32)
                observed_mm = np.array(cand["quad"], dtype=np.float32) * np.array([scale_x, scale_y], dtype=np.float32)
                template_pts.extend(template_quad.tolist())
                observed_pts.extend(observed_mm.tolist())
                top_edge = observed_mm[1] - observed_mm[0]
                bot_edge = observed_mm[2] - observed_mm[3]
                rotation_angles.append(
                    (math.atan2(float(top_edge[1]), float(top_edge[0])) +
                     math.atan2(float(bot_edge[1]), float(bot_edge[0]))) / 2.0
                )

        # Part B: concentric bullseye rings
        bullseyes = getattr(target, "bullseyes", None) or []
        if bullseyes:
            cands = _detect_scoring_zone_ellipses(gray)
            for bullseye in bullseyes:
                pairings = []
                for ring in bullseye.rings:
                    th_r = ring.outer_radius_mm
                    for c_idx, cand in enumerate(cands):
                        obs_cx_mm = cand["center"][0] * scale_x
                        obs_cy_mm = cand["center"][1] * scale_y
                        obs_r_mm = ((cand["axes"][0] + cand["axes"][1]) / 4.0) * scale_x
                        size_score = abs(obs_r_mm - th_r) / max(th_r, 1e-3)
                        center_score = np.hypot(obs_cx_mm - bullseye.center_x_mm, obs_cy_mm - bullseye.center_y_mm) / max(target.width_mm, target.height_mm)
                        score = size_score + 2.0 * center_score
                        if score <= 0.25:
                            pairings.append((score, ring, c_idx, cand))
                pairings.sort(key=lambda x: x[0])
                used_rings, used_cands = set(), set()
                for score, ring, c_idx, cand in pairings:
                    if ring.value in used_rings or c_idx in used_cands:
                        continue
                    used_rings.add(ring.value)
                    used_cands.add(c_idx)
                    matched_rings += 1
                    theta = np.radians(cand["angle"])
                    a_px = cand["axes"][1] / 2.0
                    b_px = cand["axes"][0] / 2.0
                    cx_px, cy_px = cand["center"]
                    for phi in np.linspace(0, 2 * np.pi, 8, endpoint=False):
                        x_tpl = bullseye.center_x_mm + ring.outer_radius_mm * np.cos(phi)
                        y_tpl = bullseye.center_y_mm + ring.outer_radius_mm * np.sin(phi)
                        t = phi - theta
                        x_obs_px = cx_px + a_px * np.cos(t) * np.cos(theta) - b_px * np.sin(t) * np.sin(theta)
                        y_obs_px = cy_px + a_px * np.cos(t) * np.sin(theta) + b_px * np.sin(t) * np.cos(theta)
                        template_pts.append([x_tpl, y_tpl])
                        observed_pts.append([x_obs_px * scale_x, y_obs_px * scale_y])

        if len(template_pts) < 4:
            result["message"] = "Not enough printed scoring geometry detected to fit an alignment."
            return result

        tpl = np.array(template_pts, dtype=np.float32)
        obs = np.array(observed_pts, dtype=np.float32)

        # Fit a SIMILARITY transform: uniform scale + ROTATION + translation (4 DOF).
        #   [ s*cosθ  -s*sinθ  tx ]
        #   [ s*sinθ   s*cosθ  ty ]
        # A flat printed target (already perspective-warped via AprilTags) differs from the template
        # only by scale, rotation and position — so this is the correct, robust model and it supports
        # the target being placed at ANY angle. We avoid full homography/affine which add spurious
        # shear/perspective when only a couple of concentric zones are matched.
        M, inliers = cv2.estimateAffinePartial2D(tpl, obs, method=cv2.RANSAC, ransacReprojThreshold=5.0)
        if M is None:
            result["message"] = "Geometry fit failed (could not estimate transform)."
            return result

        scale = float(np.hypot(M[0, 0], M[1, 0]))
        angle_deg = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
        if not (0.5 <= scale <= 2.0):
            result["message"] = f"Alignment rejected: implausible scale ({scale:.2f}x)."
            return result

        geometry_h = np.vstack([M, [0.0, 0.0, 1.0]]).astype(np.float64)
        result["scale"] = round(scale, 3)
        result["rotation_deg"] = round(angle_deg, 1)

        reproj = cv2.perspectiveTransform(tpl.reshape(-1, 1, 2), geometry_h).reshape(-1, 2)
        reproj_error = float(np.mean(np.linalg.norm(reproj - obs, axis=1)))
        if not np.isfinite(reproj_error) or reproj_error > 8.0:
            result["message"] = f"Alignment rejected: reprojection error {reproj_error:.2f} mm too high."
            result["reprojection_error_mm"] = reproj_error
            return result

        result.update({
            "success": True,
            "geometry_homography_mm": geometry_h.tolist(),
            "matched_regions": matched_regions,
            "matched_rings": matched_rings,
            "reprojection_error_mm": round(reproj_error, 3),
            "message": (
                f"Aligned to printed geometry ({matched_regions} zones, {matched_rings} rings) — "
                f"scale {result.get('scale', 1.0):.2f}x, rotation {result.get('rotation_deg', 0.0):.1f}°, "
                f"error {reproj_error:.2f} mm."
            ),
        })
        logger.info(result["message"])
        return result
    except Exception as e:
        logger.error(f"compute_geometry_homography failed: {e}")
        result["message"] = f"Zone alignment error: {e}"
        return result
