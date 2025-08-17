from ultralytics import YOLOWorld

# 1. 모델 로드
# model = YOLOWorld("yolov8s-worldv2.pt")
# model = YOLOWorld("yolov8x-worldv2.pt")
model = YOLOWorld("yolov8m-worldv2.pt")

# class_list = [
#     "assault incident",
#     "an assault case",
#     "People who fight in boxing",
#     "boxing gloves",
#     "a person",
#     "People are fighting"
# ]
class_list = [
    # "a person",
    "a person riding bike",
    "a fallen person",
    "A person lying on the ground"
]

# 2. 여러 클래스 동시 설정 - 이미 동시 탐지됨!
model.set_classes(class_list)

# 3. 이미지에서 추론 (두 클래스 모두 탐지)
# results = model("photo/fight.jpg")
results = model(r"..\media\screenshots\3_20250813_113219_object_9.jpg")

# 4. 결과 확인
for r in results:
    r.show()  # 시각화

# 5. 탐지된 객체 출력
print("탐지된 객체들:")
print("-" * 40)

for r in results:
    for box in r.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        xyxy = box.xyxy[0].tolist()
        class_name = r.names[cls_id]
        
        print(f"[{class_name}] Confidence: {conf:.3f}, BBox: [{xyxy[0]:.1f}, {xyxy[1]:.1f}, {xyxy[2]:.1f}, {xyxy[3]:.1f}]")
        
    
    print("-" * 40)