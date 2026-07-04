"""
Coordinate Transformation Engine for PILSS.
Translates coordinates between raw pixel space, warped pixel space, and target-space mm.
Supports the research comparison between Warp-then-Detect (Approach A) and Detect-then-Transform (Approach B).
"""

import cv2
import numpy as np
from typing import Tuple, Union, Optional


class CoordinateTransformer:
    """Handles 2D projective transformations and coordinate scaling for scoring."""

    def __init__(
        self,
        corners_pixel: np.ndarray,
        target_width_mm: float,
        target_height_mm: float,
        warped_width_px: float = 1000.0,
        warped_height_px: float = 1000.0,
        corners_warped: Optional[np.ndarray] = None,
        rotation_angle_rad: float = 0.0,
        geometry_homography_mm: Optional[list] = None
    ):
        """
        Initializes the coordinate transformer.

        Args:
            corners_pixel: 4x2 array of raw pixel corners ordered: Top-Left, Top-Right, Bottom-Right, Bottom-Left.
            target_width_mm: Real-world width of target paper sheet in mm.
            target_height_mm: Real-world height of target paper sheet in mm.
            warped_width_px: Resolution width of the warped target image in pixels.
            warped_height_px: Resolution height of the warped target image in pixels.
            corners_warped: Optional 4x2 array of corners in warped pixel space.
            rotation_angle_rad: Rotation angle of target print on sheet in radians.
            geometry_homography_mm: Optional 3x3 homography mapping template mm to physical mm.
        """
        self.corners_pixel = np.array(corners_pixel, dtype=np.float32)
        self.target_width_mm = target_width_mm
        self.target_height_mm = target_height_mm
        self.warped_width_px = warped_width_px
        self.warped_height_px = warped_height_px
        self.rotation_angle_rad = rotation_angle_rad

        # Parse geometry homography matrix if provided
        self.geometry_homography_mm = None
        self.geometry_homography_mm_inv = None
        if geometry_homography_mm is not None:
            geom = np.array(geometry_homography_mm, dtype=np.float32)
            if geom.shape == (3, 3):
                self.geometry_homography_mm = geom
                try:
                    self.geometry_homography_mm_inv = np.linalg.inv(geom)
                except np.linalg.LinAlgError:
                    self.geometry_homography_mm = None
                    self.geometry_homography_mm_inv = None

        # Standardized target corners in mm
        self.corners_mm = np.array([
            [0.0, 0.0],
            [target_width_mm, 0.0],
            [target_width_mm, target_height_mm],
            [0.0, target_height_mm]
        ], dtype=np.float32)

        # Standardized target corners in warped pixel space
        if corners_warped is not None:
            self.corners_warped = np.array(corners_warped, dtype=np.float32)
        else:
            self.corners_warped = np.array([
                [0.0, 0.0],
                [warped_width_px - 1, 0.0],
                [warped_width_px - 1, warped_height_px - 1],
                [0.0, warped_height_px - 1]
            ], dtype=np.float32)

        # Compute basic raw pixel <-> mm homographies (uncorrected)
        self.H_pixel_to_mm_raw = cv2.getPerspectiveTransform(self.corners_pixel, self.corners_mm)
        self.H_mm_to_pixel_raw = cv2.getPerspectiveTransform(self.corners_mm, self.corners_pixel)

        # 1. Raw pixels <-> mm (Approach B)
        self.H_pixel_to_mm = cv2.getPerspectiveTransform(self.corners_pixel, self.corners_mm)
        self.H_mm_to_pixel = cv2.getPerspectiveTransform(self.corners_mm, self.corners_pixel)

        # 2. Raw pixels <-> Warped pixels
        self.H_pixel_to_warped = cv2.getPerspectiveTransform(self.corners_pixel, self.corners_warped)
        self.H_warped_to_pixel = cv2.getPerspectiveTransform(self.corners_warped, self.corners_pixel)

    def raw_pixel_to_target_mm(self, x_px: float, y_px: float) -> Tuple[float, float]:
        """
        Directly projects a raw pixel coordinate to real-world target mm (Approach B).
        Bypasses any intermediate image warping step.
        """
        point = np.array([[[x_px, y_px]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.H_pixel_to_mm)
        x_mm = float(transformed[0][0][0])
        y_mm = float(transformed[0][0][1])
        
        if self.geometry_homography_mm_inv is not None:
            pt = np.array([[[x_mm, y_mm]]], dtype=np.float32)
            trans = cv2.perspectiveTransform(pt, self.geometry_homography_mm_inv)
            return float(trans[0][0][0]), float(trans[0][0][1])
        elif self.rotation_angle_rad != 0.0:
            cx = self.target_width_mm / 2.0
            cy = self.target_height_mm / 2.0
            dx = x_mm - cx
            dy = y_mm - cy
            cos_a = np.cos(-self.rotation_angle_rad)
            sin_a = np.sin(-self.rotation_angle_rad)
            return float(cx + dx * cos_a - dy * sin_a), float(cy + dx * sin_a + dy * cos_a)
        return x_mm, y_mm

    def target_mm_to_raw_pixel(self, x_mm: float, y_mm: float) -> Tuple[float, float]:
        """Maps target mm back to raw pixel space."""
        if self.geometry_homography_mm is not None:
            pt = np.array([[[x_mm, y_mm]]], dtype=np.float32)
            trans = cv2.perspectiveTransform(pt, self.geometry_homography_mm)
            x_mm = float(trans[0][0][0])
            y_mm = float(trans[0][0][1])
        elif self.rotation_angle_rad != 0.0:
            cx = self.target_width_mm / 2.0
            cy = self.target_height_mm / 2.0
            dx = x_mm - cx
            dy = y_mm - cy
            cos_a = np.cos(self.rotation_angle_rad)
            sin_a = np.sin(self.rotation_angle_rad)
            x_mm = float(cx + dx * cos_a - dy * sin_a)
            y_mm = float(cy + dx * sin_a + dy * cos_a)

        point = np.array([[[x_mm, y_mm]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.H_mm_to_pixel)
        return float(transformed[0][0][0]), float(transformed[0][0][1])

    def raw_pixel_to_warped_pixel(self, x_px: float, y_px: float) -> Tuple[float, float]:
        """Maps raw pixel space to warped pixel space."""
        point = np.array([[[x_px, y_px]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.H_pixel_to_warped)
        return float(transformed[0][0][0]), float(transformed[0][0][1])

    def warped_pixel_to_raw_pixel(self, x_w_px: float, y_w_px: float) -> Tuple[float, float]:
        """Maps warped pixel space back to raw pixel space."""
        point = np.array([[[x_w_px, y_w_px]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.H_warped_to_pixel)
        return float(transformed[0][0][0]), float(transformed[0][0][1])

    def warped_pixel_to_target_mm(self, x_w_px: float, y_w_px: float) -> Tuple[float, float]:
        """
        Transforms warped pixel coordinate to real-world target mm (Approach A).
        Uses simple linear scaling, assuming the warped image matches the target aspect ratio.
        """
        x_mm = x_w_px * (self.target_width_mm / self.warped_width_px)
        y_mm = y_w_px * (self.target_height_mm / self.warped_height_px)
        
        if self.geometry_homography_mm_inv is not None:
            pt = np.array([[[x_mm, y_mm]]], dtype=np.float32)
            trans = cv2.perspectiveTransform(pt, self.geometry_homography_mm_inv)
            return float(trans[0][0][0]), float(trans[0][0][1])
        elif self.rotation_angle_rad != 0.0:
            cx = self.target_width_mm / 2.0
            cy = self.target_height_mm / 2.0
            dx = x_mm - cx
            dy = y_mm - cy
            cos_a = np.cos(-self.rotation_angle_rad)
            sin_a = np.sin(-self.rotation_angle_rad)
            return float(cx + dx * cos_a - dy * sin_a), float(cy + dx * sin_a + dy * cos_a)
        return float(x_mm), float(y_mm)

    def target_mm_to_warped_pixel(self, x_mm: float, y_mm: float) -> Tuple[float, float]:
        """Transforms real-world target mm to warped pixel coordinate."""
        if self.geometry_homography_mm is not None:
            pt = np.array([[[x_mm, y_mm]]], dtype=np.float32)
            trans = cv2.perspectiveTransform(pt, self.geometry_homography_mm)
            x_mm = float(trans[0][0][0])
            y_mm = float(trans[0][0][1])
        elif self.rotation_angle_rad != 0.0:
            cx = self.target_width_mm / 2.0
            cy = self.target_height_mm / 2.0
            dx = x_mm - cx
            dy = y_mm - cy
            cos_a = np.cos(self.rotation_angle_rad)
            sin_a = np.sin(self.rotation_angle_rad)
            x_mm = float(cx + dx * cos_a - dy * sin_a)
            y_mm = float(cy + dx * sin_a + dy * cos_a)

        x_w_px = x_mm * (self.warped_width_px / self.target_width_mm)
        y_w_px = y_mm * (self.warped_height_px / self.target_height_mm)
        return float(x_w_px), float(y_w_px)
