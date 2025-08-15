from PIL import Image, ImageDraw, ImageFont
import torch
from transformers import Owlv2Processor, Owlv2ForObjectDetection
from ultralytics import YOLO
import os

# 1. 모델과 프로세서 로드
model_id = "google/owlv2-base-patch16"
processor = Owlv2Processor.from_pretrained(model_id)
model = Owlv2ForObjectDetection.from_pretrained(model_id)

# YOLO 모델 로드
yolo_model = YOLO("yolo11m.pt")

# 2. 이미지 불러오기
image_path = "photo/144.png"
image = Image.open(image_path).convert("RGB")

# 3. YOLO로 객체 탐지
yolo_results = yolo_model(image)

# 4. 탐지된 객체들 처리
detected_objects = []
cropped_images = []
crop_info = []

# 결과 저장을 위한 디렉토리 생성
os.makedirs("cropped_objects", exist_ok=True)

for i, result in enumerate(yolo_results):
    boxes = result.boxes
    if boxes is not None:
        for j, box in enumerate(boxes):
            # 박스 좌표 (xyxy 형식)
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            confidence = box.conf[0].cpu().numpy()
            
            # 20% 확장된 크기로 자르기
            width = x2 - x1
            height = y2 - y1
            
            # 20% 확장
            expand_w = width
            expand_h = height
            
            # 새로운 좌표 (이미지 경계 체크)
            new_x1 = max(0, x1 - expand_w/2)
            new_y1 = max(0, y1 - expand_h/2)
            new_x2 = min(image.width, x2 + expand_w/2)
            new_y2 = min(image.height, y2 + expand_h/2)
            
            # 이미지 자르기
            cropped_img = image.crop((new_x1, new_y1, new_x2, new_y2))
            cropped_images.append(cropped_img)
            
            # 자른 이미지 저장
            crop_filename = f"cropped_objects/object_{i}_{j}.png"
            cropped_img.save(crop_filename)
            
            # 좌표 정보 저장 (원본 이미지에서의 위치)
            crop_info.append({
                'original_box': (x1, y1, x2, y2),
                'cropped_box': (new_x1, new_y1, new_x2, new_y2),
                'confidence': confidence,
                'crop_filename': crop_filename
            })

print(f"YOLO로 {len(cropped_images)}개의 객체를 탐지했습니다.")

# 5. 찾을 객체 설명 (한 이미지에 여러 쿼리)
queries = [["a person riding bike", "a person running"]]

# 6. 각 잘린 이미지에 대해 OWLv2 추론 실행
owlv2_results = []

for idx, cropped_img in enumerate(cropped_images):
    print(f"OWLv2 추론 중... ({idx+1}/{len(cropped_images)})")
    
    # 입력 변환
    inputs = processor(
        text=queries,
        images=[cropped_img],
        return_tensors="pt",
        padding=True,
        truncation=True
    )
    
    # 모델 추론
    with torch.no_grad():
        outputs = model(**inputs)
    
    # 후처리
    target_sizes = torch.tensor([cropped_img.size[::-1]])
    results = processor.post_process_grounded_object_detection(
        outputs,
        target_sizes=target_sizes,
        threshold=0.4
    )
    
    # 탐지 결과 개수 출력
    num_detections = len(results[0]["scores"]) if results[0]["scores"] is not None else 0
    print(f"  - {num_detections}개의 객체 탐지됨 (threshold=0.01)")
    
    owlv2_results.append({
        'crop_idx': idx,
        'results': results[0],
        'crop_info': crop_info[idx]
    })

# 7. 결과 출력 및 원본 이미지에 박스 그리기
draw = ImageDraw.Draw(image)

# 기본 폰트 사용 (시스템에 없으면 기본 폰트)
try:
    font = ImageFont.truetype("arial.ttf", 20)
except:
    font = ImageFont.load_default()

# OWLv2 결과를 원본 이미지 좌표로 변환하여 그리기
for owlv2_result in owlv2_results:
    crop_info_item = owlv2_result['crop_info']
    results = owlv2_result['results']
    crop_idx = owlv2_result['crop_idx']
    
    # 자른 이미지의 좌표 정보
    cropped_x1, cropped_y1, cropped_x2, cropped_y2 = crop_info_item['cropped_box']
    
    print(f"\n--- 자른 이미지 {crop_idx+1} 결과 ---")
    
    for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
        # 자른 이미지 내에서의 좌표
        rel_x1, rel_y1, rel_x2, rel_y2 = box.tolist()
        
        # 원본 이미지 좌표로 변환
        abs_x1 = cropped_x1 + rel_x1
        abs_y1 = cropped_y1 + rel_y1
        abs_x2 = cropped_x1 + rel_x2
        abs_y2 = cropped_y1 + rel_y2
        
        label_text = queries[0][label]
        
        print(f"설명: {label_text} | 점수: {score:.4f}")
        print(f"원본 이미지 좌표: ({abs_x1:.1f}, {abs_y1:.1f}, {abs_x2:.1f}, {abs_y2:.1f})")
        
        # 박스 그리기 (파란색 - OWLv2 결과)
        draw.rectangle([abs_x1, abs_y1, abs_x2, abs_y2], outline="blue", width=3)
        
        # 라벨 텍스트 그리기
        text = f"{label_text} ({score:.2f})"
        draw.text((abs_x1, abs_y1-25), text, fill="blue", font=font)

# YOLO 탐지 박스도 그리기 (녹색)
for crop_info_item in crop_info:
    x1, y1, x2, y2 = crop_info_item['original_box']
    confidence = crop_info_item['confidence']
    
    draw.rectangle([x1, y1, x2, y2], outline="green", width=2)
    draw.text((x1, y1-50), f"YOLO ({confidence:.2f})", fill="green", font=font)

# 결과 이미지 저장 및 출력
output_path = image_path.replace('.png', '_result.png').replace('.jpg', '_result.jpg')
image.save(output_path)
print(f"\n결과 이미지가 저장되었습니다: {output_path}")

# 이미지 보기 (선택사항)
# image.show()
