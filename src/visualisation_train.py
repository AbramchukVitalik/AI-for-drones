from pathlib import Path
import cv2

# ================= НАСТРОЙКИ =================
IMAGES_DIR = Path(r"D:\AI-for-drones\datasets/full_dataset/images/val/")
LABELS_DIR = Path(r"D:\AI-for-drones\datasets/full_dataset/labels/val/")
SAVE_DIR = Path(r"D:\AI-for-drones/predicted/")
FAILED_FILE = Path("failed_images.txt")  # файл для не загруженных изображений
CLASSES = ["cattle", "fallen_tree", "human", "power_line", "tractor"]  # список классов по индексу
# ============================================

# Цвета для классов (BGR)
CLASS_COLORS = {
    0: (0, 255, 255),    # желтый
    1: (0, 255, 0),      # зеленый
    2: (255, 0, 0),      # синий
    3: (255, 0, 255),    # пурпурный
    4: (0, 0, 255),      # красный
}

SAVE_DIR.mkdir(parents=True, exist_ok=True)

def yolo_to_xyxy(label, w, h):
    """Конвертирует YOLO bbox в координаты xyxy"""
    cls, x, y, bw, bh = map(float, label.split())
    x1 = int((x - bw/2) * w)
    y1 = int((y - bh/2) * h)
    x2 = int((x + bw/2) * w)
    y2 = int((y + bh/2) * h)
    return int(cls), [x1, y1, x2, y2]

# Открываем файл для записи проблемных изображений в UTF-8
with open(FAILED_FILE, "w", encoding="utf-8") as f_failed:
    for img_path in IMAGES_DIR.rglob("*.jpg"):
        label_path = LABELS_DIR / img_path.relative_to(IMAGES_DIR)
        label_path = label_path.with_suffix(".txt")

        if not label_path.exists():
            print(f"Нет разметки для {img_path.name}, пропускаем...")
            continue

        img = cv2.imread(str(img_path))
        if img is None:
            print(f"Не удалось загрузить изображение: {img_path.name}")
            f_failed.write(f"{img_path.name}\n")  # записываем имя файла
            continue  # пропускаем этот файл

        h, w = img.shape[:2]

        with open(label_path, encoding="utf-8") as f_label:
            for line in f_label:
                cls_idx, box = yolo_to_xyxy(line, w, h)
                x1, y1, x2, y2 = map(int, box)
                color = CLASS_COLORS.get(cls_idx, (255, 255, 255))  # белый по умолчанию
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                cls_name = CLASSES[cls_idx] if cls_idx < len(CLASSES) else str(cls_idx)
                cv2.putText(img, cls_name, (x1, y1-5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        save_path = SAVE_DIR / img_path.name
        cv2.imwrite(str(save_path), img)
        print(f"Сохранено: {save_path.name}")

print("Проверка разметки завершена!")
print(f"Проблемные изображения сохранены в {FAILED_FILE}")