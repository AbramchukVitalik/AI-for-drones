import os
import cv2
from ultralytics import YOLO
from pathlib import Path

# ========= НАСТРОЙКИ =========
MODEL_PATH = r"D:\AI-for-drones\models\best.pt"
INPUT_DIR = r"D:\AI-for-drones\source"
OUTPUT_DIR = r"D:\AI-for-drones\results"

CONF = 0.25
IOU = 0.5
IMG_SIZE = 640
MAX_DET = 1000
# ==============================

image_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
video_ext = {".mp4", ".avi", ".mov", ".mkv", ".wmv"}


def is_image(p: Path):
    return p.suffix.lower() in image_ext


def is_video(p: Path):
    return p.suffix.lower() in video_ext


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def process_image(model, img_path: Path, out_path: Path):
    results = model.predict(
        source=str(img_path),
        conf=CONF,
        iou=IOU,
        imgsz=IMG_SIZE,
        max_det=MAX_DET,
        verbose=False
    )

    annotated = results[0].plot()
    cv2.imwrite(str(out_path), annotated)
    print(f"[IMG] Saved: {out_path}")


def process_video(model, video_path: Path, out_path: Path):
    cap = cv2.VideoCapture(str(video_path))

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.predict(
            source=frame,
            conf=CONF,
            iou=IOU,
            imgsz=IMG_SIZE,
            max_det=MAX_DET,
            verbose=False
        )

        annotated = results[0].plot()
        out.write(annotated)

    cap.release()
    out.release()
    print(f"[VID] Saved: {out_path}")


def main():
    model = YOLO(MODEL_PATH)

    input_dir = Path(INPUT_DIR)
    output_dir = Path(OUTPUT_DIR)
    ensure_dir(output_dir)

    for file_path in input_dir.rglob("*"):
        if not file_path.is_file():
            continue

        relative = file_path.relative_to(input_dir)
        out_path = output_dir / relative
        ensure_dir(out_path.parent)

        if is_image(file_path):
            process_image(model, file_path, out_path)

        elif is_video(file_path):
            out_path = out_path.with_suffix(".mp4")
            process_video(model, file_path, out_path)

        else:
            print(f"[SKIP] {file_path}")


if __name__ == "__main__":
    main()
