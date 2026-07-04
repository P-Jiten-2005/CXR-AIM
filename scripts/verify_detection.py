"""
Offline regression check for the CXR-AIM detection pipeline.

Runs the full hybrid pipeline (alignment -> difference engine -> YOLO verification)
on a baseline/capture image pair without needing the server or a camera.

Usage:
    python scripts/verify_detection.py <baseline.jpg> <capture.jpg> [--model path/to/best.pt]
"""
import sys
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))

import logging
logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Offline detection pipeline check")
    parser.add_argument("baseline", help="Path to the baseline (before-fire) image")
    parser.add_argument("capture", help="Path to the capture (after-fire) image")
    parser.add_argument("--model", default=None, help="Optional custom YOLO weights (.pt)")
    args = parser.parse_args()

    from app.services.cv_engine import cv_engine
    from app.services.ai_verifier import ai_verifier

    if args.model:
        ai_verifier.load_model(args.model)

    print("=== Detection run (no existing shots) ===")
    holes = cv_engine.detect_holes(args.baseline, args.capture, existing_shots=[], align=True)
    for h in holes:
        print(f"  hole ({h['x_raw']:.1f}, {h['y_raw']:.1f}) dia={h['diameter_px']:.1f}px "
              f"conf={h['confidence']:.2f} circ={h['circularity']:.2f} "
              f"method={h['verification_method']}")
    print(f"  -> {len(holes)} new hole(s)")

    print("\n=== Dedup check: re-run with detected shots as existing (expect 0) ===")
    existing = [{"x_raw": h["x_raw"], "y_raw": h["y_raw"], "diameter_px": h["diameter_px"]} for h in holes]
    again = cv_engine.detect_holes(args.baseline, args.capture, existing_shots=existing, align=True)
    print(f"  -> {len(again)} new hole(s)")

    print("\n=== Stability check: baseline vs itself (expect 0) ===")
    self_run = cv_engine.detect_holes(args.baseline, args.baseline, existing_shots=[], align=True)
    print(f"  -> {len(self_run)} new hole(s)")


if __name__ == "__main__":
    main()
