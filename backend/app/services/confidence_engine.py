import numpy as np
import cv2
import logging
import time
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime
from app.services.ai_verifier import ai_verifier

logger = logging.getLogger("app.confidence_engine")

class GeometryVerifier:
    @staticmethod
    def evaluate(area: float, circularity: float, solidity: float, aspect_ratio: float, config: Any) -> Tuple[str, float]:
        scores = []
        # Circularity (discrete contours can exceed 1.0)
        if circularity >= config.geom_circ_strict:
            scores.append(1.0)
        elif config.geom_circ_loose <= circularity < config.geom_circ_strict:
            scores.append(0.5)
        else:
            scores.append(0.0)

        # Solidity
        if solidity >= 0.80:  # strict
            scores.append(1.0)
        elif 0.65 <= solidity < 0.80:  # loose
            scores.append(0.5)
        else:
            scores.append(0.0)

        # Aspect Ratio
        if config.geom_aspect_strict_min <= aspect_ratio <= config.geom_aspect_strict_max:
            scores.append(1.0)
        elif config.geom_aspect_loose_min <= aspect_ratio <= config.geom_aspect_loose_max:
            scores.append(0.5)
        else:
            scores.append(0.0)

        geom_score = float(np.mean(scores))
        is_area_out = not (config.geom_area_loose_min <= area <= config.geom_area_loose_max)
        is_fail = any(s == 0.0 for s in scores) or is_area_out
        
        if is_fail:
            return "fail", geom_score
        elif all(s == 1.0 for s in scores):
            return "strong_pass", geom_score
        else:
            return "weak_pass", geom_score

class DuplicateVerifier:
    @staticmethod
    def evaluate(cX: float, cY: float, timestamp: float, verified_shots: List[Any], config: Any) -> Tuple[str, Dict[str, Any]]:
        for s in verified_shots:
            is_dict = isinstance(s, dict)
            x_val = s["x_raw"] if is_dict else s.x_raw
            y_val = s["y_raw"] if is_dict else s.y_raw
            shot_num = s["shot_number"] if is_dict else s.shot_number
            shot_id = s.get("id") if is_dict else getattr(s, "id", None)
            
            created_at = s.get("created_at") if is_dict else getattr(s, "created_at", None)
            if created_at is not None:
                if hasattr(created_at, "timestamp"):
                    s_ts = created_at.timestamp()
                elif isinstance(created_at, (int, float)):
                    s_ts = float(created_at)
                elif isinstance(created_at, str):
                    try:
                        s_ts = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        s_ts = timestamp
                else:
                    s_ts = timestamp
            else:
                created_at_ts = s.get("created_at_ts") if is_dict else getattr(s, "created_at_ts", None)
                if created_at_ts is not None:
                    s_ts = float(created_at_ts)
                else:
                    s_ts = timestamp

            dist = np.sqrt((cX - x_val)**2 + (cY - y_val)**2)
            t_diff = abs(timestamp - s_ts)
            if dist <= config.duplicate_radius_px and t_diff <= config.duplicate_time_window_sec:
                return "duplicate", {"matched_shot_number": shot_num, "dist": dist, "shot_id": shot_id}
        return "neutral", {}

class LocalizationVerifier:
    @staticmethod
    def evaluate(c_data: Any, gray_img: np.ndarray, config: Any) -> Tuple[str, float, Dict[str, Any]]:
        c = np.array(c_data, dtype=np.int32)
        if c.size == 0 or len(c) == 0:
            raise ValueError("empty contour")
        
        # 1. Moment based centroid
        M = cv2.moments(c)
        if M["m00"] == 0:
            raise ValueError("zero moments")
        cX_m = M["m10"] / M["m00"]
        cY_m = M["m01"] / M["m00"]

        # 2. Intensity-weighted centroid
        x, y, w, h = cv2.boundingRect(c)
        img_h, img_w = gray_img.shape
        x_start = max(0, x)
        y_start = max(0, y)
        x_end = min(img_w, x + w)
        y_end = min(img_h, y + h)
        
        roi = gray_img[y_start:y_end, x_start:x_end]
        if roi.size == 0:
            raise ValueError("empty ROI bounding box")
        y_indices, x_indices = np.indices(roi.shape)
        weights = 255.0 - roi.astype(np.float32)  # Darker pixels are bullet hole interiors -> higher weight
        total_w = weights.sum()
        if total_w > 0:
            cX_w = x_start + (x_indices * weights).sum() / total_w
            cY_w = y_start + (y_indices * weights).sum() / total_w
        else:
            cX_w, cY_w = cX_m, cY_m

        # 3. Ellipse fit
        if len(c) >= 5:
            try:
                ellipse = cv2.fitEllipse(c)
                cX_e, cY_e = ellipse[0]
            except Exception:
                cX_e, cY_e = cX_m, cY_m
        else:
            cX_e, cY_e = cX_m, cY_m

        # 4. Intensity peak center
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(roi)
        cX_p = x_start + min_loc[0]
        cY_p = y_start + min_loc[1]

        estimators = np.array([[cX_m, cY_m], [cX_w, cY_w], [cX_e, cY_e], [cX_p, cY_p]])
        dists = []
        for i in range(4):
            for j in range(i+1, 4):
                dists.append(np.linalg.norm(estimators[i] - estimators[j]))
        max_spread = float(np.max(dists))

        status = "strong_pass" if max_spread <= config.localization_spread_threshold else "fail"
        score = 1.0 if status == "strong_pass" else 0.2
        return status, score, {"spread": max_spread, "estimators": estimators.tolist()}

class ConfidenceEngine:
    @staticmethod
    def evaluate_candidate(
        candidate: Dict[str, Any],
        session_shots: List[Any],
        lane_config: Any,
        img: np.ndarray,
        timestamp: Optional[float] = None
    ) -> Tuple[str, float, str, Dict[str, Any]]:
        start_time = time.time()
        if timestamp is None:
            timestamp = start_time

        try:
            # Check elapsed time before starting
            if time.time() - start_time > 0.45:
                raise TimeoutError("Execution timed out before starting V&CE pipeline.")

            # Resolve gray and color versions of the image crop
            if len(img.shape) == 2:
                gray_img = img
                color_img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            else:
                gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                color_img = img

            # 1. Duplicate check
            dup_status, dup_info = DuplicateVerifier.evaluate(
                candidate["x_raw"], candidate["y_raw"], timestamp, session_shots, lane_config
            )
            if dup_status == "duplicate":
                return (
                    "REJECTED",
                    0.0,
                    f"DuplicateVerifier: Candidate matches existing Shot #{dup_info['matched_shot_number']} within {dup_info['dist']:.1f}px.",
                    {"duplicate": dup_status}
                )

            if time.time() - start_time > 0.45:
                raise TimeoutError("Execution timed out after duplicate check.")

            # 2. Geometry check
            geom_status, s_geom = GeometryVerifier.evaluate(
                candidate["area"], candidate["circularity"], candidate["solidity"], candidate["aspect_ratio"], lane_config
            )
            is_area_out = not (lane_config.geom_area_loose_min <= candidate["area"] <= lane_config.geom_area_loose_max)
            if (geom_status == "fail" and s_geom <= 0.15) or is_area_out:
                return (
                    "REJECTED",
                    0.0,
                    f"GeometryVerifier: Extreme geometry failure (area={candidate['area']:.1f}, circularity={candidate['circularity']:.2f}, aspect_ratio={candidate['aspect_ratio']:.2f}).",
                    {"geometry": geom_status}
                )

            if time.time() - start_time > 0.45:
                raise TimeoutError("Execution timed out after geometry check.")

            # 3. YOLO check
            # Run YOLO crop logic
            is_verified, yolo_conf, _ = ai_verifier.verify_candidate_roi(
                color_img,
                candidate["x_raw"],
                candidate["y_raw"],
                candidate["diameter_px"],
                circularity=candidate["circularity"],
                solidity=candidate["solidity"],
                aspect_ratio=candidate["aspect_ratio"]
            )
            s_yolo = 1.0 if yolo_conf >= lane_config.yolo_conf_strict else (0.5 if yolo_conf >= lane_config.yolo_conf_loose else 0.0)

            if time.time() - start_time > 0.45:
                raise TimeoutError("Execution timed out after YOLO verification.")

            # 4. Localization check
            contour_data = candidate.get("raw_contour_np")
            if contour_data is None:
                contour_data = candidate.get("raw_contour")
            if contour_data is None:
                raise ValueError("Candidate is missing contour data ('raw_contour_np' or 'raw_contour')")
            loc_status, s_loc, loc_info = LocalizationVerifier.evaluate(contour_data, gray_img, lane_config)

            if time.time() - start_time > 0.45:
                raise TimeoutError("Execution timed out after localization check.")

            # 5. Active Disagreement (CONFLICT)
            is_yolo_strong = yolo_conf >= lane_config.yolo_conf_strict
            is_yolo_fail = yolo_conf < lane_config.yolo_conf_loose
            is_geom_fail = geom_status == "fail"
            is_loc_fail = loc_status == "fail"

            if is_yolo_strong and (is_geom_fail and is_loc_fail):
                spread_val = loc_info.get("spread", -1.0)
                spread_str = f"{spread_val:.1f}px" if spread_val >= 0 else "unknown"
                return (
                    "CONFLICT",
                    0.50,
                    f"Active Disagreement: YOLO strongly verified hole (conf={yolo_conf:.2f}), but CV geometry and localization consensus failed (spread={spread_str}).",
                    {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status}
                )
            if (geom_status == "strong_pass" and loc_status == "strong_pass") and is_yolo_fail:
                return (
                    "CONFLICT",
                    0.50,
                    f"Active Disagreement: CV shape and localization are perfect, but YOLO failed to detect a hole (conf={yolo_conf:.2f}).",
                    {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status}
                )

            # 6. Weighted sum
            w_sum = lane_config.weight_geometry + lane_config.weight_yolo + lane_config.weight_localization
            if w_sum <= 0:
                w_g, w_y, w_l = 0.40, 0.40, 0.20
            else:
                w_g = lane_config.weight_geometry / w_sum
                w_y = lane_config.weight_yolo / w_sum
                w_l = lane_config.weight_localization / w_sum

            raw_score = (w_g * s_geom) + (w_y * s_yolo) + (w_l * s_loc)
            if loc_status == "fail":
                raw_score -= 0.15
            if s_yolo == 0.0:
                raw_score -= 0.10

            fused_score = min(max(raw_score, 0.0), 1.0)
            verdict = "VERIFIED" if fused_score >= lane_config.threshold_verified else "REVIEW"
            explanation = (
                f"Verification score {fused_score:.2f} meets threshold."
                if verdict == "VERIFIED"
                else f"Failed threshold_verified {lane_config.threshold_verified:.2f}. Low scoring modules: geom={s_geom:.2f}, yolo={yolo_conf:.2f}, loc={s_loc:.2f}"
            )
            return (
                verdict,
                fused_score,
                explanation,
                {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status, "spread": loc_info.get("spread")}
            )
        except TimeoutError as te:
            logger.error(f"Confidence Engine: {te}")
            return (
                "REVIEW",
                0.45,
                f"Failsafe triggered: Verifier system execution timed out ({str(te)}). degraded to manual review.",
                {"error": "timeout"}
            )
        except Exception as e:
            logger.error(f"Confidence Engine Failsafe: {e}", exc_info=True)
            return (
                "REVIEW",
                0.45,
                f"Failsafe triggered: Verifier system encountered a processing exception ({type(e).__name__}). degraded to manual review.",
                {"error": str(e)}
            )
