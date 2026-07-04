import os
import logging
import time
from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np

logger = logging.getLogger("app.ai_verifier")

# Safe imports for YOLO and SAHI dependencies
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("ultralytics package is not installed. AI Verification will run in fallback mode.")

class AIVerifier:
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.model_path = model_path
        self.device = "cpu"
        self.last_img_id = None
        self.last_detections = []
        # When False, the verifier is bypassed: every OpenCV candidate is auto-accepted.
        self.enabled = True
        
        if YOLO_AVAILABLE:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"YOLOv8 using hardware device: {self.device}")
            self.load_model(model_path)

    def load_model(self, model_path: Optional[str] = None) -> bool:
        if not YOLO_AVAILABLE:
            return False
            
        try:
            # Default fallback to public YOLOv8s if no custom path is configured or exists
            if not model_path or not os.path.exists(model_path):
                # Using standard yolov8s.pt, ultralytics will auto-download it on first call
                model_path = "yolov8s.pt"
                logger.info("Custom weights not found. Loading default pre-trained yolov8s.pt...")
                
            self.model = YOLO(model_path)
            self.model.to(self.device)
            self.model_path = model_path
            logger.info(f"YOLOv8s model loaded successfully from {model_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load YOLOv8s model: {e}")
            self.model = None
            return False

    def verify_candidate_roi(
        self, 
        img: np.ndarray, 
        cX: float, 
        cY: float, 
        diameter_px: float,
        padding_factor: float = 3.0,
        min_size: int = 64,
        use_sahi: bool = False,
        circularity: Optional[float] = None,
        solidity: Optional[float] = None,
        aspect_ratio: Optional[float] = None
    ) -> Tuple[bool, float, str]:
        """
        Crops a Region of Interest (ROI) around the candidate centroid, 
        runs YOLOv8s or SAHI verification, and returns (is_verified, confidence, class_name).
        """
        if not self.enabled:
            # Verifier bypassed by config: accept the OpenCV candidate as-is.
            return True, 0.85, "verifier_bypassed"

        if not YOLO_AVAILABLE or self.model is None:
            # Fallback mode: automatically approve OpenCV candidates with 100% confidence
            return True, 0.85, "opencv_fallback"

        # Check if we should use full-image context matching (only for custom models)
        use_full_image = (self.model_path != "yolov8s.pt") and (not use_sahi)
        
        if use_full_image:
            try:
                # Check cache
                current_img_id = id(img)
                if self.last_img_id != current_img_id:
                    # Run YOLO on the full image. Use a low conf so a weak/under-trained single-class
                    # model still proposes hole boxes (the default 0.25 made it return nothing here).
                    results = self.model(img, verbose=False, device=self.device, conf=0.10)[0]
                    detections = []
                    for box in results.boxes:
                        coords = box.xyxy[0].cpu().numpy() # [x1, y1, x2, y2]
                        conf = float(box.conf[0].cpu().item())
                        cls_id = int(box.cls[0].cpu().item())
                        class_names = getattr(self.model, "names", {})
                        cls_name = class_names.get(cls_id, f"class_{cls_id}")
                        detections.append({
                            "bbox": coords,
                            "confidence": conf,
                            "class_name": cls_name
                        })
                    self.last_img_id = current_img_id
                    self.last_detections = detections
                    logger.info(f"YOLO full-image inference executed: found {len(detections)} detections.")
                    
                # Check if candidate (cX, cY) falls inside or is very close to any YOLO bounding box
                best_det = None
                min_dist = float("inf")
                
                # Proximity check
                for det in self.last_detections:
                    x1, y1, x2, y2 = det["bbox"]
                    pad = 10.0
                    in_box = (x1 - pad <= cX <= x2 + pad) and (y1 - pad <= cY <= y2 + pad)
                    
                    bx_cx = (x1 + x2) / 2.0
                    by_cy = (y1 + y2) / 2.0
                    dist = np.sqrt((bx_cx - cX)**2 + (by_cy - cY)**2)
                    
                    # Accept if centroid falls inside the padded box, or if distance is less than 30px
                    if in_box or dist < 30.0:
                        if dist < min_dist:
                            min_dist = dist
                            best_det = det
                
                if best_det is not None:
                    conf = best_det["confidence"]
                    class_name = best_det["class_name"]
                    if class_name == "false_positive":
                        logger.info(f"YOLO full-image rejected candidate at ({cX:.1f}, {cY:.1f}) as false_positive (conf: {conf:.2f})")
                        return False, conf, class_name
                    
                    # Custom model classes are verified if they map to 'hole' or similar, with a lenient conf threshold (0.25)
                    is_verified = class_name in ["hole", "bullet_hole", "paper_tear"] and conf >= 0.25
                    logger.info(f"YOLO full-image verified candidate at ({cX:.1f}, {cY:.1f}) -> Verified={is_verified}, Class={class_name}, Conf={conf:.2f}")
                    return is_verified, conf, f"yolo_full:{class_name}"
                else:
                    # No overlapping YOLO box. This single-class model only has a 'hole' class (no
                    # 'false_positive' class), so it can only CONFIRM holes, never reject them — using
                    # it as a hard gate just drops real holes it happened to miss. So we accept any
                    # candidate with a plausible bullet-hole shape. Now that before/after frames are
                    # properly aligned the diff is clean, so these candidates are genuine holes, not
                    # warp noise. Thresholds sized for real pellet holes (~6-8px on the 1000px warp).
                    is_clean_hole = False
                    if circularity is not None and solidity is not None and aspect_ratio is not None:
                        is_clean_hole = (diameter_px >= 5.0) and (circularity >= 0.45) and (solidity >= 0.65) and (0.3 <= aspect_ratio <= 3.0)

                    if is_clean_hole:
                        logger.info(f"YOLO missed candidate at ({cX:.1f}, {cY:.1f}); approved via OpenCV shape (d={diameter_px:.1f}, circ={circularity:.2f}, solid={solidity:.2f}).")
                        return True, 0.65, "opencv_shape_fallback"

                    logger.info(f"Candidate at ({cX:.1f}, {cY:.1f}) rejected — no YOLO overlap and shape not hole-like.")
                    return False, 0.0, "no_overlapping_yolo_detection"
            except Exception as e:
                logger.error(f"Error during YOLO full-image verification: {e}. Falling back to crop verification.")

        try:
            h, w = img.shape[:2]
            
            # Calculate crop box size
            crop_size = max(int(diameter_px * padding_factor), min_size)
            
            x1 = max(0, int(cX - crop_size / 2))
            y1 = max(0, int(cY - crop_size / 2))
            x2 = min(w, int(cX + crop_size / 2))
            y2 = min(h, int(cY + crop_size / 2))
            
            if (x2 - x1) < 10 or (y2 - y1) < 10:
                return False, 0.0, "invalid_roi"
                
            roi = img[y1:y2, x1:x2]
            
            if use_sahi:
                # Slicing size for small object/crop
                slice_sz = max(16, min(32, roi.shape[1], roi.shape[0]))
                detections = self.run_sahi_inference(roi, slice_size=slice_sz, overlap=0.1, conf_threshold=0.25)
                
                if len(detections) == 0:
                    return False, 0.0, "no_sahi_detection"
                    
                # Find the detection closest to the center of the crop
                best_det = None
                min_dist = float("inf")
                roi_cx, roi_cy = (x2 - x1) / 2.0, (y2 - y1) / 2.0
                
                for det in detections:
                    bbox = det["bbox"] # [x1, y1, x2, y2]
                    bx_cx = (bbox[0] + bbox[2]) / 2.0
                    by_cy = (bbox[1] + bbox[3]) / 2.0
                    dist = np.sqrt((bx_cx - roi_cx)**2 + (by_cy - roi_cy)**2)
                    if dist < min_dist:
                        min_dist = dist
                        best_det = det
                        
                if best_det is None:
                    return False, 0.0, "no_centered_sahi_detection"
                    
                conf = best_det["confidence"]
                class_id = best_det["class_id"]
                verification_method = "sahi_roi"
            else:
                # Run YOLO inference on the cropped ROI
                results = self.model(roi, verbose=False, device=self.device)[0]
                
                # If no detections in ROI, it is likely a false positive
                if len(results.boxes) == 0:
                    return False, 0.0, "no_detection"
                    
                # Find the detection closest to the center of the crop
                best_det = None
                min_dist = float("inf")
                roi_cx, roi_cy = (x2 - x1) / 2.0, (y2 - y1) / 2.0
                
                for box in results.boxes:
                    coords = box.xyxy[0].cpu().numpy()
                    bx_cx = (coords[0] + coords[2]) / 2.0
                    by_cy = (coords[1] + coords[3]) / 2.0
                    
                    dist = np.sqrt((bx_cx - roi_cx)**2 + (by_cy - roi_cy)**2)
                    if dist < min_dist:
                        min_dist = dist
                        best_det = box
                        
                if best_det is None:
                    return False, 0.0, "no_centered_detection"
                    
                conf = float(best_det.conf[0].cpu().item())
                class_id = int(best_det.cls[0].cpu().item())
                verification_method = "yolo_roi"
            
            # Map class IDs to names
            class_names = getattr(self.model, "names", {})
            class_name = class_names.get(class_id, f"class_{class_id}")
            
            if class_name == "false_positive":
                logger.info(f"YOLO/SAHI rejected candidate at ({cX:.1f}, {cY:.1f}) as false_positive (conf: {conf:.2f})")
                return False, conf, class_name
                
            if self.model_path == "yolov8s.pt":
                return True, conf, "yolov8s_pretrained_fallback"
                
            is_verified = class_name in ["hole", "bullet_hole", "paper_tear"] and conf >= 0.40
            return is_verified, conf, f"{verification_method}:{class_name}"

        except Exception as e:
            logger.error(f"Error during YOLO/SAHI ROI verification: {e}")
            return True, 0.70, "opencv_error_fallback"

    def run_sahi_inference(
        self, 
        img: np.ndarray, 
        slice_size: int = 320, 
        overlap: float = 0.2, 
        conf_threshold: float = 0.25
    ) -> List[Dict[str, Any]]:
        """
        SAHI (Slicing Aided Hyper Inference) implementation:
        1. Divides the high-resolution target image into overlapping slices.
        2. Runs YOLOv8s inference on each slice.
        3. Transforms coordinates back to global canvas coordinates.
        4. Merges predictions using Non-Maximum Suppression (NMS) to handle overlaps.
        """
        if not YOLO_AVAILABLE or self.model is None:
            return []

        h, w = img.shape[:2]
        step = int(slice_size * (1 - overlap))
        
        global_detections = []
        
        # Generate slices
        for y_offset in range(0, h, step):
            for x_offset in range(0, w, step):
                # Bounded coordinates
                x1 = x_offset
                y1 = y_offset
                x2 = min(w, x_offset + slice_size)
                y2 = min(h, y_offset + slice_size)
                
                # Make sure the slice is of reasonable size
                if (x2 - x1) < 50 or (y2 - y1) < 50:
                    continue
                    
                slice_img = img[y1:y2, x1:x2]
                
                # Run YOLO inference
                results = self.model(slice_img, verbose=False, conf=conf_threshold, device=self.device)[0]
                
                for box in results.boxes:
                    coords = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().item())
                    cls_id = int(box.cls[0].cpu().item())
                    
                    # Convert bounding box coordinates back to global space
                    gx1 = coords[0] + x1
                    gy1 = coords[1] + y1
                    gx2 = coords[2] + x1
                    gy2 = coords[3] + y1
                    
                    global_detections.append({
                        "bbox": [gx1, gy1, gx2, gy2],
                        "confidence": conf,
                        "class_id": cls_id
                    })

        # Apply Non-Maximum Suppression (NMS) to merge overlapping bounding boxes
        merged_detections = self._apply_nms(global_detections, iou_threshold=0.45)
        return merged_detections

    def _apply_nms(self, detections: List[Dict[str, Any]], iou_threshold: float) -> List[Dict[str, Any]]:
        """Applies Non-Maximum Suppression (NMS) to merge global detections."""
        if not detections:
            return []
            
        # Sort by confidence descending
        sorted_dets = sorted(detections, key=lambda x: x["confidence"], reverse=True)
        keep = []
        
        while sorted_dets:
            best = sorted_dets.pop(0)
            keep.append(best)
            
            # Compare remaining boxes with 'best'
            remaining = []
            for det in sorted_dets:
                iou = self._calculate_iou(best["bbox"], det["bbox"])
                if iou < iou_threshold:
                    remaining.append(det)
            sorted_dets = remaining
            
        return keep

    def _calculate_iou(self, boxA: List[float], boxB: List[float]) -> float:
        """Calculates Intersection over Union (IoU) of two bounding boxes."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        
        interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
        if interArea == 0:
            return 0.0
            
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        
        unionArea = boxAArea + boxBArea - interArea
        return interArea / unionArea if unionArea > 0 else 0.0

# Singleton AI Verifier instance with lazy loading fallback
ai_verifier = AIVerifier()
