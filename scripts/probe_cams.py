"""Probe camera indices on DSHOW and MSMF backends; save a snapshot for each working one."""
import cv2

backends = [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)]
for name, be in backends:
    for idx in range(4):
        try:
            cap = cv2.VideoCapture(idx, be)
            if not cap.isOpened():
                print(f"{name} index {idx}: not opened")
                cap.release()
                continue
            ok, frame = False, None
            for _ in range(10):
                ok, frame = cap.read()
                if ok and frame is not None:
                    break
            if ok and frame is not None:
                h, w = frame.shape[:2]
                mean = frame.mean()
                snap = f"cam_probe_{name}_{idx}.jpg"
                cv2.imwrite(snap, frame)
                print(f"{name} index {idx}: FRAMES OK {w}x{h} mean_brightness={mean:.0f} -> {snap}")
            else:
                print(f"{name} index {idx}: opened but NO FRAMES")
            cap.release()
        except Exception as e:
            print(f"{name} index {idx}: exception {e}")
