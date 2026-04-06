from pathlib import Path

# ================= НАСТРОЙКИ =================
IMAGES_DIR = Path(r"D:\AI-for-drones\datasets/full_dataset/images/val/")
LABELS_DIR = Path(r"D:\AI-for-drones\datasets/full_dataset/labels/val/")
TXT_FILE = Path(r"D:\AI-for-drones\rejected.txt")  # твой файл со строками "имя класс"
# ============================================

if not TXT_FILE.exists():
    print(f"{TXT_FILE} не найден")
    exit()

with open(TXT_FILE, encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip()]

for line in lines:
    try:
        filename, class_number = line.split()
        class_number = int(class_number)
    except ValueError:
        print(f"Пропущена некорректная строка: {line}")
        continue

    # ищем соответствующий файл разметки
    img_path = IMAGES_DIR / filename
    label_path = LABELS_DIR / img_path.relative_to(IMAGES_DIR)
    label_path = label_path.with_suffix(".txt")

    if not label_path.exists():
        print(f"Разметка не найдена для {filename}, пропускаем...")
        continue

    # читаем строки и заменяем класс
    with open(label_path, encoding="utf-8") as f_label:
        new_lines = []
        for l in f_label:
            parts = l.strip().split()
            if len(parts) != 5:
                print(f"Некорректная строка в {label_path}: {l.strip()}")
                continue
            # сохраняем bbox, меняем только класс
            new_line = f"{class_number} {' '.join(parts[1:])}"
            new_lines.append(new_line)

    # сохраняем обратно
    with open(label_path, "w", encoding="utf-8") as f_label:
        f_label.write("\n".join(new_lines) + "\n")

    print(f"Обновлено: {label_path.name}")

print("Все разметки обновлены!")
