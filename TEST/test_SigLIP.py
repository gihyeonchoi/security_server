from PIL import Image
import requests
from transformers import AutoProcessor, AutoModel
import torch

model = AutoModel.from_pretrained("google/siglip2-large-patch16-384")
processor = AutoProcessor.from_pretrained("google/siglip2-large-patch16-384")

url = "http://images.cocodataset.org/val2017/000000039769.jpg"
# image = Image.open(r"..\media\screenshots\3_20250813_113219_object_9.jpg")
image = Image.open("photo/knife.png").convert("RGB")

candidate_labels = ["a one person", "a person holding CardBoard box", "box"]
texts = [f'This is a photo of {label}.' for label in candidate_labels]

inputs = processor(
    text=texts, 
    images=image, 
    padding=True,       # 길이에 맞춰 패딩
    truncation=True,    # 최대 길이를 넘어가면 잘라서 맞춤
    return_tensors="pt"
)

with torch.no_grad():
    outputs = model(**inputs)

logits_per_image = outputs.logits_per_image
probs = torch.sigmoid(logits_per_image) # 시그모이드 활성화 함수를 적용한 확률입니다
print(f"{probs[0][0]:.1%} that image 0 is '{candidate_labels[0]}'")