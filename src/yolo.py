import os
import cv2
import time
import socket
import threading
import struct
import numpy as np
from queue import Queue, Empty
from ultralytics import YOLO
from dotenv import load_dotenv

# ================= ENV =================
load_dotenv()
MODEL_PATH = os.getenv("MODEL_PATH")
CONFIDENCE = float(os.getenv("CONFIDENCE", 0.25))

TCP_PORT = int(os.getenv("VIDEO_TCP_PORT", 5005))
LIDAR_PORT = int(os.getenv("LIDAR_UDP_PORT", 6006))

W = int(os.getenv("FRAME_WIDTH", 640))
H = int(os.getenv("FRAME_HEIGHT", 480))
FOV = float(os.getenv("CAMERA_FOV", 90))

FRAME_DENSITY = int(os.getenv("FRAME_DENSITY", 2))
SHOW_WINDOWS = os.getenv("SHOW_WINDOWS", "1") == "1"
WINDOW_NAME = os.getenv("WINDOW_CAMERA", "Unity TCP Stream")

# ================= MODEL =================
model = YOLO(MODEL_PATH)

# ================= QUEUES =================
frame_queue = Queue(maxsize=5)
lidar_queue = Queue(maxsize=20)
lidar_data = {}

# ================= KALMAN TRACKER =================
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

# ================= TCP VIDEO SERVER =================
def handle_client(conn, addr):
    print(f"[TCP] Client connected: {addr}")
    buffer = b""
    payload_size = 4  # 4 байта для длины кадра

    try:
        while True:
            while len(buffer) < payload_size:
                data = conn.recv(4096)
                if not data:
                    return
                buffer += data

            packed_len = buffer[:payload_size]
            buffer = buffer[payload_size:]
            frame_len = struct.unpack('>I', packed_len)[0]

            while len(buffer) < frame_len:
                data = conn.recv(4096)
                if not data:
                    return
                buffer += data

            frame_data = buffer[:frame_len]
            buffer = buffer[frame_len:]

            frame = np.frombuffer(frame_data, dtype=np.uint8).reshape((H, W, 3))
            if not frame_queue.full():
                frame_queue.put(frame)

    except Exception as e:
        print(f"[TCP ERROR] {e}")
    finally:
        conn.close()
        print(f"[TCP] Client disconnected: {addr}")

def tcp_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", TCP_PORT))
    s.listen(5)
    print(f"[TCP] Server listening on port {TCP_PORT}")

    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

# ================= UDP LIDAR RECEIVER =================
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
                continue
            angle_str, dist_str = parts
            angle = int(float(angle_str))
            dist = float(dist_str)
            lidar_data[angle] = dist
        except Exception as e:
            print(f"[LiDAR ERROR] {e}")

# ================= TRACKING =================
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
        if distance:
            cv2.putText(frame, f"{distance:.2f}m", (px, py - 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

# ================= INFERENCE LOOP =================
def inference_loop():
    frame_count = 0
    prev_time = cv2.getTickCount()

    while True:
        try:
            frame = frame_queue.get(timeout=0.01)
        except Empty:
            continue

        frame_count += 1
        if frame_count % FRAME_DENSITY == 0:
            results = model.predict(frame, conf=CONFIDENCE, verbose=False)[0]
            draw(frame, results)

        now = cv2.getTickCount()
        fps = cv2.getTickFrequency() / (now - prev_time)
        prev_time = now
        cv2.putText(frame, f"FPS: {int(fps)}", (20,40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

        if SHOW_WINDOWS:
            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) == ord('q'):
                break

    cv2.destroyAllWindows()

# ================= START =================
if __name__ == "__main__":
    threading.Thread(target=tcp_server, daemon=True).start()
    threading.Thread(target=receive_lidar, daemon=True).start()
    inference_loop()
