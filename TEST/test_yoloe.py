from ultralytics import YOLOE
import cv2
import matplotlib.pyplot as plt

# 이미지 경로 설정
# image_path = r"..\media\screenshots\3_20250813_113219_object_9.jpg"
image_path = r"photo\falldown.png"

# YOLOE 모델 로드 (HuggingFace에서 자동 다운로드)
model = YOLOE("yoloe-11l-seg.pt")
model_no_prompt = YOLOE("yoloe-11l-seg-pf.pt")

print("모델 로딩 완료!")

# 1. 프롬프트 없는 모드 (모든 객체 자동 탐지)
print("\n=== 프롬프트 없는 모드 ===")
results = model_no_prompt.predict(image_path)

results[0].show()  # 결과 이미지 표시

# 2. 텍스트 프롬프트 모드 예시
print("\n=== 텍스트 프롬프트 모드 ===")
# 찾고 싶은 객체를 텍스트로 지정

prompt = [
    "a person",
    "a fallen person",
    "A person lying on the ground"
]

model.set_classes(prompt, model.get_text_pe(prompt))

# 프롬프트 기반 추론 실행
results_prompt = model.predict(image_path)
results_prompt[0].show()

# 3. 결과 정보 출력
print("\n=== 탐지 결과 정보 ===")
for i, result in enumerate(results_prompt):
    print(f"탐지된 객체 수: {len(result.boxes) if result.boxes is not None else 0}")
    if result.boxes is not None:
        for j, box in enumerate(result.boxes):
            confidence = box.conf.item()
            class_id = int(box.cls.item())
            print(f"객체 {j+1}: 신뢰도 {confidence:.2f}")

print("\n추론 완료!")