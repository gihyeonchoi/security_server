# from transformers import pipeline
from PIL import Image
import cv2

# image_path = "photo/knife.png"
# orig_image = cv2.imread(image_path)
# image_rgb = cv2.cvtColor(orig_image, cv2.COLOR_BGR2RGB)
# pil_image = Image.fromarray(image_rgb)


# classifier = pipeline("zero-shot-image-classification", 
#                       model="google/siglip-so400m-patch14-384")
# result = classifier(pil_image, candidate_labels=["person", "knife"])
# print(result)

from transformers import pipeline
from PIL import Image
import requests

# load pipe
image_classifier = pipeline(task="zero-shot-image-classification", model="google/siglip-so400m-patch14-384")

cap = cv2.VideoCapture(0)  # 기본 웹캠

if not cap.isOpened():
    print("웹캠을 열 수 없습니다.")
    exit()

candidate_labels = ["2 cats", "a plane", "a remote", "a person"]

while True:
    ret, frame = cap.read()
    if not ret:
        print("프레임을 읽을 수 없습니다.")
        break

    # OpenCV BGR -> PIL RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(frame_rgb)

    # ----------------------------
    # 3. SigLIP 추론
    # ----------------------------
    outputs = image_classifier(pil_image, candidate_labels=candidate_labels)
    outputs = [{"score": round(o["score"], 4), "label": o["label"]} for o in outputs]

    # ----------------------------
    # 4. 화면에 출력
    # ----------------------------
    display_text = ", ".join([f"{o['label']}:{o['score']}" for o in outputs])
    cv2.putText(frame, display_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 255, 0), 2)

    cv2.imshow("Webcam Zero-Shot Classification", frame)

    # 'q' 키를 누르면 종료
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()