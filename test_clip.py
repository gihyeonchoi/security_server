import torch
import clip
from PIL import Image
import time

device = "cuda" if torch.cuda.is_available() else "cpu"

# 모델 로드 시간 측정
start_time = time.time()

model_list = ["ViT-L/14@336px", "ViT-L/14", "ViT-B/16", "ViT-B/32"]
model_name = model_list[2]

model, preprocess = clip.load(model_name, device=device)
print(f"모델 이름 : {model_name}")

load_time = time.time() - start_time
print(f"Model load time: {load_time:.4f} sec")

image_path = "clip_images/tmpeb_qopzg.PNG"  # YOLO로 자른 이미지 경로
image = Image.open(image_path)

# 전처리 시간 측정
start_time = time.time()
image_input = preprocess(image).unsqueeze(0).to(device)
preprocess_time = time.time() - start_time
print(f"Preprocess time: {preprocess_time:.4f} sec")

# print(clip.available_models())
texts = clip.tokenize(["a person", "other object"]).to(device)

# 추론 시간 측정
start_time = time.time()
with torch.no_grad():
    logits_per_image, logits_per_text = model(image_input, texts)
inference_time = time.time() - start_time
print(f"Inference time: {inference_time:.4f} sec")

# Softmax 계산
probs = logits_per_image.softmax(dim=-1).cpu().numpy()

print("Logits per image:", logits_per_image.cpu().numpy())
print("Softmax probabilities:", probs)
