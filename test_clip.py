import torch
import clip
from PIL import Image

device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

# 이미 자른 객체 이미지 로드
image_path = "clip_images/tmpeb_qopzg.PNG"  # YOLO로 자른 이미지 경로
image = Image.open(image_path)
image_input = preprocess(image).unsqueeze(0).to(device)

# 여러 텍스트 입력 (예: "a person", "a car", "other object")
texts = clip.tokenize(["a chair", "a person"]).to(device)
# texts = clip.tokenize(["a person","not listed object"]).to(device)
# texts = clip.tokenize(["A dolphin is crossing the sea", "not listed object"]).to(device)

# 모델 실행
# with torch.no_grad():
#     logits_per_image, logits_per_text = model(image_input, texts)
#     probs = logits_per_image.softmax(dim=-1).cpu().numpy()

with torch.no_grad():
    image_features = model.encode_image(image_input)
    text_features = model.encode_text(texts)
    
    # 정규화
    image_features = image_features / image_features.norm(dim=-1, keepdim=True)
    text_features = text_features / text_features.norm(dim=-1, keepdim=True)
    
    # 코사인 유사도 (-1 ~ 1)
    similarity = (image_features @ text_features.T).cpu().numpy()[0][0]
    
    # 0~1로 변환
    similarity_normalized = (similarity + 1) / 2


# print("Logits per image:", logits_per_image.cpu().numpy())
# print("Softmax probabilities:", probs)

print("Cosine similarity:", similarity)  # 의자-person은 낮을 것
print("Normalized (0-1):", similarity_normalized)  # 예: 0.3

# 가장 유사한 텍스트 출력
# best_match_index = probs.argmax()
# print(f"The best match is: {['a person', 'other object'][best_match_index]} with probability: {probs[0][best_match_index]}")
