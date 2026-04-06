import os
import cv2
import time
import socket
import threading
import numpy as np
from queue import Queue
from ultralytics import YOLO
from dotenv import load_dotenv

# ============== ENV ==============
load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH")
CONFIDENCE = float(os.getenv("CONFIDENCE", 0.25))

VIDEO_PORT = int(os.getenv("VIDEO_UDP_PORT", 5005))
LIDAR_PORT = int(os.getenv("LIDAR_UDP_PORT", 6006))

W = int(os.getenv("FRAME_WIDTH", 640))
H = int(os.getenv("FRAME_HEIGHT", 480))
FOV = float(os.getenv("CAMERA_FOV", 90))

FRAME_DENSITY = int(os.getenv("FRAME_DENSITY", 2))
SHOW_WINDOWS = os.getenv("SHOW_WINDOWS", "1") == "1"
WINDOW_NAME = os.getenv("WINDOW_CAMERA", "Unity Fast Stream")

# ============== MODEL ==============
model = YOLO(MODEL_PATH)

# ============== QUEUES ==============
frame_queue = Queue(maxsize=2)
lidar_data = {}

# ============== KALMAN TRACKER ==============
class KalmanTracker:
    def __init__(self, x, y):
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.measurementMatrix = np.array([[1,0,0,0],[0,1,0,0]], np.float32)
        self.kf.transitionMatrix = np.array([[1,0,1,0],
                                             [0,1,0,1],
                                             [0,0,1,0],
                                             [0,0,0,1]], np.float32)
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * 0.03

        self.kf.statePre = np.array([[x],[y],[0],[0]], np.float32)
        self.last_prediction = (x, y)
        self.missed = 0

    def correct(self, x, y):
        measurement = np.array([[np.float32(x)], [np.float32(y)]])
        self.kf.correct(measurement)
        self.missed = 0

    def predict(self):
        prediction = self.kf.predict()
        x, y = int(prediction[0]), int(prediction[1])
        self.last_prediction = (x, y)
        self.missed += 1
        return self.last_prediction

trackers = {}
next_id = 0

# ============== UDP VIDEO RECEIVER ==============
def receive_video():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", VIDEO_PORT))

    while True:
        data, _ = sock.recvfrom(W * H * 3)
        frame = np.frombuffer(data, dtype=np.uint8).reshape((H, W, 3))
        if not frame_queue.full():
            frame_queue.put(frame)

# ============== UDP LIDAR RECEIVER ==============
def receive_lidar():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LIDAR_PORT))

    while True:
        try:
            msg, _ = sock.recvfrom(1024)
            line = msg.decode().strip()
            if not line:
                continue

            parts = line.split(",")
            if len(parts) != 2:
                continue  # игнорируем неправильный пакет

            angle_str, dist_str = parts
            angle = int(float(angle_str))
            dist = float(dist_str)
            lidar_data[angle] = dist

        except Exception as e:
            print(f"[LiDAR ERROR] {e}")

# ============== TRACKING LOGIC ==============
def assign_detections(detections):
    global next_id
    assigned = {}

    for (cx, cy) in detections:
        best_id = None
        best_dist = 9999

        for tid, tracker in trackers.items():
            px, py = tracker.last_prediction
            dist = np.hypot(cx - px, cy - py)
            if dist < 50 and dist < best_dist:
                best_id = tid
                best_dist = dist

        if best_id is None:
            trackers[next_id] = KalmanTracker(cx, cy)
            assigned[next_id] = (cx, cy)
            next_id += 1
        else:
            assigned[best_id] = (cx, cy)

    return assigned

# ============== DRAW ==============
def draw(frame, results):
    detections = []

    for box in results.boxes.xyxy:
        x1, y1, x2, y2 = map(int, box)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        detections.append((cx, cy))

    assigned = assign_detections(detections)

    # обновляем Kalman
    for tid, (cx, cy) in assigned.items():
        trackers[tid].correct(cx, cy)

    # предсказания всех трекеров
    for tid, tracker in list(trackers.items()):
        px, py = tracker.predict()

        # удаляем потерянные
        if tracker.missed > 30:
            del trackers[tid]
            continue

        angle = int((px / W - 0.5) * FOV + 180)
        distance = lidar_data.get(angle)

        cv2.circle(frame, (px, py), 6, (0, 0, 255), -1)
        cv2.putText(frame, f"ID {tid}", (px, py - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 2)

        if distance:
            cv2.putText(frame, f"{distance:.2f}m",
                        (px, py - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2)

# ============== INFERENCE LOOP ==============
def inference_loop():
    frame_count = 0

    while True:
        if frame_queue.empty():
            continue

        frame = frame_queue.get()
        frame_count += 1

        if frame_count % FRAME_DENSITY == 0:
            results = model.predict(frame, conf=CONFIDENCE, verbose=False)[0]
            draw(frame, results)

        if SHOW_WINDOWS:
            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) == ord('q'):
                break

# ============== START ==============
if __name__ == "__main__":
    print("🚀 YOLO + LiDAR + Kalman Tracking (CPU FAST)")

    threading.Thread(target=receive_video, daemon=True).start()
    threading.Thread(target=receive_lidar, daemon=True).start()

    inference_loop()
