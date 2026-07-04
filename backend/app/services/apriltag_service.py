"""
AprilTag A4 warp service for CXR-AIM platform.
Detects 4+ AprilTags, recovers paper corners, warps to canonical A4 (2100x2970).
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("app.apriltag")

# The native AprilTag library (apriltag.dll) is unsigned. On Windows with Smart App Control
# enforced it can be blocked at load time, so guard the import itself.
try:
    from pupil_apriltags import Detector
    _APRILTAG_IMPORT_OK = True
except Exception as e:  # pragma: no cover - environment dependent
    Detector = None  # type: ignore
    _APRILTAG_IMPORT_OK = False
    logger.warning(f"pupil_apriltags import failed ({e}); AprilTag detection disabled, using fallback calibration.")

A4_W, A4_H = 2100, 2970
TAG_MIN_COUNT = 3

# Per-family detector cache. pupil_apriltags.Detector is family-locked, so we keep one
# instance per family instead of a single global, enabling multi-family fallback.
_DET_CACHE: dict = {}

# None = not yet probed; True/False after the first detector construction attempt. When the OS
# blocks the unsigned apriltag.dll, the first attempt fails and we flip this to False so we never
# retry (which would re-trigger the Windows "Bad Image" dialog on every calibration).
_APRILTAG_AVAILABLE: Optional[bool] = None if _APRILTAG_IMPORT_OK else False

# Candidate AprilTag families, tried in order (ported from PILSS tag detection). The primary
# family is attempted first; the others are only scanned when too few tags are found.
APRILTAG_FALLBACK_FAMILIES = ["tag36h11", "tag25h9", "tag16h5"]


def apriltag_available() -> bool:
    """Whether AprilTag detection is usable in this environment (native lib loadable)."""
    return _APRILTAG_AVAILABLE is not False


def _get_detector(family: str):
    """Return a cached Detector for `family`, or None if the native AprilTag library can't be
    loaded (e.g. Windows Smart App Control blocking the unsigned apriltag.dll). The failure is
    cached so we fall back cleanly instead of re-triggering the OS block on every call."""
    global _APRILTAG_AVAILABLE
    if _APRILTAG_AVAILABLE is False or Detector is None:
        return None
    det = _DET_CACHE.get(family)
    if det is None:
        try:
            det = Detector(families=family)
            _DET_CACHE[family] = det
            _APRILTAG_AVAILABLE = True
        except Exception as e:
            _APRILTAG_AVAILABLE = False
            logger.warning(f"AprilTag native library unavailable ({e}); using contour/center-crop fallback.")
            return None
    return det

TAG_MARGIN_MM = 20.0
MM_PER_PX = 10.0

# --- AprilTag outdoor detection settings ---
ENABLE_CLAHE = True
CLAHE_CLIP_LIMIT = 3.5
AUTO_MARGIN_MIN = 0.15
AUTO_MARGIN_MAX = 0.5
DETECT_AT_NATIVE_RESOLUTION = False
# --- End settings ---


# ---------------------------------------------------------------------------
# Multi-scale AprilTag detection
# ---------------------------------------------------------------------------

def _preprocess(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    blur = cv2.GaussianBlur(eq, (0, 0), 1.0)
    return cv2.addWeighted(eq, 1.5, blur, -0.5, 0)


def _detect_at_scale(gray: np.ndarray, family: str, scale: float,
                     min_area_px: float) -> list:
    if scale != 1.0:
        h, w = gray.shape
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_CUBIC)

    # Apply CLAHE followed by unsharp mask sharpening to enhance tag borders
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    blur = cv2.GaussianBlur(eq, (0, 0), 1.0)
    processed = cv2.addWeighted(eq, 1.5, blur, -0.5, 0)
    det = _get_detector(family)
    if det is None:
        return []
    raw = det.detect(processed, estimate_tag_pose=False, camera_params=None, tag_size=None)

    validated = []
    h_h, w_w = processed.shape[:2]
    for tag in raw:
        if tag.hamming > 1:
            continue
        cx, cy = float(tag.center[0]), float(tag.center[1])
        if cx < 3 or cx > w_w - 3 or cy < 3 or cy > h_h - 3:
            continue
        corners = tag.corners.astype(np.float32)
        area = cv2.contourArea(corners.reshape(-1, 1, 2))
        if area < min_area_px or area > h_h * w_w * 0.5:
            continue

        if scale != 1.0:
            corners /= scale
            cx, cy = cx / scale, cy / scale

        validated.append({
            "id": tag.tag_id,
            "corners": corners,
            "center": np.array([cx, cy], dtype=np.float32),
            "hamming": tag.hamming,
            "decision_margin": getattr(tag, "decision_margin", 0.0),
        })
    return validated


def _detect_tags_single_family(gray: np.ndarray, family: str) -> list:
    scales = [1.0] if DETECT_AT_NATIVE_RESOLUTION else [1.0, 1.5, 2.0, 0.75]
    best_tags = []
    for s in scales:
        tags = _detect_at_scale(gray, family, s, 16)
        if len(tags) > len(best_tags):
            best_tags = tags
            if len(best_tags) >= 4:
                break  # Already found all 4 corners, no need to check other scales
    return best_tags


# ---------------------------------------------------------------------------
# OpenCV ArUco/AprilTag detector (primary).
# Uses the already-loaded OpenCV binaries, so it works even when the unsigned
# pupil_apriltags native DLL is blocked by Windows Smart App Control. It also
# detects both AprilTag and ArUco marker families.
# ---------------------------------------------------------------------------
_OPENCV_AVAILABLE = hasattr(cv2, "aruco") and hasattr(cv2.aruco, "ArucoDetector")

# Marker dictionaries tried in priority order. The system's targets use AprilTag 36h11,
# but we also try the smaller AprilTag families and common ArUco dicts for robustness.
_OPENCV_TAG_DICTS = [d for d in [
    getattr(cv2.aruco, "DICT_APRILTAG_36h11", None),
    getattr(cv2.aruco, "DICT_APRILTAG_25h9", None),
    getattr(cv2.aruco, "DICT_APRILTAG_16h5", None),
    getattr(cv2.aruco, "DICT_5X5_50", None),
    getattr(cv2.aruco, "DICT_4X4_50", None),
    getattr(cv2.aruco, "DICT_6X6_50", None),
] if d is not None] if _OPENCV_AVAILABLE else []

_OPENCV_DETECTORS: dict = {}


def _get_opencv_detector(dict_id: int):
    d = _OPENCV_DETECTORS.get(dict_id)
    if d is None:
        aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
        params = cv2.aruco.DetectorParameters()
        # Sub-pixel corner refinement -> sharper homography -> cleaner rectification.
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        # Widen the adaptive-threshold window range so tags are found across lighting/scale.
        params.adaptiveThreshWinSizeMin = 3
        params.adaptiveThreshWinSizeMax = 33
        params.adaptiveThreshWinSizeStep = 6
        d = cv2.aruco.ArucoDetector(aruco_dict, params)
        _OPENCV_DETECTORS[dict_id] = d
    return d


def _aruco_to_tags(corners, ids) -> list:
    tags = []
    if ids is None:
        return tags
    for i, c in enumerate(corners):
        pts = c.reshape(4, 2).astype(np.float32)
        center = pts.mean(axis=0).astype(np.float32)
        tags.append({
            "id": int(ids[i][0]),
            "corners": pts,
            "center": center,
            "hamming": 0,
            "decision_margin": 1.0,
        })
    return tags


def _marker_area(corners: np.ndarray) -> float:
    return float(cv2.contourArea(corners.reshape(-1, 1, 2).astype(np.float32)))


def _clean_tags(tags: list, frame_area: float) -> list:
    """Remove noise/false-positive detections that wreck paper recovery:
      * drop markers that are tiny relative to the frame (texture/grain false hits), and
      * collapse duplicate IDs (e.g. the spurious second 'ID 24') to a single marker,
        keeping the largest-area instance (the real printed tag).
    """
    min_area = max(120.0, frame_area * 2e-5)
    by_id: dict = {}
    for t in tags:
        area = _marker_area(t["corners"])
        if area < min_area:
            continue
        prev = by_id.get(t["id"])
        if prev is None or area > _marker_area(prev["corners"]):
            by_id[t["id"]] = t
    return list(by_id.values())


def _detect_markers_for_dict(detector, passes: list, frame_area: float) -> list:
    """Run one ArUco/AprilTag dictionary across all image passes (native + CLAHE + 2x upscale)
    and return the best cleaned set of distinct markers found for that single dictionary."""
    dict_best: list = []
    for scale, img in passes:
        try:
            corners, ids, _ = detector.detectMarkers(img)
        except Exception as e:
            logger.debug(f"ArUco detectMarkers failed (scale {scale}): {e}")
            continue
        tags = _aruco_to_tags(corners, ids)
        if scale != 1.0:
            for t in tags:
                t["corners"] = t["corners"] / scale
                t["center"] = t["center"] / scale
        tags = _clean_tags(tags, frame_area)
        if len(tags) > len(dict_best):
            dict_best = tags
        if len(dict_best) >= 4:
            break
    return dict_best


def _detect_tags_opencv(gray: np.ndarray) -> list:
    if not _OPENCV_AVAILABLE:
        return []
    frame_area = float(gray.shape[0] * gray.shape[1])
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    # 2x upscale recovers small/distant tags; corners are rescaled back in _detect_markers_for_dict.
    h, w = gray.shape[:2]
    up = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    passes = [(1.0, gray), (1.0, eq), (2.0, up), (2.0, clahe.apply(up))]

    # Evaluate dictionaries in priority order (AprilTag 36h11 first). Crucially we do NOT merge
    # results across dictionaries — that is exactly what produced the bogus mixed IDs like
    # [0, 24, 24]. A single dictionary that yields >=3 distinct, decently-sized markers is a
    # coherent result and wins outright; lower-priority dicts are only consulted if it doesn't.
    best: list = []
    for dict_id in _OPENCV_TAG_DICTS:
        dict_best = _detect_markers_for_dict(_get_opencv_detector(dict_id), passes, frame_area)
        if len(dict_best) >= 4:
            return dict_best
        if len(dict_best) >= 3:
            best = dict_best  # strong candidate; keep scanning only for a full 4-tag dict
        elif len(dict_best) > len(best):
            best = dict_best
    return best


def detect_tags(gray: np.ndarray, family: str = "tag36h11",
                tag_size_mm: float = 15.0) -> list:
    # Primary: OpenCV ArUco/AprilTag detector (Smart-App-Control-safe, no popup).
    best_tags = _detect_tags_opencv(gray)
    if len(best_tags) >= 4:
        return best_tags

    # Secondary: pupil_apriltags, only if its native library is actually loadable here.
    if apriltag_available():
        pupil = _detect_tags_single_family(gray, family)
        if len(pupil) < 4:
            for fam in APRILTAG_FALLBACK_FAMILIES:
                if fam.lower() == family.lower():
                    continue
                t = _detect_tags_single_family(gray, fam)
                if len(t) > len(pupil):
                    pupil = t
                    if len(pupil) >= 4:
                        break
        if len(pupil) > len(best_tags):
            best_tags = pupil

    return best_tags


# ---------------------------------------------------------------------------
# Paper recovery
# ---------------------------------------------------------------------------

def _sort_tags_by_position(tags: list) -> list:
    centers = [(t["center"][0], t["center"][1], t) for t in tags]
    centers.sort(key=lambda c: c[1])
    top = sorted(centers[:2], key=lambda c: c[0])
    bot = sorted(centers[2:], key=lambda c: c[0])
    return [top[0][2], top[1][2], bot[1][2], bot[0][2]]


_SCORE_FNS = [
    lambda c: c[0] + c[1],   # TL: minimize x+y (top-leftmost)
    lambda c: -c[0] + c[1],  # TR: minimize -x+y (top-rightmost)
    lambda c: -c[0] - c[1],  # BR: minimize -x-y (bottom-rightmost)
    lambda c: c[0] - c[1],   # BL: minimize x-y (bottom-leftmost)
]
_POSITION_NAMES = ["TL", "TR", "BR", "BL"]


def _pick_outward_corner(tag: dict, position_idx: int) -> np.ndarray:
    corners = tag["corners"]
    best = min(range(4), key=lambda j: _SCORE_FNS[position_idx](corners[j]))
    return corners[best]


def _infer_tag_positions(centers_sorted: list) -> tuple:
    """
    Given 3 tags sorted by Y, determine which paper positions they occupy
    and which corner is missing.
    Returns (tag_indices, pos_indices, missing_idx).
    """
    y_gap_12 = centers_sorted[1][1] - centers_sorted[0][1]
    y_gap_23 = centers_sorted[2][1] - centers_sorted[1][1]

    if y_gap_23 > y_gap_12:
        # 2 top (indices 0,1), 1 bottom (index 2)
        top_sorted = sorted(centers_sorted[:2], key=lambda c: c[0])
        bot = centers_sorted[2]
        mid_x = (top_sorted[0][0] + top_sorted[1][0]) / 2
        if bot[0] > mid_x:
            # bottom tag is BR, missing BL
            return [top_sorted[0][2], top_sorted[1][2], bot[2]], [0, 1, 2], 3
        else:
            # bottom tag is BL, missing BR
            return [top_sorted[0][2], top_sorted[1][2], bot[2]], [0, 1, 3], 2
    else:
        # 1 top (index 0), 2 bottom (indices 1,2)
        top = centers_sorted[0]
        bot_sorted = sorted(centers_sorted[1:], key=lambda c: c[0])
        mid_x = (bot_sorted[0][0] + bot_sorted[1][0]) / 2
        if top[0] > mid_x:
            # top tag is TR, missing TL
            return [top[2], bot_sorted[0][2], bot_sorted[1][2]], [1, 3, 2], 0
        else:
            # top tag is TL, missing TR
            return [top[2], bot_sorted[0][2], bot_sorted[1][2]], [0, 3, 2], 1


def _sort_to_tl_tr_br_bl(pts: np.ndarray) -> np.ndarray:
    s = pts[np.argsort(pts[:, 1])]
    top = s[:2][np.argsort(s[:2, 0])]
    bot = s[2:][np.argsort(s[2:, 0])]
    return np.array([top[0], top[1], bot[1], bot[0]], dtype=np.float32)


def _compute_auto_margin(tags: list, paper: np.ndarray) -> float:
    tag_diags = []
    for t in tags:
        c = t["corners"]
        tag_diags.append(float(np.linalg.norm(c[0] - c[2])))
    avg_tag_diag = np.mean(tag_diags)
    center = paper.mean(axis=0)
    avg_corner_dist = float(np.mean([np.linalg.norm(pc - center) for pc in paper]))
    if avg_corner_dist < 1.0:
        return 0.2
    margin = avg_tag_diag / (avg_corner_dist * 2)
    return max(AUTO_MARGIN_MIN, min(AUTO_MARGIN_MAX, margin))


def recover_paper_corners(tags: list, image: np.ndarray,
                          margin_factor: float = 0.0,
                          auto_margin: bool = False) -> Optional[np.ndarray]:
    if len(tags) < 3:
        return None

    if len(tags) >= 4:
        sorted_tags = _sort_tags_by_position(tags)
        paper = np.zeros((4, 2), dtype=np.float32)
        for i in range(4):
            paper[i] = _pick_outward_corner(sorted_tags[i], i)
    else:
        # 3-tag: determine positions via Y-sorting, pick outward corners, compute 4th via parallelogram
        centers = [(t["center"][0], t["center"][1], i) for i, t in enumerate(tags)]
        centers.sort(key=lambda c: c[1])
        tag_indices, pos_indices, missing_idx = _infer_tag_positions(centers)

        three_corners = []
        for tag_i, pos_i in zip(tag_indices, pos_indices):
            three_corners.append(_pick_outward_corner(tags[tag_i], pos_i))
        three_corners = np.array(three_corners, dtype=np.float32)

        # Parallelogram rule for 4th corner: P_missing = opposite_pair[0] + opposite_pair[1] - adjacent
        # Parallelogram rule: opposite corners sum must match: P_TL + P_BR = P_TR + P_BL
        if missing_idx == 0:      # missing TL: P_TL = TR + BL - BR
            fourth = three_corners[0] + three_corners[1] - three_corners[2]
            all_four = np.array([fourth, three_corners[0], three_corners[1], three_corners[2]])
        elif missing_idx == 1:    # missing TR: P_TR = TL + BR - BL
            fourth = three_corners[0] + three_corners[2] - three_corners[1]
            all_four = np.array([three_corners[0], fourth, three_corners[1], three_corners[2]])
        elif missing_idx == 2:    # missing BR: P_BR = TR + BL - TL
            fourth = three_corners[1] + three_corners[2] - three_corners[0]
            all_four = np.array([three_corners[0], three_corners[1], fourth, three_corners[2]])
        else:                     # missing BL: P_BL = TL + BR - TR
            fourth = three_corners[0] + three_corners[2] - three_corners[1]
            all_four = np.array([three_corners[0], three_corners[1], three_corners[2], fourth])
        paper = _sort_to_tl_tr_br_bl(all_four)

    if auto_margin and len(tags) >= 3:
        margin_factor = _compute_auto_margin(tags, paper)

    if margin_factor > 0:
        cx = paper[:, 0].mean()
        cy = paper[:, 1].mean()
        for i in range(4):
            vec = paper[i] - np.array([cx, cy])
            paper[i] = paper[i] + vec * margin_factor

    return paper


# ---------------------------------------------------------------------------
# Warp to A4
# ---------------------------------------------------------------------------

def warp_to_a4(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    src_pts = np.array(corners, dtype=np.float32)
    dst_pts = np.array([
        [0, 0], [A4_W - 1, 0], [A4_W - 1, A4_H - 1], [0, A4_H - 1]
    ], dtype=np.float32)
    H = cv2.getPerspectiveTransform(src_pts, dst_pts)
    return cv2.warpPerspective(image, H, (A4_W, A4_H),
                                flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT,
                                borderValue=255)


# ---------------------------------------------------------------------------
# Live diagnostic overlay ("Live Tag Feed")
# ---------------------------------------------------------------------------

def annotate_frame_with_tags(image: np.ndarray) -> Tuple[np.ndarray, dict]:
    """Draw the detected AprilTag/ArUco markers and the recovered paper quad onto a copy of
    `image`, exactly as the calibration pipeline sees them. Used by the live "Tag Feed" so the
    operator can tell at a glance whether the problem is the tags (none/too few detected) or the
    backend (tags found but paper recovery / warp wrong).

    Returns (annotated_bgr, info) where info has tag_count, tag_ids and paper_ok.
    """
    annotated = image.copy()
    info = {"tag_count": 0, "tag_ids": [], "paper_ok": False}
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        tags = detect_tags(gray)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Tag feed detection failed: {e}")
        tags = []

    info["tag_count"] = len(tags)
    info["tag_ids"] = [int(t["id"]) for t in tags]

    # Per-tag overlay: corner polygon (green), center (orange), id label (yellow).
    for t in tags:
        corners = t["corners"].astype(np.int32)
        cv2.polylines(annotated, [corners.reshape(-1, 1, 2)], True, (0, 255, 0), 2, cv2.LINE_AA)
        cx, cy = int(t["center"][0]), int(t["center"][1])
        cv2.circle(annotated, (cx, cy), 5, (0, 165, 255), -1, cv2.LINE_AA)
        cv2.putText(annotated, f"ID {t['id']}", (cx + 8, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)

    # Recovered paper quad (magenta) — the exact region that will be warped to the baseline.
    if len(tags) >= TAG_MIN_COUNT:
        try:
            paper = recover_paper_corners(tags, image, margin_factor=0.0, auto_margin=True)
            if paper is not None:
                pts = paper.astype(np.int32).reshape(-1, 1, 2)
                cv2.polylines(annotated, [pts], True, (255, 0, 255), 2, cv2.LINE_AA)
                for label, (px, py) in zip(["TL", "TR", "BR", "BL"], paper.astype(int)):
                    cv2.putText(annotated, label, (int(px), int(py)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2, cv2.LINE_AA)
                info["paper_ok"] = True
        except Exception as e:
            logger.debug(f"Tag feed paper recovery failed: {e}")

    # Status banner.
    if info["paper_ok"]:
        status, color = f"TAGS: {len(tags)}  PAPER LOCKED - CALIBRATION READY", (0, 255, 0)
    elif len(tags) > 0:
        status, color = f"TAGS: {len(tags)} (NEED >= {TAG_MIN_COUNT}) - WILL CENTER-CROP", (0, 165, 255)
    else:
        status, color = "NO TAGS DETECTED - WILL CENTER-CROP FALLBACK", (0, 0, 255)

    h, w = annotated.shape[:2]
    cv2.rectangle(annotated, (0, 0), (w, 44), (0, 0, 0), -1)
    cv2.putText(annotated, status, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
    cv2.putText(annotated, "LIVE TAG FEED", (12, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1, cv2.LINE_AA)
    return annotated, info


# ---------------------------------------------------------------------------
# Service class for CXR-AIM integration
# ---------------------------------------------------------------------------

class AprilTagService:
    """
    Service wrapper around AprilTag detection + A4 warp.
    Used by CameraService to replace contour-based paper detection.
    """

    def __init__(self, tag_family: str = "tag36h11", tag_size_mm: float = 15.0,
                 margin: float = 0.2, auto_margin: bool = True, min_tags: int = 3):
        self.tag_family = tag_family
        self.tag_size_mm = tag_size_mm
        self.margin = margin
        self.auto_margin = auto_margin
        self.min_tags = min_tags

    def detect_and_warp(self, image: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], list]:
        """
        Detect AprilTags in image, recover paper corners, and warp to A4.

        Returns:
            (warped_image, paper_corners, detected_tags)
            warped_image is None if < min_tags tags detected.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        tags = detect_tags(gray, self.tag_family, self.tag_size_mm)
        if len(tags) < self.min_tags:
            return None, None, tags

        corners = recover_paper_corners(tags, image, self.margin, self.auto_margin)
        if corners is None:
            return None, None, tags

        warped = warp_to_a4(image, corners)
        return warped, corners, tags

    def get_tag_count(self, image: np.ndarray) -> int:
        """Quick check: how many AprilTags are visible in the image."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        tags = detect_tags(gray, self.tag_family, self.tag_size_mm)
        return len(tags)


apriltag_service = AprilTagService()
