import os
import cv2
import time
import socket
import struct
import threading
import numpy as np
from queue import Queue
from ultralytics import YOLO
from dotenv import load_dotenv

# ============== ENV ==============
load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH")
CONFIDENCE = float(os.getenv("CONFIDENCE", 0.25))

VIDEO_PORT = int(os.getenv("VIDEO_TCP_PORT", 5005))   # TCP
LIDAR_PORT = int(os.getenv("LIDAR_UDP_PORT", 6006))   # UDP

W = int(os.getenv("FRAME_WIDTH", 640))
H = int(os.getenv("FRAME_HEIGHT", 480))
FOV = float(os.getenv("CAMERA_FOV", 90))

FRAME_DENSITY = int(os.getenv("FRAME_DENSITY", 2))
SHOW_WINDOWS = os.getenv("SHOW_WINDOWS", "1") == "1"
WINDOW_NAME = os.getenv("WINDOW_CAMERA", "Unity TCP Stream")

# ============== MODEL ==============
model = YOLO(MODEL_PATH)

# ============== QUEUES / STATE ==============
frame_queue = Queue(maxsize=2)
lidar_data = {}

# ============== KALMAN TRACKER ==============
class KalmanTracker:
    def __init__(self, x, y):
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.measurementMatrix = np.array([[1,0,0,0],
                                              [0,1,0,0]], np.float32)
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

        # 🔥 ГАРАНТИРОВАННО РАБОТАЕТ НА ВСЕХ ВЕРСИЯХ OPENCV
        x = int(prediction[0].item())
        y = int(prediction[1].item())

        self.last_prediction = (x, y)
        self.missed += 1
        return self.last_prediction


trackers = {}
next_id = 0

# ============== TCP VIDEO RECEIVER ==============

def recv_exact(sock, size):
    """Читает ровно size байт из TCP, либо возвращает None при разрыве."""
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def receive_video_tcp():
    """Сервер, принимающий JPEG-кадры по TCP от Unity."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", VIDEO_PORT))
    server.listen(1)

    print(f"[VIDEO TCP] Ожидание подключения на порту {VIDEO_PORT}...")
    conn, addr = server.accept()
    print(f"[VIDEO TCP] Подключен клиент: {addr}")

    try:
        while True:
            length_bytes = recv_exact(conn, 4)
            if length_bytes is None:
                break

            frame_len = struct.unpack("<I", length_bytes)[0]
            if frame_len <= 0 or frame_len > 10_000_000:
                print("[VIDEO TCP] Неверная длина кадра")
                break

            jpg_bytes = recv_exact(conn, frame_len)
            if jpg_bytes is None:
                break

            jpg_np = np.frombuffer(jpg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(jpg_np, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            if frame.shape[1] != W or frame.shape[0] != H:
                frame = cv2.resize(frame, (W, H))

            if not frame_queue.full():
                frame_queue.put(frame)

    except Exception as e:
        print(f"[VIDEO TCP ERROR] {e}")
    finally:
        conn.close()
        server.close()
        print("[VIDEO TCP] Сервер остановлен.")

# ============== UDP LIDAR RECEIVER ==============
def receive_lidar():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", LIDAR_PORT))
    print(f"[LiDAR UDP] Слушаем порт {LIDAR_PORT}...")

    while True:
        try:
            msg, _ = sock.recvfrom(1024)
            line = msg.decode().strip()
            if not line:
                continue

            parts = line.split(",")
            if len(parts) != 2:
                continue

            angle = int(float(parts[0]))
            dist = float(parts[1])
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

    for tid, (cx, cy) in assigned.items():
        trackers[tid].correct(cx, cy)

    for tid, tracker in list(trackers.items()):
        px, py = tracker.predict()

        if tracker.missed > 30:
            del trackers[tid]
            continue

        angle = int((px / W - 0.5) * FOV + 180)
        distance = lidar_data.get(angle)

        cv2.circle(frame, (px, py), 6, (0, 0, 255), -1)
        cv2.putText(frame, f"ID {tid}", (px, py - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,255), 2)

        if distance is not None:
            cv2.putText(frame, f"{distance:.2f}m",
                        (px, py - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2)

# ============== INFERENCE LOOP ==============
def inference_loop():
    frame_count = 0

    while True:
        if frame_queue.empty():
            time.sleep(0.001)
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
    print("🚀 YOLO + LiDAR + Kalman Tracking (TCP VIDEO + UDP LiDAR)")

    threading.Thread(target=receive_video_tcp, daemon=True).start()
    threading.Thread(target=receive_lidar, daemon=True).start()

    inference_loop()
    cv2.destroyAllWindows()
