import cv2
import threading
import time
from ultralytics import YOLO

# Инициализация
model = YOLO('yolo26n.pt')

class DroneCamera:
    def __init__(self, source=0):
        self.cap = cv2.VideoCapture(source)
        self.ret, self.frame = self.cap.read()
        self.running = True
        self.results = None
        
        # Поток для чтения камеры (всегда читает свежий кадр)
        self.thread_cap = threading.Thread(target=self._update_frame, daemon=True)
        # Поток для нейросети (работает в своем темпе)
        self.thread_inference = threading.Thread(target=self._run_inference, daemon=True)

    def _update_frame(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
            else:
                self.running = False

    def _run_inference(self):
        frame_count = 0
        while self.running:
            frame_count += 1
            # Обрабатываем каждый 3-й кадр
            if frame_count % 3 == 0 and self.frame is not None:
                # stream=True и persist=True для стабильности
                res = model.track(self.frame, persist=True, verbose=False)
                self.results = res[0]
            time.sleep(0.01) # Небольшая пауза, чтобы не забивать CPU

    def start(self):
        self.thread_cap.start()
        self.thread_inference.start()
        
        prev_time = time.time()
        
        while self.running:
            # Берем текущий кадр из потока камеры
            display_frame = self.frame.copy()
            
            # Накладываем последние результаты нейросети
            if self.results is not None:
                display_frame = self.results.plot() # Отрисовка рамок

            # Считаем реальный FPS вывода
            curr_time = time.time()
            fps = 1 / (curr_time - prev_time)
            prev_time = curr_time
            
            cv2.putText(display_frame, f"Display FPS: {int(fps)}", (20, 40), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow("Drone AI", display_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        self.running = False
        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    drone_vision = DroneCamera(0)
    drone_vision.start()
