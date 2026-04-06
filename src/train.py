from ultralytics import YOLO

model = YOLO(r"D:/AI-for-drones/models/yolo26n.pt")

model.train(
    data=r"D:/AI-for-drones/datasets/full_dataset/data.yaml",
    imgsz=960,
    epochs=100,
    batch=16
)