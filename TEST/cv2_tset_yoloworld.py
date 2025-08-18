from ultralytics import YOLOWorld, YOLOE
import cv2
import matplotlib.pyplot as plt

model = YOLOWorld("yolov8x-worldv2.pt")
# model = YOLOE("yoloe-11l-seg.pt")

# 동의어 그룹 정의 (출력 라벨 : 프롬프트 리스트)
label_map = {
    # 서 있는 사람
    "standing_person": [
        "a person standing", "a person who is standing", "someone standing upright",
        "a person standing alone", "people standing together",
        "a person standing calmly", "a person waiting while standing"
    ],

    # 넘어지거나 눕는 사람
    "fallen_person": [
        "a fallen person", "a person collapsed", "a person who has fallen down",
        "a person lying on the ground", "a person laying flat on the floor", "a human body on the ground",
        "someone lying on the floor", "a person sprawled on the ground"
    ],

    # 앉아 있는 사람
    "sitting_person": [
        "a person seated on a chair", "a person sitting on a bench", "a person sitting cross-legged",
        "a person sitting upright", "someone sitting calmly", "a person sitting at a desk",
        "a person sitting on the floor", "a person resting while sitting"
    ],

    # 싸우는 사람들
    "fighting_persons": [
        "a person hitting another person",
        "a person punching another person",
        "a person kicking another person",
        "a person slapping another person",
        "a person striking someone",
        "a person pushing another person forcefully",
        "a person grappling with another person",
        "people involved in a brawl"
    ],

    # 컵
    "cup": [
        "a disposable cup", "a plastic cup", "a paper cup",
        "a coffee cup", "a cup of coffee", "a mug with coffee", "a takeaway coffee cup"
    ],

    # Negative prompt / 오탐 방지용
    # "negative": [
    #     "two people standing", "people standing together", "people walking",
    #     "people talking", "a person standing next to another person"
    # ]
}


# YOLOE에 프롬프트 세팅 (모든 프롬프트를 flatten해서 넣음)
all_prompts = [p for prompts in label_map.values() for p in prompts]

model.set_classes(all_prompts)

results = model(r"photo/fight2.png")

prompt_to_label = {}
for group_label, prompts in label_map.items():
    for p in prompts:
        prompt_to_label[p] = group_label

# 3. 탐지 결과 출력 시 그룹 라벨로 변환
for r in results:
    for box in r.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        xyxy = box.xyxy[0].tolist()
        class_name = r.names[cls_id]
        
        # class_name을 그룹 라벨로 변환
        group_label = prompt_to_label.get(class_name, class_name)
        
        print(f"[{group_label}] Confidence: {conf:.3f}, BBox: [{xyxy[0]:.1f}, {xyxy[1]:.1f}, {xyxy[2]:.1f}, {xyxy[3]:.1f}]")
    r.show()

# # 웹캠 열기
# cap = cv2.VideoCapture(0)
# if not cap.isOpened():
#     print("웹캠을 열 수 없습니다.")
#     exit()

# # 역맵 생성: 프롬프트 → 그룹 라벨
# prompt_to_label = {}
# for label, prompts in label_map.items():
#     for p in prompts:
#         prompt_to_label[p] = label

# while True:
#     ret, frame = cap.read()
#     if not ret:
#         print("프레임을 읽을 수 없습니다.")
#         break

#     results = model.predict(frame)

#     for result in results:
#         if result.boxes is not None:
#             for box in result.boxes:
#                 x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
#                 confidence = box.conf.item()
#                 class_id = int(box.cls.item())
                
#                 # 탐지된 클래스명을 그룹 라벨로 변환
#                 detected_prompt = model.names[class_id]
#                 label = prompt_to_label.get(detected_prompt, detected_prompt)
#                 label_text = f'{label} {confidence:.2f}'

#                 # 박스 그리기
#                 cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
#                 cv2.putText(frame, label_text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

#     cv2.imshow("Real-time Object Detection", frame)
#     if cv2.waitKey(1) & 0xFF == ord('q'):
#         break

# cap.release()
# cv2.destroyAllWindows()