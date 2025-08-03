import cv2
import torch
from ultralytics import YOLO
import clip
from PIL import Image
import numpy as np
import time

# YOLOv8n 로드
yolo_model = YOLO("yolo11n.pt")  # 또는 경로 지정
yolo_model.fuse()  # 속도 최적화

# CLIP 모델 로드
device = "cuda" if torch.cuda.is_available() else "cpu"
clip_model, preprocess = clip.load("ViT-B/32", device=device)

# CLIP 라벨 후보
text_labels = ["a man", "a woman", "a child", "a person", "a statue", "a robot"]
text_tokens = clip.tokenize(text_labels).to(device)

# 웹캠 열기 (1280x720으로 설정)
cap = cv2.VideoCapture('rtsp://admin:Password12!@192.168.0.25:554/stream1')

while True:
    start_time = time.time()

    ret, frame = cap.read()
    if not ret:
        break

    # YOLO 추론 (resize 안 해도 모델 내부에서 처리)
    results = yolo_model.predict(source=frame, classes=[0], verbose=False)  # person만
    boxes = results[0].boxes

    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf[0])
        if conf < 0.4:
            continue

        # 사람 영역 잘라내기
        person_crop = frame[y1:y2, x1:x2]
        # CLIP 입력 전용 리사이즈 및 전처리
        pil_image = Image.fromarray(cv2.cvtColor(person_crop, cv2.COLOR_BGR2RGB))
        image_input = preprocess(pil_image).unsqueeze(0).to(device)

        # CLIP 추론
        with torch.no_grad():
            image_features = clip_model.encode_image(image_input)
            text_features = clip_model.encode_text(text_tokens)
            logits_per_image = image_features @ text_features.T
            probs = logits_per_image.softmax(dim=-1).cpu().numpy()[0]

        # 가장 높은 확률의 라벨 선택
        best_idx = np.argmax(probs)
        label = f"{text_labels[best_idx]} ({probs[best_idx]:.2f})"

        # 시각화
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    # FPS 표시
    end_time = time.time()
    fps = 1 / (end_time - start_time)
    cv2.putText(frame, f"{fps:.2f} FPS", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
    
    frame = cv2.resize(frame, (800, 450))
    cv2.imshow("YOLOv8n + CLIP", frame)
    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()
