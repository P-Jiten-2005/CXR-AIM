### Task 3: Implement V&CE Verifier & Fusion Engine

**Files:**
- Create: `backend/app/services/confidence_engine.py`
- Create: `backend/tests/test_confidence_engine.py`

**Interfaces:**
- Consumes: `ai_verifier.verify_candidate_roi` from `app.services.ai_verifier`
- Produces: `confidence_engine.evaluate_candidate(candidate, session_shots, lane_config, img)` returning `(verdict, score, explanation, signals_dict)`.

- [ ] **Step 1: Write the failing test**
  Create `backend/tests/test_confidence_engine.py` testing verifier scores, hard gates, active disagreement, and failsafe behavior:
  ```python
  import unittest
  import numpy as np
  from app.services.confidence_engine import ConfidenceEngine, GeometryVerifier, DuplicateVerifier, LocalizationVerifier
  from app.schemas.schemas import LaneConfigBase

  class TestConfidenceEngine(unittest.TestCase):
      def test_geometry_verifier(self):
          config = LaneConfigBase()
          # Test strong pass
          result = GeometryVerifier.evaluate(200.0, 0.8, 0.95, 1.0, config)
          self.assertEqual(result, ("strong_pass", 1.0))
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_confidence_engine.py`
  Expected: FAIL (module not found).

- [ ] **Step 3: Implement verifiers and fusion logic in confidence_engine.py**
  Write the logic for `GeometryVerifier`, `DuplicateVerifier`, `LocalizationVerifier`, and `ConfidenceEngine` exactly as defined in the design spec:
  ```python
  import numpy as np
  import cv2
  import logging
  from typing import Tuple, Dict, Any, List

  logger = logging.getLogger("app.confidence_engine")

  class GeometryVerifier:
      @staticmethod
      def evaluate(area: float, circularity: float, solidity: float, aspect_ratio: float, config: Any) -> Tuple[str, float]:
          scores = []
          # Circularity
          if config.geom_circ_strict <= circularity <= 1.0:
              scores.append(1.0)
          elif config.geom_circ_loose <= circularity < config.geom_circ_strict:
              scores.append(0.5)
          else:
              scores.append(0.0)

          # Solidity
          if 0.80 <= solidity <= 1.0: # strict
              scores.append(1.0)
          elif 0.65 <= solidity < 0.80: # loose
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
          is_fail = any(s == 0.0 for s in scores) or not (config.geom_area_loose_min <= area <= config.geom_area_loose_max)
          
          if is_fail:
              return "fail", geom_score
          elif all(s == 1.0 for s in scores):
              return "strong_pass", geom_score
          else:
              return "weak_pass", geom_score

  class DuplicateVerifier:
      @staticmethod
      def evaluate(cX: float, cY: float, timestamp: float, verified_shots: List[Dict[str, Any]], config: Any) -> Tuple[str, Dict[str, Any]]:
          for s in verified_shots:
              dist = np.sqrt((cX - s["x_raw"])**2 + (cY - s["y_raw"])**2)
              t_diff = abs(timestamp - s.get("created_at_ts", timestamp))
              if dist <= config.duplicate_radius_px and t_diff <= config.duplicate_time_window_sec:
                  return "duplicate", {"matched_shot_number": s["shot_number"], "dist": dist, "shot_id": s.get("id")}
          return "neutral", {}

  class LocalizationVerifier:
      @staticmethod
      def evaluate(c: np.ndarray, gray_img: np.ndarray, config: Any) -> Tuple[str, float, Dict[str, Any]]:
          # 1. Moment based centroid
          M = cv2.moments(c)
          if M["m00"] == 0:
              return "fail", 0.0, {"error": "zero moments"}
          cX_m = M["m10"] / M["m00"]
          cY_m = M["m01"] / M["m00"]

          # 2. Intensity-weighted centroid
          x, y, w, h = cv2.boundingRect(c)
          roi = gray_img[y:y+h, x:x+w]
          y_indices, x_indices = np.indices(roi.shape)
          weights = 255.0 - roi.astype(np.float32) # Darker pixels are bullet hole interiors -> higher weight
          total_w = weights.sum()
          if total_w > 0:
              cX_w = x + (x_indices * weights).sum() / total_w
              cY_w = y + (y_indices * weights).sum() / total_w
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
          cX_p = x + min_loc[0]
          cY_p = y + min_loc[1]

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
          verified_shots: List[Dict[str, Any]],
          config: Any,
          gray_img: np.ndarray,
          ai_verifier: Any,
          timestamp: float
      ) -> Tuple[str, float, str, Dict[str, Any]]:
          try:
              # 1. Duplicate check
              dup_status, dup_info = DuplicateVerifier.evaluate(candidate["x_raw"], candidate["y_raw"], timestamp, verified_shots, config)
              if dup_status == "duplicate":
                  return "REJECTED", 0.0, f"DuplicateVerifier: Candidate matches existing Shot #{dup_info['matched_shot_number']} within {dup_info['dist']:.1f}px.", {"duplicate": dup_status}

              # 2. Geometry check
              geom_status, s_geom = GeometryVerifier.evaluate(
                  candidate["area"], candidate["circularity"], candidate["solidity"], candidate["aspect_ratio"], config
              )
              if geom_status == "fail" and s_geom <= 0.15:
                  return "REJECTED", 0.0, f"GeometryVerifier: Extreme geometry failure (area={candidate['area']:.1f}, circularity={candidate['circularity']:.2f}, aspect_ratio={candidate['aspect_ratio']:.2f}).", {"geometry": geom_status}

              # 3. YOLO check
              # Run YOLO crop logic
              is_verified, yolo_conf, _ = ai_verifier.verify_candidate_roi(
                  cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR), candidate["x_raw"], candidate["y_raw"], candidate["diameter_px"]
              )
              s_yolo = 1.0 if yolo_conf >= config.yolo_conf_strict else (0.5 if yolo_conf >= config.yolo_conf_loose else 0.0)

              # 4. Localization check
              loc_status, s_loc, loc_info = LocalizationVerifier.evaluate(np.array(candidate["raw_contour_np"]), gray_img, config)

              # 5. Active Disagreement (CONFLICT)
              is_yolo_strong = yolo_conf >= config.yolo_conf_strict
              is_yolo_fail = yolo_conf < config.yolo_conf_loose
              is_geom_fail = geom_status == "fail"
              is_loc_fail = loc_status == "fail"

              if is_yolo_strong and (is_geom_fail and is_loc_fail):
                  return "CONFLICT", 0.50, f"Active Disagreement: YOLO strongly verified hole (conf={yolo_conf:.2f}), but CV geometry and localization consensus failed (spread={loc_info['spread']:.1f}px).", {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status}
              if (geom_status == "strong_pass" and loc_status == "strong_pass") and is_yolo_fail:
                  return "CONFLICT", 0.50, f"Active Disagreement: CV shape and localization are perfect, but YOLO failed to detect a hole (conf={yolo_conf:.2f}).", {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status}

              # 6. Weighted sum
              w_sum = config.weight_geometry + config.weight_yolo + config.weight_localization
              w_g = config.weight_geometry / w_sum
              w_y = config.weight_yolo / w_sum
              w_l = config.weight_localization / w_sum

              raw_score = (w_g * s_geom) + (w_y * s_yolo) + (w_l * s_loc)
              if loc_status == "fail":
                  raw_score -= 0.15
              if s_yolo == 0.0:
                  raw_score -= 0.10

              fused_score = min(max(raw_score, 0.0), 1.0)
              verdict = "VERIFIED" if fused_score >= config.threshold_verified else "REVIEW"
              explanation = f"Verification score {fused_score:.2f} meets threshold." if verdict == "VERIFIED" else f"Failed threshold_verified {config.threshold_verified:.2f}. Low scoring modules: geom={s_geom:.2f}, yolo={yolo_conf:.2f}, loc={s_loc:.2f}"
              return verdict, fused_score, explanation, {"geometry": geom_status, "yolo": yolo_conf, "localization": loc_status, "spread": loc_info.get("spread")}
          except Exception as e:
              logger.error(f"Confidence Engine Failsafe: {e}", exc_info=True)
              return "REVIEW", 0.45, f"Failsafe triggered: Verifier system encountered a processing exception ({type(e).__name__}). degraded to manual review.", {"error": str(e)}
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `./venv/Scripts/python.exe -m unittest backend/tests/test_confidence_engine.py`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add backend/app/services/confidence_engine.py backend/tests/test_confidence_engine.py
  git commit -m "feat: implement V&CE verifiers and ConfidenceEngine fusion layer"
  ```

---

