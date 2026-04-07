import socket
import struct
import threading
import math
import time
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
MAX_LIDAR_DISTANCE = 50.0

CLASS_COLORS = {
    "cattle": (0, 255, 255),      # желтый
    "fallen_tree": (0, 255, 0),   # зеленый
    "human": (255, 0, 0),         # синий
    "power_line": (255, 0, 255),  # пурпурный
    "tractor": (0, 0, 255),       # красный
}

# --- НАСТРОЙКИ ТРЕКИНГА ---
# Классы, для которых будет применяться прогнозирование Калмана
CLASSES_TO_TRACK = ["human", "tractor", "cattle"]
MAX_MISSED_FRAMES = 15  # Сколько кадров помним объект, если YOLO его не видит
MAX_TRACK_DIST = 100.0  # Макс. дистанция в пикселях для связывания бокса и трекера

def get_color_for_class(label: str):
    if label in CLASS_COLORS:
        return CLASS_COLORS[label]
    h = abs(hash(label)) % 255
    return (h, 255 - h, (h * 2) % 255)

def recv_exact(conn, n):
    """Оригинальная функция приема точного количества байт (без изменений)"""
    data = b''
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def parse_lidar_line(text):
    """Оригинальная функция парсинга строки лидара (без изменений)"""
    parts = text.split(",")
    angle = int(parts[0])
    if len(parts) == 3:
        dist = float(parts[1] + "." + parts[2])
    else:
        dist = float(parts[1])
    return angle, dist


# -----------------------------
# КЛАСС ФИЛЬТРА КАЛМАНА
# -----------------------------

class KalmanTracker:
    def init(self, track_id, box, label, dist):
        self.track_id = track_id
        self.label = label
        
        # Состояние: [cx, cy, dx, dy]
        # Измерения: [cx, cy]
        self.kf = cv2.KalmanFilter(4, 2)
        
        # Матрица измерений
        self.kf.measurementMatrix = np.array([[1, 0, 0, 0], 
                                              [0, 1, 0, 0]], np.float32)
        
        # Матрица переходов (dt = 1)
        self.kf.transitionMatrix = np.array([[1, 0, 1, 0], 
                                             [0, 1, 0, 1], 
                                             [0, 0, 1, 0], 
                                             [0, 0, 0, 1]], np.float32)
        
        # Ковариация шума процесса
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * 0.03
        
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        
        self.kf.statePre = np.array([[cx], [cy], [0], [0]], np.float32)
        self.kf.statePost = np.array([[cx], [cy], [0], [0]], np.float32)
        
        self.width = box[2] - box[0]
        self.height = box[3] - box[1]
        self.last_dist = dist
        
        self.missed_frames = 0
        self.predicted_box = box

    def predict(self):
        pred = self.kf.predict()
        cx, cy = pred[0][0], pred[1][0]
        
        # Обновляем predicted_box на основе предсказанного центра
        x1 = cx - self.width / 2
        y1 = cy - self.height / 2
        x2 = cx + self.width / 2
        y2 = cy + self.height / 2
        self.predicted_box = [x1, y1, x2, y2]
        
        self.missed_frames += 1
        return cx, cy

    def update(self, box, dist):
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        
        # Корректируем фильтр новым измерением
        self.kf.correct(np.array([[np.float32(cx)], [np.float32(cy)]]))
        
        self.width = box[2] - box[0]
        self.height = box[3] - box[1]
        
        if dist is not None:
            self.last_dist = dist
            
        self.missed_frames = 0


# -----------------------------
# ООП АРХИТЕКТУРА СЕРВЕРА
# -----------------------------
class SensorFusionNode:
    def init(self):
        self.model = YOLO(MODEL_PATH)
        self.fov_x_deg = self._calculate_fov_x()
        
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.frame_event = threading.Event()
        
        self.latest_lidar = {}
        self.lidar_lock = threading.Lock()
        self.last_lidar_time = time.time()
        
        # Трекинг
        self.trackers = {} # track_id -> KalmanTracker
        self.next_track_id = 1

    def _calculate_fov_x(self):
        aspect = WIDTH / HEIGHT
        fov_y = math.radians(CAMERA_FOV_Y_DEG)
        fov_x = 2.0 * math.atan(math.tan(fov_y / 2.0) * aspect)
        return math.degrees(fov_x)

    def camera_server(self):
        """Оригинальная логика TCP-сервера камеры"""
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
                            if header is None: break

                            (size,) = struct.unpack('>I', header)
                            data = recv_exact(conn, size)
                            if data is None: break

                            frame_rgb = np.frombuffer(data, dtype=np.uint8).reshape((HEIGHT, WIDTH, CHANNELS))
                            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                            frame_bgr = cv2.flip(frame_bgr, 0)

                            with self.frame_lock:
                                self.latest_frame = frame_bgr
                            self.frame_event.set()

            except Exception as e:
                print(f"[CAM] Server error: {e}")
                time.sleep(1)

    def lidar_server(self):
        """Оригинальная логика TCP-сервера лидара"""
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
                            if not chunk: break

                            buffer += chunk
                            while b"\n" in buffer:
                                line, buffer = buffer.split(b"\n", 1)
                                try:
                                    text = line.decode('ascii').strip()
                                    if not text: continue

                                    angle, dist = parse_lidar_line(text)

                                    with self.lidar_lock:
                                        current_time = time.time()
                                        if current_time - self.last_lidar_time > 2.0:
                                            self.latest_lidar.clear()
                                        
                                        self.latest_lidar[angle] = dist
                                        self.last_lidar_time = current_time
                                except Exception:
                                    pass

            except Exception as e:
                print(f"[LIDAR] Server error: {e}")
                time.sleep(1)

    def get_distance_from_lidar(self, box, lidar_data):
        if not lidar_data: return None
        x1, y1, x2, y2 = box
        x_center = (x1 + x2) / 2.0

        nx = (x_center - WIDTH / 2.0) / (WIDTH / 2.0)
        theta_cam = nx * (self.fov_x_deg / 2.0)

        theta_lidar = (theta_cam + CAMERA_YAW_OFFSET_DEG) % 360.0
        theta_lidar_int = int(round(theta_lidar)) % 360

        return lidar_data.get(theta_lidar_int, None)
        
    def _format_dist(self, dist):
        if dist is None or dist > MAX_LIDAR_DISTANCE:
            return f">{MAX_LIDAR_DISTANCE:.0f}m"
        return f"{dist:.2f}m"

    def run(self):
        threading.Thread(target=self.camera_server, daemon=True).start()
        threading.Thread(target=self.lidar_server, daemon=True).start()

        while True:
            if not self.frame_event.wait(timeout=0.1):
                if cv2.waitKey(1) & 0xFF == 27: break
                continue
            
            self.frame_event.clear()

            with self.frame_lock:
                frame = self.latest_frame.copy()

            results = self.model(frame, verbose=False)
            
            with self.lidar_lock:
                lidar_snapshot = dict(self.latest_lidar)

            current_detections = [] # Храним детекции классов, подлежащих трекингу

            if len(results) > 0:
                r = results[0]
                
                # 1. Сначала обрабатываем все детекции от YOLO
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    label = self.model.names[cls_id]
                    dist = self.get_distance_from_lidar([x1, y1, x2, y2], lidar_snapshot)

                    if label in CLASSES_TO_TRACK:
                        # Сохраняем для сопоставления с Калманом
                        cx = (x1 + x2) / 2.0
                        cy = (y1 + y2) / 2.0
                        current_detections.append({
                            'box': [x1, y1, x2, y2], 'center': (cx, cy),
                            'label': label, 'conf': conf, 'dist': dist, 'matched': False
                        })
                    else:
                        # Если класс не отслеживается, просто рисуем обычный бокс
                        color = get_color_for_class(label)
                        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        text = f"{label} {conf:.2f} | {self._format_dist(dist)}"
                        cv2.putText(frame, text, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # 2. ПРОГНОЗИРОВАНИЕ (Kalman Predict)
            for t_id, tracker in list(self.trackers.items()):
                tracker.predict()
                
            # 3. СОПОСТАВЛЕНИЕ (Data Association - жадный алгоритм по дистанции)
            for det in current_detections:
                best_match_id = None
                best_dist = MAX_TRACK_DIST
                
                for t_id, tracker in self.trackers.items():
                    if tracker.label != det['label']: continue
                    
                    # Дистанция между центрами
                    tcx, tcy = (tracker.predicted_box[0] + tracker.predicted_box[2])/2, (tracker.predicted_box[1] + tracker.predicted_box[3])/2
                    dist = math.hypot(tcx - det['center'][0], tcy - det['center'][1])
                    
                    if dist < best_dist:
                        best_dist = dist
                        best_match_id = t_id
                
                if best_match_id is not None:
                    # Нашли существующий трек
                    self.trackers[best_match_id].update(det['box'], det['dist'])
                    det['matched'] = True
                    # Рисуем обновленный бокс с ID
                    color = get_color_for_class(det['label'])
                    x1, y1, x2, y2 = det['box']
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    text = f"ID:{best_match_id} {det['label']} | {self._format_dist(det['dist'])}"
                    cv2.putText(frame, text, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                else:
                    # Новый объект
                    new_id = self.next_track_id
                    self.trackers[new_id] = KalmanTracker(new_id, det['box'], det['label'], det['dist'])
                    self.next_track_id += 1
                    det['matched'] = True
                    
                    # Рисуем новый бокс
                    color = get_color_for_class(det['label'])
                    x1, y1, x2, y2 = det['box']
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    text = f"ID:{new_id} {det['label']} | {self._format_dist(det['dist'])}"
                    cv2.putText(frame, text, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 4. ОБРАБОТКА ПОТЕРЯННЫХ, НО ПРОГНОЗИРУЕМЫХ ОБЪЕКТОВ
            for t_id, tracker in list(self.trackers.items()):
                if tracker.missed_frames > 0: # YOLO не увидел объект в этом кадре
                    if tracker.missed_frames > MAX_MISSED_FRAMES:
                        # Слишком долго не видели - удаляем трек
                        del self.trackers[t_id]
                    else:
                        # Рисуем ПРОГНОЗИРУЕМЫЙ бокс белым цветом (или пунктиром)
                        x1, y1, x2, y2 = tracker.predicted_box
                        
                        # Не рисуем, если ушел за пределы экрана
                        if x1 < WIDTH and x2 > 0 and y1 < HEIGHT and y2 > 0:
                            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 255, 255), 2, cv2.LINE_AA)
                            text = f"ID:{t_id} PREDICTED | {self._format_dist(tracker.last_dist)}"
                            cv2.putText(frame, text, (int(x1), int(y1) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            cv2.imshow("YOLO + Lidar + Kalman", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = SensorFusionNode()
    app.run()
