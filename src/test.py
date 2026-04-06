import socket
import struct
import threading
import math
import numpy as np
import cv2
from ultralytics import YOLO

# -----------------------------
# НАСТРОЙКИ
# -----------------------------

HOST = '0.0.0.0'
CAM_PORT = 5005
LIDAR_PORT = 6006

WIDTH = 640
HEIGHT = 480
CHANNELS = 3

CAMERA_FOV_Y_DEG = 90.0
CAMERA_YAW_OFFSET_DEG = 0.0

MODEL_PATH = "../models/best.pt"

# Максимальная дальность лидара (м)
MAX_LIDAR_DISTANCE = 50.0

# -----------------------------
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# -----------------------------

latest_frame = None
frame_lock = threading.Lock()

latest_lidar = {}
lidar_lock = threading.Lock()

model = YOLO(MODEL_PATH)

# -----------------------------
# ЦВЕТА ДЛЯ КЛАССОВ
# -----------------------------

CLASS_COLORS = {
    "person": (0, 255, 0),
    "car": (0, 128, 255),
    "truck": (0, 0, 255),
    "power_line": (255, 255, 0),
    "tree": (0, 255, 255),
    "building": (255, 0, 255),
}

def get_color_for_class(label: str):
    if label in CLASS_COLORS:
        return CLASS_COLORS[label]
    h = abs(hash(label)) % 255
    return (h, 255 - h, (h * 2) % 255)

# -----------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -----------------------------

def recv_exact(conn, n):
    data = b''
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def parse_lidar_line(text):
    parts = text.split(",")
    angle = int(parts[0])
    if len(parts) == 3:
        dist = float(parts[1] + "." + parts[2])
    else:
        dist = float(parts[1])
    return angle, dist

def get_distance_from_lidar(box, lidar_data, W, H, fov_y_deg, camera_yaw_offset_deg=0.0):
    if not lidar_data:
        return None

    x1, y1, x2, y2 = box
    x_center = (x1 + x2) / 2.0

    aspect = W / H
    fov_y = math.radians(fov_y_deg)
    fov_x = 2.0 * math.atan(math.tan(fov_y / 2.0) * aspect)
    fov_x_deg = math.degrees(fov_x)

    nx = (x_center - W / 2.0) / (W / 2.0)
    theta_cam = nx * (fov_x_deg / 2.0)

    theta_lidar = (theta_cam + camera_yaw_offset_deg) % 360.0
    theta_lidar_int = int(round(theta_lidar)) % 360

    return lidar_data.get(theta_lidar_int, None)

# -----------------------------
# НАДЁЖНЫЙ TCP-СЕРВЕР КАМЕРЫ
# -----------------------------

def camera_server():
    global latest_frame

    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, CAM_PORT))
                s.listen(1)
                print(f"[CAM] Waiting for connection on {HOST}:{CAM_PORT}")

                conn, addr = s.accept()
                print(f"[CAM] Connected from {addr}")

                with conn:
                    while True:
                        header = recv_exact(conn, 4)
                        if header is None:
                            print("[CAM] Lost connection")
                            break

                        (size,) = struct.unpack('>I', header)
                        data = recv_exact(conn, size)
                        if data is None:
                            print("[CAM] Lost connection")
                            break

                        frame_rgb = np.frombuffer(data, dtype=np.uint8).reshape((HEIGHT, WIDTH, CHANNELS))
                        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                        frame_bgr = cv2.flip(frame_bgr, 0)

                        with frame_lock:
                            latest_frame = frame_bgr

        except Exception as e:
            print(f"[CAM] Server error: {e}")

# -----------------------------
# НАДЁЖНЫЙ TCP-СЕРВЕР ЛИДАРА
# -----------------------------

def lidar_server():
    global latest_lidar

    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((HOST, LIDAR_PORT))
                s.listen(1)
                print(f"[LIDAR] Waiting for connection on {HOST}:{LIDAR_PORT}")

                conn, addr = s.accept()
                print(f"[LIDAR] Connected from {addr}")

                with conn:
                    buffer = b""
                    while True:
                        chunk = conn.recv(1024)
                        if not chunk:
                            print("[LIDAR] Lost connection")
                            break

                        buffer += chunk

                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            try:
                                text = line.decode('ascii').strip()
                                if not text:
                                    continue

                                angle, dist = parse_lidar_line(text)

                                with lidar_lock:
                                    latest_lidar[angle] = dist

                            except Exception as e:
                                print(f"[LIDAR] Parse error: {e}, line={line!r}")

        except Exception as e:
            print(f"[LIDAR] Server error: {e}")

# -----------------------------
# ОСНОВНОЙ ЦИКЛ YOLO + ВИЗУАЛИЗАЦИЯ
# -----------------------------

def main_loop():
    while True:
        with frame_lock:
            frame = None if latest_frame is None else latest_frame.copy()

        if frame is None:
            if cv2.waitKey(1) & 0xFF == 27:
                break
            continue

        results = model(frame, verbose=False)

        if len(results) > 0:
            r = results[0]
            boxes = r.boxes

            with lidar_lock:
                lidar_snapshot = dict(latest_lidar)

            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                label = model.names[cls_id]

                dist = get_distance_from_lidar(
                    [x1, y1, x2, y2],
                    lidar_snapshot,
                    WIDTH,
                    HEIGHT,
                    CAMERA_FOV_Y_DEG,
                    CAMERA_YAW_OFFSET_DEG
                )

                # -----------------------------
                # ЛОГИКА МАКСИМАЛЬНОЙ ДАЛЬНОСТИ
                # -----------------------------
                if dist is None:
                    dist_text = f">{MAX_LIDAR_DISTANCE:.0f} m"
                else:
                    if dist > MAX_LIDAR_DISTANCE:
                        dist_text = f">{MAX_LIDAR_DISTANCE:.0f} m"
                    else:
                        dist_text = f"{dist:.2f} m"

                color = get_color_for_class(label)

                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)

                text = f"{label} {conf:.2f} | {dist_text}"

                cv2.putText(frame, text, (int(x1), int(y1) - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        cv2.imshow("YOLO + Lidar", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

    cv2.destroyAllWindows()

# -----------------------------
# ЗАПУСК
# -----------------------------

if __name__ == "__main__":
    cam_thread = threading.Thread(target=camera_server, daemon=True)
    lidar_thread = threading.Thread(target=lidar_server, daemon=True)

    cam_thread.start()
    lidar_thread.start()

    main_loop()
