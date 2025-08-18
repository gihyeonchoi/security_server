# from ultralytics import YOLOE
# import cv2
# import matplotlib.pyplot as plt

# # 이미지 경로 설정
# # image_path = r"..\media\screenshots\3_20250813_113219_object_9.jpg"
# image_path = r"photo\falldown.png"

# # YOLOE 모델 로드 (HuggingFace에서 자동 다운로드)
# model = YOLOE("yoloe-11l-seg.pt")
# model_no_prompt = YOLOE("yoloe-11l-seg-pf.pt")

# print("모델 로딩 완료!")

# # 1. 프롬프트 없는 모드 (모든 객체 자동 탐지)
# print("\n=== 프롬프트 없는 모드 ===")
# results = model_no_prompt.predict(image_path)

# results[0].show()  # 결과 이미지 표시

# # 2. 텍스트 프롬프트 모드 예시
# print("\n=== 텍스트 프롬프트 모드 ===")
# # 찾고 싶은 객체를 텍스트로 지정

# prompt = [
#     "a person",
#     "a fallen person",
#     "A person lying on the ground"
# ]

# model.set_classes(prompt, model.get_text_pe(prompt))

# # 프롬프트 기반 추론 실행
# results_prompt = model.predict(image_path)
# results_prompt[0].show()

# # 3. 결과 정보 출력
# print("\n=== 탐지 결과 정보 ===")
# for i, result in enumerate(results_prompt):
#     print(f"탐지된 객체 수: {len(result.boxes) if result.boxes is not None else 0}")
#     if result.boxes is not None:
#         for j, box in enumerate(result.boxes):
#             confidence = box.conf.item()
#             class_id = int(box.cls.item())
#             print(f"객체 {j+1}: 신뢰도 {confidence:.2f}")

# print("\n추론 완료!")



from ultralytics import YOLOE
import cv2
import matplotlib.pyplot as plt

# YOLOE 모델 로드 (HuggingFace에서 자동 다운로드)
model = YOLOE("yoloe-11l-seg.pt")
model_no_prompt = YOLOE("yoloe-11l-seg-pf.pt")

print("모델 로딩 완료!")

prompt = [
    "a standing person",
    "a fallen person",
    "A person lying on the ground",
    "disposal cup",
    "a cup of coffee",
]

model.set_classes(prompt, model.get_text_pe(prompt))

# 웹캠 열기 (기본 웹캠 사용)
cap = cv2.VideoCapture(0)


# 웹캠이 정상적으로 열렸는지 확인
if not cap.isOpened():
    print("웹캠을 열 수 없습니다.")
    exit()

while True:
    # 웹캠에서 프레임 읽기
    ret, frame = cap.read()
    if not ret:
        print("프레임을 읽을 수 없습니다.")
        break
    
    # 프레임을 YOLOE 모델에 전달하여 객체 탐지 수행
    # results = model.predict(frame)
    results = model_no_prompt.predict(frame)

    for result in results:
        if result.boxes is not None:
            for box in result.boxes:
                # 박스의 좌표, 클래스, 신뢰도
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist()) 
                confidence = box.conf.item()
                class_id = int(box.cls.item())
                label = f'{model_no_prompt.names[class_id]} {confidence:.2f}'

                # 객체 탐지 박스를 이미지에 그리기
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)  # 박스 그리기
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)  # 라벨 그리기

    # 실시간으로 추론 결과를 화면에 표시
    cv2.imshow("Real-time Object Detection", frame)

    # 'q' 키를 눌러 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 웹캠 종료 및 모든 창 닫기
cap.release()
cv2.destroyAllWindows()
