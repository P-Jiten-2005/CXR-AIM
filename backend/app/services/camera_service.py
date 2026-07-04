import cv2
import numpy as np
import threading
import time
import os
import logging
from typing import Optional, Tuple
from datetime import datetime
from app.core.config import settings
from app.services.cv_engine import cv_engine
from app.services.ws_manager import ws_manager
from app.services.apriltag_service import apriltag_service, annotate_frame_with_tags, A4_W, A4_H
from app.models import models
from app.core.database import AsyncSessionLocal
from sqlalchemy import select, func

logger = logging.getLogger("app.camera_service")

class CameraService:
    def __init__(self):
        self.cap: Optional[cv2.VideoCapture] = None
        self.current_frame: Optional[np.ndarray] = None
        self.is_running = False
        self.is_monitoring = False
        self.camera_source = "0"  # Default webcam index
        self._thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._auto_thread: Optional[threading.Thread] = None
        self._auto_session_id: Optional[str] = None
        self._tag_stable_count = 0
        self.is_auto_pipeline = False
        self.lock = threading.Lock()
        
        # Calibration state
        self.calibrated_baseline: Optional[np.ndarray] = None
        self.active_session_id: Optional[str] = None
        self.is_calibrated = False
        self.zoom_factor = 1.0
        self.homography_matrix: Optional[np.ndarray] = None
        self.calibration_method: Optional[str] = None
        self.connect_warning: Optional[str] = None
        # Target capture resolution requested from the source. High values make the driver
        # negotiate its real maximum (e.g. 1080p/4K), preserving original source quality.
        self.requested_width = 1920
        self.requested_height = 1080
        self.actual_width = 0
        self.actual_height = 0


    def set_active_session(self, session_id: str):
        with self.lock:
            self._auto_session_id = session_id

    def reset_calibration(self):
        with self.lock:
            self.calibrated_baseline = None
            self.active_session_id = None
            self.is_calibrated = False
            self.homography_matrix = None
            self.calibration_method = None
            logger.info("Camera service calibration state reset.")


    def start_camera(self, source: str = "0") -> bool:
        with self.lock:
            if self.is_running:
                if self.camera_source == source:
                    return True
                self.stop_camera_unlocked()

            try:
                src = int(source)
            except ValueError:
                src = source

            if isinstance(src, int):
                if os.name == "nt":
                    logger.info(f"Attempting to open camera index {src} via DirectShow...")
                    self.cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
                    if not self.cap.isOpened():
                        logger.warning(f"DirectShow failed to open index {src}. Falling back to default MSMF backend...")
                        self.cap = cv2.VideoCapture(src)
                else:
                    self.cap = cv2.VideoCapture(src)
            else:
                self.cap = cv2.VideoCapture(src)

            if not self.cap.isOpened():
                logger.error(f"Failed to open video source: {source}")
                self.cap = None
                return False

            # Request FULL native resolution — but ONLY for physical device indexes. For URL/IP
            # sources (e.g. DroidCam's http://<ip>:4747/video) the stream resolution is fixed by the
            # URL itself; forcing CAP_PROP/MJPG there can break or downgrade the stream.
            if isinstance(src, int):
                try:
                    self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # needed for HD on USB/virtual cams
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.requested_width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.requested_height)
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception as e:
                    logger.warning(f"Could not set camera resolution (using device default): {e}")

            self.connect_warning: Optional[str] = None
            ret, test_frame = self.cap.read()
            # Record the ACTUAL delivered resolution from the real frame (most reliable).
            if ret and test_frame is not None:
                self.actual_height, self.actual_width = test_frame.shape[:2]
                logger.info(f"Camera '{source}' delivering {self.actual_width}x{self.actual_height}")
                if self.actual_width < 1280:
                    self.connect_warning = (
                        f"Source is only {self.actual_width}x{self.actual_height}. For full quality use DroidCam HD "
                        f"or connect via the IP URL (e.g. http://<phone-ip>:4747/video). Free DroidCam caps at 640x480."
                    )
            if not ret or test_frame is None:
                self.connect_warning = (
                    f"Camera source {source} opened but is not returning frames. "
                    "The device might be locked by another app."
                )
                logger.warning(self.connect_warning)
            elif float(test_frame.mean()) < 8.0:
                self.connect_warning = (
                    f"Camera source {source} is delivering near-black frames. If this is DroidCam, "
                    "open the DroidCam client on the PC and connect it to your phone before capturing."
                )
                logger.warning(self.connect_warning)

            self.camera_source = source
            self.is_running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            logger.info(f"Camera stream started successfully: Source {source}")
            return True

    def stop_camera(self):
        with self.lock:
            self.stop_camera_unlocked()

    def stop_camera_unlocked(self):
        self.is_monitoring = False
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        self.current_frame = None
        self._tag_stable_count = 0
        logger.info("Camera stream stopped.")

    def _capture_loop(self):
        while self.is_running:
            if self.cap:
                ret, frame = self.cap.read()
                if ret:
                    if self.zoom_factor > 1.0:
                        h, w = frame.shape[:2]
                        new_h, new_w = int(h / self.zoom_factor), int(w / self.zoom_factor)
                        startY = (h - new_h) // 2
                        startX = (w - new_w) // 2
                        cropped = frame[startY:startY+new_h, startX:startX+new_w]
                        frame = cv2.resize(cropped, (w, h))
                    with self.lock:
                        self.current_frame = frame
                else:
                    time.sleep(0.01)
            time.sleep(0.01)

    def get_latest_frame_jpeg(self) -> Optional[bytes]:
        with self.lock:
            if self.current_frame is None:
                return None
            preview_frame = self.current_frame.copy()
            if self.is_calibrated:
                cv2.putText(preview_frame, "CALIBRATED FEED", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(preview_frame, "UNCONNECTED FEED - PLACE TARGET", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
            ret, jpeg = cv2.imencode('.jpg', preview_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
            return jpeg.tobytes() if ret else None

    def get_tag_feed_jpeg(self) -> Optional[bytes]:
        """Returns the latest live frame with AprilTag/paper-quad detection drawn on top, as a
        JPEG. Powers the diagnostic 'Live Tag Feed' so the operator can see exactly what the
        calibration detector sees (which tags, their IDs, and the recovered paper region)."""
        with self.lock:
            if self.current_frame is None:
                return None
            frame = self.current_frame.copy()
        try:
            annotated, _ = annotate_frame_with_tags(frame)
        except Exception as e:
            logger.warning(f"Tag feed annotation failed, streaming raw frame: {e}")
            annotated = frame
        ret, jpeg = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return jpeg.tobytes() if ret else None

    def get_tag_debug_info(self) -> dict:
        """Lightweight JSON snapshot of the current tag detection state (count + ids)."""
        with self.lock:
            if self.current_frame is None:
                return {"camera": False, "tag_count": 0, "tag_ids": [], "paper_ok": False}
            frame = self.current_frame.copy()
        try:
            _, info = annotate_frame_with_tags(frame)
            info["camera"] = True
            return info
        except Exception as e:
            logger.warning(f"Tag debug info failed: {e}")
            return {"camera": True, "tag_count": 0, "tag_ids": [], "paper_ok": False}

    def _find_paper_contour(self, img: np.ndarray) -> Optional[np.ndarray]:
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            frame_area = img.shape[0] * img.shape[1]
            binaries = []
            
            try:
                blurred_adaptive = cv2.bilateralFilter(gray, 9, 75, 75)
                thresh_adaptive = cv2.adaptiveThreshold(
                    blurred_adaptive, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV, 21, 4
                )
                binaries.append(("adaptive", thresh_adaptive))
            except Exception as e:
                logger.warning(f"Adaptive threshold prep failed: {e}")
                
            try:
                blurred_canny = cv2.GaussianBlur(gray, (5, 5), 0)
                edged = cv2.Canny(blurred_canny, 30, 150)
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                dilated = cv2.dilate(edged, kernel, iterations=1)
                binaries.append(("canny", dilated))
            except Exception as e:
                logger.warning(f"Canny edge prep failed: {e}")

            try:
                blurred_otsu = cv2.GaussianBlur(gray, (5, 5), 0)
                _, thresh_otsu = cv2.threshold(blurred_otsu, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                binaries.append(("otsu_inv", thresh_otsu))
                _, thresh_otsu_normal = cv2.threshold(blurred_otsu, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                binaries.append(("otsu", thresh_otsu_normal))
            except Exception as e:
                logger.warning(f"Otsu prep failed: {e}")
                
            for name, binary_img in binaries:
                contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                contours = sorted(contours, key=cv2.contourArea, reverse=True)
                for c in contours:
                    area = cv2.contourArea(c)
                    if not (0.04 * frame_area <= area <= 0.95 * frame_area):
                        continue
                    peri = cv2.arcLength(c, True)
                    approx = None
                    for eps_factor in [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06]:
                        candidate = cv2.approxPolyDP(c, eps_factor * peri, True)
                        if len(candidate) == 4 and cv2.isContourConvex(candidate):
                            approx = candidate
                            break
                    if approx is not None:
                        x, y, w, h = cv2.boundingRect(approx)
                        aspect_ratio = float(w) / h
                        if 0.5 <= aspect_ratio <= 2.0:
                            logger.info(f"Target paper contour detected using strategy: {name} (area: {area}, aspect: {aspect_ratio:.2f})")
                            return approx.reshape(4, 2)
        except Exception as e:
            logger.error(f"Error in _find_paper_contour: {e}")
        logger.warning("No robust 4-corner paper target detected with any strategy.")
        return None

    def rectify_target_paper(self, img: np.ndarray) -> Tuple[np.ndarray, bool]:
        pts = self._find_paper_contour(img)
        if pts is not None:
            try:
                rect = np.zeros((4, 2), dtype="float32")
                s = pts.sum(axis=1)
                rect[0] = pts[np.argmin(s)]
                rect[2] = pts[np.argmax(s)]
                diff = np.diff(pts, axis=1)
                rect[1] = pts[np.argmin(diff)]
                rect[3] = pts[np.argmax(diff)]
                margin = 150
                dst = np.array([
                    [margin, margin],
                    [999 - margin, margin],
                    [999 - margin, 999 - margin],
                    [margin, 999 - margin]
                ], dtype="float32")
                M = cv2.getPerspectiveTransform(rect, dst)
                warped = cv2.warpPerspective(img, M, (1000, 1000), flags=cv2.INTER_LANCZOS4)
                return warped, True
            except Exception as e:
                logger.error(f"Error rectifying target paper from detected contour: {e}")
        h, w = img.shape[:2]
        crop_size = min(h, w)
        startY, startX = (h - crop_size) // 2, (w - crop_size) // 2
        cropped = img[startY:startY+crop_size, startX:startX+crop_size]
        resized = cv2.resize(cropped, (1000, 1000), interpolation=cv2.INTER_LANCZOS4)
        return resized, False

    def calibrate_homography(self, session_id: str) -> bool:
        with self.lock:
            if self.current_frame is None:
                logger.error("No active camera frame to calibrate.")
                return False
            frame_to_calibrate = self.current_frame.copy()

        try:
            warped, corners, tags = apriltag_service.detect_and_warp(frame_to_calibrate)
            if warped is not None and len(tags) >= apriltag_service.min_tags:
                tag_ids = [t["id"] for t in tags]
                logger.info(f"AprilTag calibration: {len(tags)} tags detected (IDs: {tag_ids})")
                rectified_target = cv2.resize(warped, (1000, 1000), interpolation=cv2.INTER_LANCZOS4)
                dst_1k = np.array([[0, 0], [999, 0], [999, 999], [0, 999]], dtype=np.float32)
                M = cv2.getPerspectiveTransform(corners, dst_1k)
                baseline_name = f"baseline_{session_id}.jpg"
                file_path = os.path.join(settings.UPLOAD_DIR, baseline_name)
                cv2.imwrite(file_path, rectified_target, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                with self.lock:
                    self.homography_matrix = M
                    self.calibrated_baseline = rectified_target
                    self.active_session_id = session_id
                    self.is_calibrated = True
                    self.calibration_method = "apriltag"
                logger.info("Camera calibrated via AprilTag warp.")
                return True
        except Exception as e:
            logger.warning(f"AprilTag calibration failed: {e}")

        pts = self._find_paper_contour(frame_to_calibrate)
        if pts is not None:
            try:
                rect = np.zeros((4, 2), dtype="float32")
                s = pts.sum(axis=1)
                rect[0] = pts[np.argmin(s)]
                rect[2] = pts[np.argmax(s)]
                diff = np.diff(pts, axis=1)
                rect[1] = pts[np.argmin(diff)]
                rect[3] = pts[np.argmax(diff)]
                margin = 150
                dst = np.array([
                    [margin, margin],
                    [999 - margin, margin],
                    [999 - margin, 999 - margin],
                    [margin, 999 - margin]
                ], dtype="float32")
                M = cv2.getPerspectiveTransform(rect, dst)
                rectified_target = cv2.warpPerspective(frame_to_calibrate, M, (1000, 1000), flags=cv2.INTER_LANCZOS4)
                baseline_name = f"baseline_{session_id}.jpg"
                file_path = os.path.join(settings.UPLOAD_DIR, baseline_name)
                cv2.imwrite(file_path, rectified_target, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                with self.lock:
                    self.homography_matrix = M
                    self.calibrated_baseline = rectified_target
                    self.active_session_id = session_id
                    self.is_calibrated = True
                    self.calibration_method = "paper"
                logger.info("Homography matrix calibrated successfully from paper borders.")
                return True
            except Exception as e:
                logger.error(f"Failed to calibrate homography from detected paper borders: {e}")

        # Fallback for tag-less targets (e.g. a printed Figure-11 with no AprilTags, or a target
        # that fills the frame so there's no clean 4-corner paper border). We capture a centered
        # square crop resized to 1000x1000 instead of hard-failing. Differencing still works because
        # the camera is fixed and the before/after frames are ORB-aligned at detection time.
        #
        # Guard: reject a near-black / blank frame (the old "wrong camera = selfie/black" bug) so a
        # genuinely empty feed still fails loudly rather than poisoning the baseline.
        try:
            mean_brightness = float(frame_to_calibrate.mean())
            if mean_brightness < 12.0:
                logger.error(f"Calibration fallback refused: frame is near-black (mean={mean_brightness:.1f}).")
                return False

            h, w = frame_to_calibrate.shape[:2]
            crop_size = min(h, w)
            startY, startX = (h - crop_size) // 2, (w - crop_size) // 2
            rect = np.array([
                [startX, startY], [startX + crop_size - 1, startY],
                [startX + crop_size - 1, startY + crop_size - 1], [startX, startY + crop_size - 1],
            ], dtype="float32")
            dst = np.array([[0, 0], [999, 0], [999, 999], [0, 999]], dtype="float32")
            M = cv2.getPerspectiveTransform(rect, dst)
            rectified_target = cv2.warpPerspective(frame_to_calibrate, M, (1000, 1000), flags=cv2.INTER_LANCZOS4)
            baseline_name = f"baseline_{session_id}.jpg"
            file_path = os.path.join(settings.UPLOAD_DIR, baseline_name)
            cv2.imwrite(file_path, rectified_target, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
            with self.lock:
                self.homography_matrix = M
                self.calibrated_baseline = rectified_target
                self.active_session_id = session_id
                self.is_calibrated = True
                self.calibration_method = "fallback_crop"
            logger.warning(
                "No AprilTags / paper border found — calibrated via centered-crop fallback. "
                "For accurate scoring zones, add AprilTags to the target corners."
            )
            return True
        except Exception as e:
            logger.error(f"Centered-crop fallback calibration failed: {e}")
            return False

    def capture_before_fire(self, session_id: str) -> Optional[np.ndarray]:
        with self.lock:
            if self.current_frame is None:
                logger.error("No active camera frame to capture before fire.")
                return None
            frame = self.current_frame.copy()
            M = self.homography_matrix

        if M is not None:
            rectified = cv2.warpPerspective(frame, M, (1000, 1000), flags=cv2.INTER_LANCZOS4)
        else:
            rectified, _ = self.rectify_target_paper(frame)
            
        baseline_name = f"baseline_{session_id}.jpg"
        file_path = os.path.join(settings.UPLOAD_DIR, baseline_name)
        cv2.imwrite(file_path, rectified, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
        with self.lock:
            self.calibrated_baseline = rectified
            self.active_session_id = session_id
        logger.info(f"Captured reference baseline target for session {session_id}")
        return rectified

    def capture_after_fire(self, session_id: str) -> Optional[str]:
        with self.lock:
            if self.current_frame is None:
                logger.error("No active camera frame to capture after fire.")
                return None
            frame = self.current_frame.copy()
            M = self.homography_matrix

        if M is not None:
            rectified = cv2.warpPerspective(frame, M, (1000, 1000), flags=cv2.INTER_LANCZOS4)
        else:
            rectified, _ = self.rectify_target_paper(frame)

        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        file_name = f"capture_{session_id}_{timestamp_str}.jpg"
        file_path = os.path.join(settings.UPLOAD_DIR, file_name)
        cv2.imwrite(file_path, rectified, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
        logger.info(f"Captured after-fire target for session {session_id} -> {file_path}")
        return file_path

    def rectify_frame(self, img: np.ndarray) -> np.ndarray:
        # CRITICAL: use the SAME homography that produced the baseline so the before/after
        # frames are pixel-aligned. The camera is fixed, so the baseline's warp applies to
        # every later frame. Re-detecting tags per-frame (as this used to do) can pick a
        # different corner order / tag subset and rotate the warp — which makes differencing
        # flag the entire target as changed and spawn dozens of phantom "shots".
        with self.lock:
            M = self.homography_matrix
        if M is not None:
            return cv2.warpPerspective(img, M, (1000, 1000), flags=cv2.INTER_LANCZOS4)

        # Uncalibrated fallback only: no stored homography yet, so derive one from this frame.
        try:
            warped, corners, tags = apriltag_service.detect_and_warp(img)
            if warped is not None and len(tags) >= 3:
                return cv2.resize(warped, (1000, 1000), interpolation=cv2.INTER_LANCZOS4)
        except Exception as e:
            logger.warning(f"AprilTag rectification failed: {e}")
        warped, _ = self.rectify_target_paper(img)
        return warped

camera_service = CameraService()

