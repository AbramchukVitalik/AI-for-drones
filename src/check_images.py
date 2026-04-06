from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QComboBox
from PyQt6.QtGui import QPixmap
from pathlib import Path
import sys

# ================= НАСТРОЙКИ =================
IMAGES_DIR = Path(r"D:\AI-for-drones\predicted")
TXT_FILE = Path(r"D:\AI-for-drones\rejected.txt")
PROGRESS_FILE = Path(r"D:\AI-for-drones\progress.txt")
CLASSES = ["cattle", "fallen_tree", "human", "power_line", "tractor"]
# ============================================

class ImageReviewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Reviewer")
        self.image_paths = sorted(IMAGES_DIR.glob("*.jpg"))
        self.total_images = len(self.image_paths)
        self.index = 0
        self.history = []  # хранит (index, was_no, class_index)
        self.rejected = set()

        # Загружаем прогресс
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE) as f:
                try:
                    self.index = int(f.read().strip())
                except:
                    self.index = 0

        # Загружаем уже "нет" файлы
        if TXT_FILE.exists():
            with open(TXT_FILE) as f:
                self.rejected = set(line.strip() for line in f)

        # UI
        self.label = QLabel()
        self.label.setFixedSize(800, 600)
        self.status_label = QLabel()  # Для номера изображения

        # Выпадающий список классов
        self.class_selector = QComboBox()
        self.class_selector.addItems(CLASSES)
        self.class_selector.setCurrentIndex(0)

        self.btn_yes = QPushButton("Да")
        self.btn_no = QPushButton("Нет")
        self.btn_back = QPushButton("Назад")

        self.btn_yes.clicked.connect(self.yes)
        self.btn_no.clicked.connect(self.no)
        self.btn_back.clicked.connect(self.back)

        # Верстка
        hbox_buttons = QHBoxLayout()
        hbox_buttons.addWidget(self.btn_yes)
        hbox_buttons.addWidget(self.btn_no)
        hbox_buttons.addWidget(self.btn_back)

        vbox = QVBoxLayout()
        vbox.addWidget(self.status_label)
        vbox.addWidget(self.label)
        vbox.addWidget(self.class_selector)
        vbox.addLayout(hbox_buttons)
        self.setLayout(vbox)

        self.show_image()

    def show_image(self):
        if 0 <= self.index < self.total_images:
            pixmap = QPixmap(str(self.image_paths[self.index])).scaled(self.label.width(), self.label.height())
            self.label.setPixmap(pixmap)
            self.status_label.setText(f"Изображение {self.index+1}/{self.total_images}")
            self.save_progress()
        else:
            self.label.setText("Конец списка изображений")
            self.status_label.setText(f"Обработано {self.total_images}/{self.total_images}")

    def yes(self):
        self.history.append((self.index, False, None))
        self.index += 1
        self.show_image()

    def no(self):
        class_index = self.class_selector.currentIndex()
        self.history.append((self.index, True, class_index))
        filename = self.image_paths[self.index].name
        self.rejected.add(f"{filename} {class_index}")
        self.save_txt()
        self.index += 1
        self.show_image()

    def back(self):
        if not self.history:
            return
        last_index, was_no, class_index = self.history.pop()
        self.index = last_index
        if was_no:
            filename = self.image_paths[self.index].name
            entry = f"{filename} {class_index}"
            if entry in self.rejected:
                self.rejected.remove(entry)
                self.save_txt()
        self.show_image()

    def save_txt(self):
        with open(TXT_FILE, "w") as f:
            for name in sorted(self.rejected):
                f.write(name + "\n")

    def save_progress(self):
        with open(PROGRESS_FILE, "w") as f:
            f.write(str(self.index))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageReviewer()
    window.show()
    sys.exit(app.exec())
