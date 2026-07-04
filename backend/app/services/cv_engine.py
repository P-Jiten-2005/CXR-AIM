import os
import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("app.cv_engine")

class CVEngine:
    def __init__(
        self,
        min_area: float = 15.0,      # Minimum pixel area; on the 1000x1000 warp a real hole is 100+ px², warp-border specks are 3-22 px²
        max_area: float = 5000.0,    # Maximum pixel area
        min_circularity: float = 0.30, # Roundness threshold (lowered to catch distorted holes)
        min_solidity: float = 0.50,    # Solidity threshold (lowered to catch irregular tears)
        aspect_ratio_range: Tuple[float, float] = (0.2, 5.0), # Allowable stretch ratio (widened for small pixel shapes)
        proximity_threshold_px: float = 15.0, # Max pixel distance to consider a hole as pre-existing
        border_margin_px: float = 30.0, # Candidates this close to the warp border are warp-seam artifacts, not shots
        abs_diff_threshold: int = 25,  # Min gray-level change vs baseline to count as a new mark
        sahi: Optional[bool] = None,
        sahi_min_roi_size: Optional[float] = None
    ):
        self.min_area = min_area
        self.max_area = max_area
        self.min_circularity = min_circularity
        self.min_solidity = min_solidity
        self.aspect_ratio_range = aspect_ratio_range
        self.proximity_threshold_px = proximity_threshold_px
        self.border_margin_px = border_margin_px
        self.abs_diff_threshold = abs_diff_threshold
        self._exclusion_mask_cache: Dict[Tuple[str, float], np.ndarray] = {}
        
        # Load from config settings if not supplied
        if sahi is None:
            try:
                from app.core.config import settings
                self.sahi = getattr(settings, "SAHI_ENABLED", False)
            except Exception:
                self.sahi = False
        else:
            self.sahi = sahi
            
        if sahi_min_roi_size is None:
            try:
                from app.core.config import settings
                self.sahi_min_roi_size = getattr(settings, "SAHI_MIN_ROI_SIZE", 32.0)
            except Exception:
                self.sahi_min_roi_size = 32.0
        else:
            self.sahi_min_roi_size = sahi_min_roi_size

    def _baseline_exclusion_mask(self, baseline_path: str, gray_base: np.ndarray) -> np.ndarray:
        """
        Builds a mask of the AprilTag quads only. Warp jitter between the baseline and after-fire
        rectifications produces strong diff artifacts at the high-contrast tag borders, so each tag
        gets a generous halo. Cached per baseline file.

        NOTE: this intentionally masks ONLY the AprilTags. It must NOT mask every dark region —
        on silhouette targets (e.g. Figure-11) the black figure is a legitimate detection area and
        bullet holes appear on it. Edge-based jitter suppression (in detect_holes) handles the rest.
        """
        cache_key = None
        try:
            cache_key = (baseline_path, os.path.getmtime(baseline_path))
            cached = self._exclusion_mask_cache.get(cache_key)
            if cached is not None:
                return cached
        except OSError:
            pass

        halo_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
        mask = np.zeros_like(gray_base)

        try:
            from app.services.apriltag_service import detect_tags
            tags = detect_tags(gray_base)
            for tag in tags:
                cv2.fillConvexPoly(mask, tag["corners"].astype(np.int32), 255)
            mask = cv2.dilate(mask, halo_kernel, iterations=1)
            logger.info(f"Baseline exclusion mask built: {len(tags)} AprilTags masked.")
        except Exception as e:
            logger.warning(f"AprilTag exclusion masking unavailable ({e}); no tag mask applied.")

        if cache_key is not None:
            if len(self._exclusion_mask_cache) > 8:
                self._exclusion_mask_cache.clear()
            self._exclusion_mask_cache[cache_key] = mask
        return mask

    def align_images(self, baseline_img: np.ndarray, current_img: np.ndarray) -> np.ndarray:
        """
        Aligns current_img to baseline_img using ORB feature matching and Homography.
        Falls back to current_img if alignment fails.
        """
        try:
            gray_base = cv2.cvtColor(baseline_img, cv2.COLOR_BGR2GRAY)
            gray_curr = cv2.cvtColor(current_img, cv2.COLOR_BGR2GRAY)

            # Initialize ORB detector
            orb = cv2.ORB_create(nfeatures=1500)
            kp1, des1 = orb.detectAndCompute(gray_base, None)
            kp2, des2 = orb.detectAndCompute(gray_curr, None)

            if des1 is None or des2 is None or len(kp1) < 10 or len(kp2) < 10:
                logger.warning("Not enough features for image registration. Using unaligned current frame.")
                return current_img

            # Match features using Brute Force Hamming distance
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des1, des2)
            matches = sorted(matches, key=lambda x: x.distance)[:100]

            if len(matches) < 4:
                logger.warning("Fewer than 4 feature matches. Alignment homography calculation skipped.")
                return current_img

            # Extract location of good matches
            src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

            # Find homography matrix using RANSAC
            H, mask = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)

            if H is None:
                logger.warning("Homography matrix estimation failed. Using unaligned current frame.")
                return current_img

            # Warp current image to match baseline perspective
            height, width, channels = baseline_img.shape
            aligned_img = cv2.warpPerspective(current_img, H, (width, height))
            return aligned_img

        except Exception as e:
            logger.error(f"Image registration failed with error: {e}. Defaulting to unaligned frame.")
            return current_img

    def detect_holes(
        self, 
        baseline_path: str, 
        current_path: str, 
        existing_shots: List[Dict[str, Any]],
        align: bool = True,
        sahi: Optional[bool] = None,
        sahi_min_roi_size: Optional[float] = None,
        save_diff_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes the hybrid detection pipeline:
        1. Loads baseline & current frame.
        2. Registers (aligns) current frame if align=True.
        3. Computes absolute difference.
        4. Thresholds & morphological cleaning.
        5. Contour-based candidate extraction.
        6. Runs YOLOv8 ROI verification or SAHI sliced verification.
        7. Deduplicates against already recorded shots in the session.
        """
        baseline_img = cv2.imread(baseline_path)
        current_img = cv2.imread(current_path)

        if baseline_img is None or current_img is None:
            raise ValueError("Failed to load baseline or current image from disk.")

        # Step 1: Align current image to baseline if requested
        if align:
            aligned_current = self.align_images(baseline_img, current_img)
        else:
            aligned_current = current_img

        # Step 2: Grayscale and Blur
        gray_base = cv2.cvtColor(baseline_img, cv2.COLOR_BGR2GRAY)
        gray_curr = cv2.cvtColor(aligned_current, cv2.COLOR_BGR2GRAY)
        
        blur_base = cv2.GaussianBlur(gray_base, (5, 5), 0)
        blur_curr = cv2.GaussianBlur(gray_curr, (5, 5), 0)

        # Normalize brightness to handle auto-exposure changes
        mean_base = np.mean(blur_base)
        mean_curr = np.mean(blur_curr)
        if mean_curr > 0:
            scale_factor = mean_base / mean_curr
            scale_factor = min(max(scale_factor, 0.7), 1.3) # Cap to avoid extreme noise scaling
            blur_curr = np.clip(blur_curr * scale_factor, 0, 255).astype(np.uint8)

        # Step 3: Primary change signal — per-pixel absolute difference. This is BACKGROUND-AGNOSTIC:
        # it catches a new hole whether it appears darker (dark hole on the white sheet) or lighter
        # (torn white paper edges on a black silhouette). The old dark-on-light-only Otsu threshold
        # could never see holes on the black figure, which is why they went undetected.
        abs_diff = cv2.absdiff(blur_base, blur_curr)
        _, changed = cv2.threshold(abs_diff, self.abs_diff_threshold, 255, cv2.THRESH_BINARY)

        # Also OR in classic new-dark-on-light spots; helps faint low-contrast holes on the white sheet.
        thresh_val, bin_base = cv2.threshold(blur_base, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, bin_curr = cv2.threshold(blur_curr, thresh_val, 255, cv2.THRESH_BINARY_INV)
        new_dark = cv2.bitwise_and(
            bin_curr,
            cv2.bitwise_not(cv2.dilate(bin_base, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))))
        )
        candidate_mask = cv2.bitwise_or(changed, new_dark)

        # Step 4: Suppress warp/registration jitter. Jitter shows up along high-contrast baseline
        # EDGES (silhouette outline, scoring rings, tag borders) — never in flat interiors where a
        # real hole lands. So we mask baseline edges (a thin band), NOT entire dark regions. This is
        # the key change that lets holes be detected on the black silhouette interior.
        grad = cv2.morphologyEx(blur_base, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        _, edge_mask = cv2.threshold(grad, 40, 255, cv2.THRESH_BINARY)
        edge_mask = cv2.dilate(edge_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)), iterations=1)
        diff_binary = cv2.bitwise_and(candidate_mask, cv2.bitwise_not(edge_mask))

        # Mask the AprilTag quads (with halo) — their borders jitter strongly between warps.
        exclusion = self._baseline_exclusion_mask(baseline_path, gray_base)
        diff_binary = cv2.bitwise_and(diff_binary, cv2.bitwise_not(exclusion))

        # Step 5: Morphological Operations (Opening to remove noise, Closing to fill holes)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned = cv2.morphologyEx(diff_binary, cv2.MORPH_OPEN, kernel, iterations=1)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)

        if save_diff_path:
            try:
                cv2.imwrite(save_diff_path, cleaned, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                logger.info(f"Saved binarized difference image to {save_diff_path}")
            except Exception as e:
                logger.error(f"Failed to save difference image: {e}")

        # Step 6: Find contours
        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        new_holes = []

        # Determine SAHI settings for this run
        active_sahi = self.sahi if sahi is None else sahi
        active_sahi_min_roi_size = self.sahi_min_roi_size if sahi_min_roi_size is None else sahi_min_roi_size

        img_h, img_w = cleaned.shape[:2]

        for c in contours:
            # Area filtering
            area = cv2.contourArea(c)
            if not (self.min_area <= area <= self.max_area):
                continue

            # Perimeter for circularity
            perimeter = cv2.arcLength(c, True)
            if perimeter == 0:
                continue

            # Circularity filter
            circularity = (4.0 * np.pi * area) / (perimeter ** 2)
            if circularity < self.min_circularity:
                continue

            # Convex hull and solidity filter
            hull = cv2.convexHull(c)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 0
            if solidity < self.min_solidity:
                continue

            # Aspect ratio check
            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = float(w) / h
            if not (self.aspect_ratio_range[0] <= aspect_ratio <= self.aspect_ratio_range[1]):
                continue

            # Centroid calculations
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cX = M["m10"] / M["m00"]
            cY = M["m01"] / M["m00"]

            # Reject warp-seam artifacts: the two perspective warps (baseline vs current) never agree
            # exactly at the canvas border, producing thin high-contrast slivers there.
            if (cX < self.border_margin_px or cY < self.border_margin_px or
                    cX > img_w - self.border_margin_px or cY > img_h - self.border_margin_px):
                continue

            # Equivalent circle diameter calculation
            equiv_diameter = np.sqrt(4.0 * area / np.pi)

            # CV Shape Confidence (average of normalized roundness & solidity metrics)
            cv_confidence = float((circularity + solidity) / 2.0)
            cv_confidence = min(max(cv_confidence, 0.0), 1.0)

            # Step 7: Deduplicate candidate against existing shots list
            is_new = True
            for shot in existing_shots:
                dist = np.sqrt((cX - shot["x_raw"])**2 + (cY - shot["y_raw"])**2)
                if dist < self.proximity_threshold_px:
                    is_new = False
                    break

            if is_new:
                # Store contour as a flat coordinate list for serialization [[x1, y1], [x2, y2], ...]
                raw_contour_pts = [pt[0].tolist() for pt in c]
                new_holes.append({
                    "x_raw": float(cX),
                    "y_raw": float(cY),
                    "diameter_px": float(equiv_diameter),
                    "area": float(area),
                    "circularity": float(circularity),
                    "solidity": float(solidity),
                    "aspect_ratio": float(aspect_ratio),
                    "raw_contour": raw_contour_pts,
                    "raw_contour_np": c # keep numpy contour for localization verifier
                })

        return new_holes, aligned_current

    def detect_all_holes(
        self,
        baseline_path: str,
        current_path: str,
    ) -> List[Dict[str, Any]]:
        baseline_img = cv2.imread(baseline_path)
        current_img = cv2.imread(current_path)
        if baseline_img is None or current_img is None:
            raise ValueError("Failed to load baseline or current image from disk.")
        gray_base = cv2.cvtColor(baseline_img, cv2.COLOR_BGR2GRAY)
        gray_curr = cv2.cvtColor(current_img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced_base = clahe.apply(gray_base)
        enhanced_curr = clahe.apply(gray_curr)
        blur_base = cv2.GaussianBlur(enhanced_base, (3, 3), 0)
        blur_curr = cv2.GaussianBlur(enhanced_curr, (3, 3), 0)
        diff = cv2.absdiff(blur_base, blur_curr)
        _, thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, thresh_fixed = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
        combined = cv2.bitwise_or(thresh, thresh_fixed)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        cleaned = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        results = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 3.0 or area > 8000.0:
                continue
            perimeter = cv2.arcLength(c, True)
            if perimeter == 0:
                continue
            circularity = (4.0 * np.pi * area) / (perimeter ** 2)
            hull = cv2.convexHull(c)
            hull_area = cv2.contourArea(hull)
            solidity = area / hull_area if hull_area > 0 else 0
            x, y, w_b, h_b = cv2.boundingRect(c)
            aspect_ratio = float(w_b) / h_b
            if not (0.3 <= aspect_ratio <= 3.0):
                continue
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue
            cX = M["m10"] / M["m00"]
            cY = M["m01"] / M["m00"]
            equiv_diameter = np.sqrt(4.0 * area / np.pi)
            score = (circularity + solidity) / 2.0
            confidence = float(min(max(score, 0.0), 1.0))
            raw_contour_pts = [pt[0].tolist() for pt in c]
            results.append({
                "x_raw": float(cX),
                "y_raw": float(cY),
                "diameter_px": float(equiv_diameter),
                "confidence": confidence,
                "area": float(area),
                "circularity": float(circularity),
                "solidity": float(solidity),
                "aspect_ratio": float(aspect_ratio),
                "raw_contour": raw_contour_pts
            })
        return results

cv_engine = CVEngine()
