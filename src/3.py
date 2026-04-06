import cv2
import threading
import time
import os
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
import socket
import struct

# ================== LOAD ENV ==================
load_dotenv()

def env_bool(name, default="1"):
    return os.getenv(name, default) == "1"

MODEL_PATH = os.getenv("MODEL_PATH")
CONFIDENCE = float(os.getenv("CONFIDENCE", 0.25))
FRAME_DENSITY = int(os.getenv("FRAME_DENSITY", 3))
CAMERA_FPS_SLEEP = float(os.getenv("CAMERA_FPS_SLEEP", 0.01))
SHOW_WINDOWS = env_bool("SHOW_WINDOWS")

WINDOW_CAMERA = os.getenv("WINDOW_CAMERA", "Drone Camera")

VIDEO_TCP_PORT = int(os.getenv("VIDEO_TCP_PORT", 5005))
LIDAR_UDP_PORT = int(os.getenv("LIDAR_UDP_PORT", 6006))
CAMERA_FOV = float(os.getenv("CAMERA_FOV", 90.0))
LIDAR_OFFSET = float(os.getenv("LIDAR_OFFSET", 0.0))  # <--- ВАЖНО

# ================== BASE CLASS ==================
class DroneBase:
    def __init__(self):
        if not MODEL_PATH:
            raise ValueError("MODEL_PATH не указан в .env")
        self.model = YOLO(MODEL_PATH)
        self.results = None

# ================== CAMERA STREAM FROM UNITY (TCP) ==================
class UnityCameraVision(DroneBase):
    def __init__(self, video_port=5005, lidar_port=6006):
        super().__init__()
        self.running = True
        self.frame = None
        self.lidar_data = {}

        # TCP socket for video
        self.video_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.video_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.video_server.bind(("0.0.0.0", video_port))
        self.video_server.listen(1)

        print(f"[TCP VIDEO] Ожидание подключения Unity...")
        self.video_conn, addr = self.video_server.accept()
        print(f"[TCP VIDEO] Подключено: {addr}")

        # UDP socket for LiDAR
        self.lidar_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.lidar_sock.bind(("0.0.0.0", lidar_port))

    def _recv_exact(self, size):
        data = b""
        while len(data) < size:
            chunk = self.video_conn.recv(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _update_frame(self):
        while self.running:
            try:
                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    continue

                frame_len = struct.unpack("<I", length_bytes)[0]
                if frame_len <= 0 or frame_len > 10_000_000:
                    continue

                jpg_bytes = self._recv_exact(frame_len)
                if not jpg_bytes:
                    continue

                npimg = np.frombuffer(jpg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(npimg, 1)

                if frame is not None:
                    self.frame = frame

            except Exception as e:
                print("[TCP VIDEO ERROR]", e)
                continue

    def _update_lidar(self):
        while self.running:
            try:
                msg, _ = self.lidar_sock.recvfrom(1024)
                angle_str, dist_str = msg.decode().split(",")
                angle = int(float(angle_str)) % 360
                dist = float(dist_str)
                self.lidar_data[angle] = dist
            except:
                continue

    def _run_inference(self):
        count = 0
        while self.running:
            if self.frame is not None:
                count += 1
                if count % FRAME_DENSITY == 0:
                    res = self.model.track(self.frame, persist=True, conf=CONFIDENCE, verbose=False)
                    self.results = res[0]
            time.sleep(CAMERA_FPS_SLEEP)

    def process(self):
        print("🚀 Запуск TCP-видео + UDP-LiDAR...")

        threading.Thread(target=self._update_frame, daemon=True).start()
        threading.Thread(target=self._update_lidar, daemon=True).start()
        threading.Thread(target=self._run_inference, daemon=True).start()

        prev_time = time.time()

        while self.running:
            if self.frame is None:
                continue

            display_frame = self.frame.copy()
            h, w, _ = display_frame.shape

            if self.results is not None:
                display_frame = self.results.plot()

                for box in self.results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0]

                    # углы по краям бокса
                    left_angle  = int(((x1 / w) - 0.5) * CAMERA_FOV + 180 + LIDAR_OFFSET) % 360
                    right_angle = int(((x2 / w) - 0.5) * CAMERA_FOV + 180 + LIDAR_OFFSET) % 360

                    # диапазон углов
                    if left_angle <= right_angle:
                        angles = range(left_angle, right_angle + 1)
                    else:
                        angles = list(range(left_angle, 360)) + list(range(0, right_angle + 1))

                    distances = [self.lidar_data[a] for a in angles if a in self.lidar_data]

                    if distances:
                        distance = min(distances)  # ближайшая точка объекта

                        center_x = int((x1 + x2) / 2)

                        cv2.putText(
                            display_frame,
                            f"{distance:.2f} m",
                            (center_x, int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (0, 0, 255),
                            2
                        )

            fps = 1 / (time.time() - prev_time)
            prev_time = time.time()

            cv2.putText(display_frame, f"FPS: {int(fps)}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            if SHOW_WINDOWS:
                cv2.imshow(WINDOW_CAMERA, display_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False

        self.video_conn.close()
        self.video_server.close()
        self.lidar_sock.close()
        cv2.destroyAllWindows()

# ================== ENTRY POINT ==================
if __name__ == "__main__":
    unity_cam = UnityCameraVision(
        video_port=VIDEO_TCP_PORT,
        lidar_port=LIDAR_UDP_PORT
    )
    unity_cam.process()
