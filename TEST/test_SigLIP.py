from PIL import Image
import cv2
import torch
import numpy as np
from transformers import AutoProcessor, AutoModel
from ultralytics import YOLO

# ----------------------------
# 0. 설정: 모델 및 라벨 맵
# ----------------------------
# YOLO11 모델 로드
yolo_model = YOLO("yolo11m.pt")

# SigLIP2 모델 로드 (원래 모델 사용)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
siglip_model = AutoModel.from_pretrained("google/siglip2-large-patch16-384").to(device)
siglip_processor = AutoProcessor.from_pretrained("google/siglip2-large-patch16-384")

# 개선된 라벨 맵
label_map = {
    # 사람 관련 - 더 직접적인 표현
    "person": ["person", "human", "people"],
    "standing_person": ["standing person", "person standing"],
    "fallen_person": ["fallen person", "person lying down", "person on ground"],
    "sitting_person": ["sitting person", "seated person"],
    "fighting_persons": ["people fighting", "fight", "violence"],
    
    # 객체 관련
    "knife": ["knife", "blade", "weapon"],
    "remote": ["remote control", "TV remote"],
    "cup": ["cup", "mug"]
}

# 역맵 생성
prompt_to_label = {}
for group_label, prompts in label_map.items():
    for p in prompts:
        prompt_to_label[p] = group_label

# ----------------------------
# 1. 이미지 불러오기
# ----------------------------
image_path = "photo/knife.png"
orig_image = cv2.imread(image_path)
image_rgb = cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB)
pil_image = Image.fromarray(image_rgb)

# ----------------------------
# 2. YOLO로 객체 탐지
# ----------------------------
results = yolo_model(pil_image)

# ----------------------------
# 3. YOLO 박스 표시 및 디버깅
# ----------------------------
display_image = orig_image.copy()

print("=" * 50)
print("YOLO Detection Results:")
print("=" * 50)
for r in results:
    for box in r.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf[0])
        cls_id = int(box.cls[0])
        class_name = r.names[cls_id]
        
        print(f"  [{class_name}] conf={conf:.3f}, box=[{x1},{y1},{x2},{y2}]")
        
        # YOLO 탐지 박스 표시 (초록색)
        cv2.rectangle(display_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(display_image, f"{class_name} {conf:.2f}", (x1, y1-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

cv2.imshow("YOLO Detection", display_image)
cv2.waitKey(0)

# ----------------------------
# 4. SigLIP2로 각 박스 재분류
# ----------------------------
threshold = 0.05  # 낮은 threshold 유지

final_image = orig_image.copy()

print("\n" + "=" * 50)
print("SigLIP2 Classification Results:")
print("=" * 50)

for r in results:
    for idx, box in enumerate(r.boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        yolo_class = r.names[int(box.cls[0])]
        
        # 크롭 이미지
        crop = pil_image.crop((x1, y1, x2, y2))
        
        # 크롭 크기 확인
        crop_width, crop_height = crop.size
        print(f"\n[Box {idx+1}] YOLO: {yolo_class}, Size: {crop_width}x{crop_height}")
        
        # YOLO 클래스에 따라 적절한 후보 선택
        if yolo_class == "person":
            # 사람인 경우 다양한 표현 테스트
            candidate_labels = [
                "person",
                "human",
                "standing person", 
                "sitting person",
                "fallen person",
                "walking person"
            ]
        elif yolo_class in ["knife", "knives"]:
            candidate_labels = ["knife", "blade", "weapon", "tool"]
        elif yolo_class == "remote":
            candidate_labels = ["remote control", "TV remote", "remote", "controller"]
        else:
            # 기본 라벨 + 변형
            candidate_labels = [yolo_class, "object", "thing"]
        
        print(f"  Testing labels: {candidate_labels}")
        
        # SigLIP2 입력 생성 - 간단한 텍스트 사용
        inputs = siglip_processor(
            text=candidate_labels,
            images=crop,
            # padding="max_length",
            padding=True,
            truncation=True,
            return_tensors="pt"
        ).to(device)
        
        # 추론
        with torch.no_grad():
            outputs = siglip_model(**inputs)
            
        # SigLIP2는 sigmoid 사용
        logits = outputs.logits_per_image  # shape: [1, num_texts]
        probs = torch.sigmoid(logits)
        
        # 디버깅: 모든 확률 출력
        print(f"  Probabilities:")
        for i, (label, prob) in enumerate(zip(candidate_labels, probs[0])):
            print(f"    {label}: {prob.item():.4f}")
        
        # 최고 확률 선택
        max_idx = torch.argmax(probs[0])
        max_prob = probs[0, max_idx].item()
        best_label = candidate_labels[max_idx]
        
        # 그룹 라벨 결정
        final_label = prompt_to_label.get(best_label, best_label)
        
        # 낮은 확률 처리
        if max_prob < threshold:
            print(f"  ⚠️ Low confidence ({max_prob:.4f} < {threshold})")
            final_label = f"{yolo_class}(?)"
        else:
            print(f"  ✓ Selected: {best_label} → {final_label} (prob={max_prob:.4f})")
        
        # 색상 맵
        color_map = {
            "person": (0, 255, 255),           # 청록
            "standing_person": (0, 255, 0),    # 초록
            "fallen_person": (0, 0, 255),      # 빨강
            "sitting_person": (255, 255, 0),   # 노랑
            "knife": (0, 0, 255),              # 빨강
            "remote": (255, 0, 255),           # 보라
            "cup": (255, 128, 0),              # 주황
        }
        
        # 기본 색상
        color = color_map.get(final_label.replace("(?)", ""), (128, 128, 128))
        
        # 박스와 라벨 표시
        cv2.rectangle(final_image, (x1, y1), (x2, y2), color, 2)
        label_text = f"{final_label} {max_prob:.2f}"
        cv2.putText(final_image, label_text, (x1, y1-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

# 결과 표시
cv2.imshow("YOLO + SigLIP2 Detection", final_image)
cv2.waitKey(0)
cv2.destroyAllWindows()

# 시스템 정보
print("\n" + "=" * 50)
print("System Info:")
print("=" * 50)
print(f"Device: {device}")
print(f"Model: {siglip_model.config.model_type}")
print(f"Vision Config: {siglip_model.config.vision_config.image_size}px")
print(f"Text Config: max_length={siglip_model.config.text_config.max_position_embeddings}")

# 추가 테스트: 전체 이미지로 SigLIP2 테스트
print("\n" + "=" * 50)
print("Testing SigLIP2 on full image:")
print("=" * 50)
test_labels = ["person", "knife", "remote control", "indoor scene", "weapon"]
test_inputs = siglip_processor(
    text=test_labels,
    images=pil_image,
    # padding="max_length",
    padding=True,
    truncation=True,
    return_tensors="pt"
).to(device)

with torch.no_grad():
    test_outputs = siglip_model(**test_inputs)
    test_probs = torch.sigmoid(test_outputs.logits_per_image)

for label, prob in zip(test_labels, test_probs[0]):
    print(f"  {label}: {prob.item():.4f}")