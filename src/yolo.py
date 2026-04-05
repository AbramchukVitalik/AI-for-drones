import cv2
import threading
import time
import os
import numpy as np
from ultralytics import YOLO
from dotenv import load_dotenv
import socket

# ================== LOAD ENV ==================
load_dotenv()

def env_bool(name, default="1"):
    return os.getenv(name, default) == "1"

MODEL_PATH = os.getenv("MODEL_PATH")
CONFIDENCE = float(os.getenv("CONFIDENCE", 0.25))
FRAME_DENSITY = int(os.getenv("FRAME_DENSITY", 3))
CAMERA_FPS_SLEEP = float(os.getenv("CAMERA_FPS_SLEEP", 0.01))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "results")
SHOW_WINDOWS = env_bool("SHOW_WINDOWS")

WINDOW_CAMERA = os.getenv("WINDOW_CAMERA", "Drone Camera")

VIDEO_UDP_PORT = int(os.getenv("VIDEO_UDP_PORT", 5005))
LIDAR_UDP_PORT = int(os.getenv("LIDAR_UDP_PORT", 6006))
CAMERA_FOV = float(os.getenv("CAMERA_FOV", 90.0))  # degrees

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ================== BASE CLASS ==================
class DroneBase:
    def __init__(self):
        if not MODEL_PATH:
            raise ValueError("MODEL_PATH не указан в .env")
        self.model = YOLO(MODEL_PATH)
        self.results = None

# ================== CAMERA STREAM FROM UNITY ==================
class UnityCameraVision(DroneBase):
    def __init__(self, video_port=5005, lidar_port=6006):
        super().__init__()
        self.running = True
        self.frame = None
        self.lidar_data = {}

        # UDP sockets
        self.video_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.video_sock.bind(("0.0.0.0", video_port))

        self.lidar_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.lidar_sock.bind(("0.0.0.0", lidar_port))

    # ================= VIDEO THREAD =================
    def _update_frame(self):
        while self.running:
            try:
                data, _ = self.video_sock.recvfrom(65536)
                npimg = np.frombuffer(data, dtype=np.uint8)
                frame = cv2.imdecode(npimg, 1)
                if frame is not None:
                    self.frame = frame
            except:
                continue

    # ================= LIDAR THREAD =================
    def _update_lidar(self):
        while self.running:
            try:
                msg, _ = self.lidar_sock.recvfrom(1024)
                angle, dist = msg.decode().split(",")
                self.lidar_data[int(float(angle))] = float(dist)
            except:
                continue

    # ================= INFERENCE THREAD =================
    def _run_inference(self):
        count = 0
        while self.running:
            if self.frame is not None:
                count += 1
                if count % FRAME_DENSITY == 0:
                    res = self.model.track(
                        self.frame, persist=True, conf=CONFIDENCE, verbose=False
                    )
                    self.results = res[0]
            time.sleep(CAMERA_FPS_SLEEP)

    # ================= PROCESS =================
    def process(self):
        print("🚀 Запуск стрима Unity + LiDAR...")

        # Start threads
        threading.Thread(target=self._update_frame, daemon=True).start()
        threading.Thread(target=self._update_lidar, daemon=True).start()
        threading.Thread(target=self._run_inference, daemon=True).start()

        prev_time = time.time()

        while self.running:
            if self.frame is None:
                continue

            display_frame = self.frame.copy()
            h, w, _ = display_frame.shape

            # Draw YOLO boxes + calculate distances
            if self.results is not None:
                display_frame = self.results.plot()
                for box in self.results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0]
                    center_x = (x1 + x2) / 2

                    # Convert pixel to angle relative to camera FOV
                    angle = int((center_x / w - 0.5) * CAMERA_FOV + 180)  # adjust 180 if needed

                    # Get lidar distance
                    distance = self.lidar_data.get(angle, None)
                    if distance:
                        cv2.putText(
                            display_frame,
                            f"{distance/1000:.2f} m",
                            (int(center_x), int(y1) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 255),
                            2
                        )

            # Compute FPS
            fps = 1 / (time.time() - prev_time)
            prev_time = time.time()
            cv2.putText(
                display_frame,
                f"FPS: {int(fps)}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            if SHOW_WINDOWS:
                cv2.imshow(WINDOW_CAMERA, display_frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.running = False

        self.video_sock.close()
        self.lidar_sock.close()
        cv2.destroyAllWindows()

# ================== ENTRY POINT ==================
if __name__ == "__main__":
    unity_cam = UnityCameraVision(
        video_port=VIDEO_UDP_PORT,
        lidar_port=LIDAR_UDP_PORT
    )
    unity_cam.process()
