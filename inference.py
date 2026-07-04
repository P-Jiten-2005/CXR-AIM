import os
import sys
import json
import argparse
import cv2
import numpy as np
import time
from pathlib import Path
from typing import List, Dict, Any

# Add backend directory to sys.path to allow app imports
sys.path.append(str(Path(__file__).parent / "backend"))

logging_level = os.environ.get("LOG_LEVEL", "WARNING")
import logging
logging.basicConfig(level=getattr(logging, logging_level))
logger = logging.getLogger("inference_cli")

try:
    from app.services.cv_engine import CVEngine
    from app.services.ai_verifier import AIVerifier
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    IMPORTS_SUCCESSFUL = False
    logger.error(f"Failed to import app services: {e}. Ensure requirements.txt is installed.")

def draw_visualizations(img: np.ndarray, detections: List[Dict[str, Any]]) -> np.ndarray:
    """Helper to draw detection bounding circles and text labels on the image."""
    visualized = img.copy()
    for det in detections:
        cx = int(det["center_x"])
        cy = int(det["center_y"])
        d = int(det["diameter"])
        conf = det["confidence"]
        method = det["verification_method"]
        hid = det["hole_id"]
        
        # Color depending on verification level
        if "sahi" in method:
            color = (0, 255, 0) # Bright green for SAHI
        elif "yolov8" in method:
            color = (255, 100, 0) # Orange/Cyan for standard YOLO
        else:
            color = (0, 0, 255) # Red for raw OpenCV fallback
            
        cv2.circle(visualized, (cx, cy), max(d // 2, 5), color, 2)
        cv2.putText(
            visualized, 
            f"#{hid} ({conf:.2f}) {method.split('+')[-1]}", 
            (cx + 8, cy - 8), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.4, 
            color, 
            1, 
            cv2.LINE_AA
        )
    return visualized

def run_hybrid_pipeline(
    cv_engine: CVEngine, 
    ai_verifier: AIVerifier, 
    baseline_path: str, 
    current_path: str,
    sahi: bool = False
) -> List[Dict[str, Any]]:
    """Runs the full OpenCV Difference + YOLOv8 + SAHI hybrid pipeline."""
    # We pass an empty list of existing shots to detect all holes
    raw_holes = cv_engine.detect_holes(
        baseline_path=baseline_path,
        current_path=current_path,
        existing_shots=[],
        align=True,
        sahi=sahi
    )
    
    formatted_detections = []
    for idx, hole in enumerate(raw_holes):
        formatted_detections.append({
            "hole_id": idx + 1,
            "center_x": int(round(hole["x_raw"])),
            "center_y": int(round(hole["y_raw"])),
            "diameter": int(round(hole["diameter_px"])),
            "confidence": float(round(hole["confidence"], 2)),
            "verification_method": hole["verification_method"]
        })
    return formatted_detections

def handle_single_image(
    baseline_path: str, 
    image_path: str, 
    weights_path: str = None, 
    sahi: bool = False,
    output_dir: str = None
):
    """Executes detection on a single image and prints JSON to stdout."""
    cv_engine = CVEngine()
    ai_verifier = AIVerifier(weights_path)
    
    # We must patch the global singleton if a custom weights path was provided
    if weights_path:
        from app.services.ai_verifier import ai_verifier as verifier_singleton
        verifier_singleton.load_model(weights_path)

    try:
        detections = run_hybrid_pipeline(cv_engine, ai_verifier, baseline_path, image_path, sahi)
        
        # Output JSON result
        print(json.dumps(detections, indent=2))
        
        # Save visualization if requested
        if output_dir:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            
            img = cv2.imread(image_path)
            if img is not None:
                vis = draw_visualizations(img, detections)
                save_file = out_path / f"detected_{Path(image_path).name}"
                cv2.imwrite(str(save_file), vis)
                logger.info(f"Saved visualization overlay to {save_file}")
                
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

def handle_folder(
    baseline_path: str, 
    folder_path: str, 
    weights_path: str = None, 
    sahi: bool = False,
    output_dir: str = None
):
    """Processes all images in a directory against a single baseline image."""
    cv_engine = CVEngine()
    ai_verifier = AIVerifier(weights_path)
    
    if weights_path:
        from app.services.ai_verifier import ai_verifier as verifier_singleton
        verifier_singleton.load_model(weights_path)
        
    folder = Path(folder_path)
    if not folder.exists():
        print(json.dumps({"error": f"Folder {folder_path} does not exist"}), file=sys.stderr)
        sys.exit(1)
        
    results = {}
    valid_extensions = [".jpg", ".jpeg", ".png"]
    
    for item in folder.iterdir():
        if item.suffix.lower() in valid_extensions and item.name != Path(baseline_path).name:
            try:
                detections = run_hybrid_pipeline(cv_engine, ai_verifier, baseline_path, str(item), sahi)
                results[item.name] = detections
                
                if output_dir:
                    out_path = Path(output_dir)
                    out_path.mkdir(parents=True, exist_ok=True)
                    img = cv2.imread(str(item))
                    if img is not None:
                        vis = draw_visualizations(img, detections)
                        cv2.imwrite(str(out_path / f"detected_{item.name}"), vis)
            except Exception as e:
                results[item.name] = {"error": str(e)}
                
    print(json.dumps(results, indent=2))

def handle_live_feed(
    source_index: int = 0, 
    weights_path: str = None, 
    sahi: bool = False
):
    """Starts interactive camera stream for live target difference checks."""
    cv_engine = CVEngine()
    ai_verifier = AIVerifier(weights_path)
    
    if weights_path:
        from app.services.ai_verifier import ai_verifier as verifier_singleton
        verifier_singleton.load_model(weights_path)

    cap = cv2.VideoCapture(source_index)
    if not cap.isOpened():
        print(f"Error: Could not open camera source {source_index}", file=sys.stderr)
        sys.exit(1)
        
    print("--------------------------------------------------")
    print("CXR-AIM Live Target Inference Engine")
    print("Instructions:")
    print("  Press 'b' - Capture clean baseline target image (Do this first!)")
    print("  Press 'd' - Trigger Difference Detection check")
    print("  Press 'q' - Quit stream")
    print("--------------------------------------------------")
    
    baseline_img = None
    baseline_temp_path = "temp_baseline_inference.jpg"
    current_temp_path = "temp_current_inference.jpg"
    
    detections = []
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab camera frame.", file=sys.stderr)
                break
                
            display_frame = frame.copy()
            
            # Draw overlay depending on state
            if baseline_img is None:
                cv2.putText(display_frame, "STATUS: Awaiting Baseline Calibration (Press 'b')", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            else:
                cv2.putText(display_frame, "STATUS: Active Difference Engine (Press 'd' to detect)", (20, 40), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                # Draw last detected spots
                display_frame = draw_visualizations(display_frame, detections)
                
            cv2.imshow("CXR-AIM Target Detection System", display_frame)
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                break
            elif key == ord('b'):
                baseline_img = frame.copy()
                cv2.imwrite(baseline_temp_path, baseline_img)
                print("Captured and saved baseline reference target!")
            elif key == ord('d'):
                if baseline_img is None:
                    print("Error: Capture baseline target reference first using 'b'!")
                    continue
                    
                cv2.imwrite(current_temp_path, frame)
                print("Triggering difference engine + AI verification check...")
                start_t = time.time()
                try:
                    detections = run_hybrid_pipeline(
                        cv_engine, ai_verifier, baseline_temp_path, current_temp_path, sahi
                    )
                    elapsed = time.time() - start_t
                    print(f"Check finished in {elapsed:.3f} seconds. Detected {len(detections)} holes:")
                    print(json.dumps(detections, indent=2))
                except Exception as e:
                    print(f"Pipeline error: {e}", file=sys.stderr)
                    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        # Clean up temp files
        for f in [baseline_temp_path, current_temp_path]:
            if os.path.exists(f):
                os.remove(f)

def main():
    if not IMPORTS_SUCCESSFUL:
        print(json.dumps({"error": "Dependency imports failed. Run launcher setup first."}), file=sys.stderr)
        sys.exit(1)
        
    parser = argparse.ArgumentParser(description="CXR-AIM Inference CLI Pipeline")
    parser.add_argument("--mode", type=str, required=True, choices=["image", "folder", "webcam", "live"],
                        help="Inference mode: single image, directory search, or live feed")
    parser.add_argument("--input", type=str, default=None,
                        help="Input file image path, folder directory, or webcam index")
    parser.add_argument("--baseline", type=str, default=None,
                        help="Baseline target image reference path (required for image/folder modes)")
    parser.add_argument("--weights", type=str, default=None,
                        help="Optional custom trained YOLOv8 weights best.pt file")
    parser.add_argument("--sahi", action="store_true",
                        help="Force SAHI sliced verification")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Folder path to save visual overlay outputs")
                        
    args = parser.parse_args()
    
    if args.mode == "image":
        if not args.input or not args.baseline:
            parser.error("--mode=image requires both --input and --baseline parameters.")
        handle_single_image(args.baseline, args.input, args.weights, args.sahi, args.output_dir)
        
    elif args.mode == "folder":
        if not args.input or not args.baseline:
            parser.error("--mode=folder requires both --input and --baseline parameters.")
        handle_folder(args.baseline, args.input, args.weights, args.sahi, args.output_dir)
        
    elif args.mode in ["webcam", "live"]:
        source = 0
        if args.input:
            try:
                source = int(args.input)
            except ValueError:
                pass
        handle_live_feed(source, args.weights, args.sahi)

if __name__ == "__main__":
    main()
