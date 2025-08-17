from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image
import torch
import torch.nn.functional as F
import numpy as np
import re
import warnings

# 경고 메시지 무시
warnings.filterwarnings("ignore")

# 모델 및 프로세서 로드
print("Florence-2 모델 로딩 중...")
model = AutoModelForCausalLM.from_pretrained(
    "microsoft/Florence-2-base",
    trust_remote_code=True,
    attn_implementation="eager"
)

processor = AutoProcessor.from_pretrained(
    "microsoft/Florence-2-base", 
    trust_remote_code=True
)

# GPU 사용 가능시 GPU로 이동
device = "cuda" if torch.cuda.is_available() else "cpu"
model = model.to(device)
print(f"디바이스: {device}")

# 이미지 로드
image_path = "photo/fight.jpg"
try:
    image = Image.open(image_path)
    print(f"\n이미지 로드 완료: {image_path}")
    print(f"이미지 크기: {image.size}")
except FileNotFoundError:
    print(f"이미지를 찾을 수 없습니다: {image_path}")
    exit()

# 4가지 상황 시나리오 정의
scenarios = [
    "두 남자가 싸우는 상황",
    "두 사람이 음식을 먹는 상황", 
    "두 사람이 대화하는 상황",
    "두 사람이 운동하는 상황"
]

print("\n" + "="*50)
print("Florence-2를 사용한 상황 분석")
print("="*50)

# 1. Caption 생성 (post_process 없이 직접 파싱)
print("\n이미지 분석 중...")

all_captions = []

# DETAILED_CAPTION 생성
task = "<DETAILED_CAPTION>"
inputs = processor(text=task, images=image, return_tensors="pt").to(device)

with torch.no_grad():
    generated_ids = model.generate(
        input_ids=inputs["input_ids"],
        pixel_values=inputs["pixel_values"],
        max_new_tokens=200,
        num_beams=3,
        do_sample=False
    )
    
    # 디코딩
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    
    # 태스크 토큰 제거하고 실제 caption 추출
    # Florence-2는 보통 "task_token<실제내용>" 형태로 출력
    caption = generated_text.replace(task, "").strip()
    
    # 추가 토큰 제거
    caption = re.sub(r'<[^>]+>', '', caption).strip()
    
    all_captions.append(caption)
    print(f"\n실제 이미지 설명:")
    print(f"'{caption}'")

# CAPTION (간단) 생성
task = "<CAPTION>"
inputs = processor(text=task, images=image, return_tensors="pt").to(device)

with torch.no_grad():
    generated_ids = model.generate(
        input_ids=inputs["input_ids"],
        pixel_values=inputs["pixel_values"],
        max_new_tokens=50,
        num_beams=3,
        do_sample=False
    )
    
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    simple_caption = generated_text.replace(task, "").strip()
    simple_caption = re.sub(r'<[^>]+>', '', simple_caption).strip()
    all_captions.append(simple_caption)

# 모든 caption을 하나로 합치기
combined_caption = ' '.join(all_captions).lower()

print("\n" + "-"*50)

# 2. 각 시나리오에 대한 키워드 정의 및 매칭
scenario_keywords = {
    "두 남자가 싸우는 상황": {
        "strong": ["fight", "fighting", "punch", "kick", "combat", "boxing", "martial", "wrestl"],
        "medium": ["aggressive", "conflict", "confrontation", "attack", "violent", "battle"],
        "weak": ["angry", "tension", "dispute", "physical", "fist", "stance"]
    },
    "두 사람이 음식을 먹는 상황": {
        "strong": ["eating", "food", "meal", "dining", "restaurant", "lunch", "dinner"],
        "medium": ["table", "plate", "fork", "spoon", "drink", "cuisine", "dish"],
        "weak": ["kitchen", "cafe", "breakfast", "snack", "beverage", "cook"]
    },
    "두 사람이 대화하는 상황": {
        "strong": ["talking", "conversation", "speaking", "discussing", "chat", "dialogue"],
        "medium": ["communication", "meeting", "interview", "discussion", "talk", "speech"],
        "weak": ["face", "gesture", "listening", "explaining", "mouth", "words"]
    },
    "두 사람이 운동하는 상황": {
        "strong": ["exercise", "workout", "sport", "training", "gym", "fitness"],
        "medium": ["athletic", "running", "lifting", "stretching", "sparring", "practice"],
        "weak": ["active", "physical", "sweat", "muscle", "movement", "activity"]
    }
}

# 3. 점수 계산
print("\n키워드 매칭 분석:")
print("-"*50)

scores = []
for scenario in scenarios:
    keywords = scenario_keywords[scenario]
    
    # 가중치 적용 점수 계산
    strong_score = sum(3 for word in keywords["strong"] if word in combined_caption)
    medium_score = sum(2 for word in keywords["medium"] if word in combined_caption)
    weak_score = sum(1 for word in keywords["weak"] if word in combined_caption)
    
    total_score = strong_score + medium_score + weak_score
    scores.append(total_score)
    
    # 매칭된 키워드 출력
    matched_keywords = []
    for level, words in keywords.items():
        for word in words:
            if word in combined_caption:
                matched_keywords.append(f"{word}({level[0]})")
    
    if matched_keywords:
        print(f"{scenario}:")
        print(f"  매칭: {', '.join(matched_keywords[:5])}")  # 최대 5개만 표시

# 4. 점수가 모두 0인 경우 처리
if all(score == 0 for score in scores):
    print("\n키워드 매칭 실패 - 기본 분석 수행")
    # 기본 단어 검색
    if "man" in combined_caption or "men" in combined_caption or "people" in combined_caption:
        if any(word in combined_caption for word in ["two", "2", "pair"]):
            scores[0] = 1  # 기본값 부여

# 5. Softmax를 사용한 확률 변환
if sum(scores) > 0:
    # 온도 매개변수로 확률 분포 조정
    temperature = 1.5
    scores_array = np.array(scores, dtype=float)
    # 0 제거를 위해 작은 값 추가
    scores_array = scores_array + 0.1
    exp_scores = np.exp(scores_array / temperature)
    probabilities = exp_scores / exp_scores.sum()
else:
    # 점수가 모두 0인 경우 균등 분포
    probabilities = np.array([0.25] * 4)

# 6. 결과 출력
print("\n" + "="*50)
print("📊 각 상황별 확률:")
print("="*50)

results = []
for scenario, prob in zip(scenarios, probabilities):
    results.append((scenario, prob))
    
    # 시각적 바 그래프
    bar_length = int(prob * 30)
    bar = '█' * bar_length + '░' * (30 - bar_length)
    
    # 확률에 따른 색상 이모지
    if prob > 0.5:
        emoji = "🔴"
    elif prob > 0.3:
        emoji = "🟡"
    else:
        emoji = "⚪"
    
    print(f"\n{emoji} {scenario}")
    print(f"   {bar} {prob:.4f} ({prob*100:.2f}%)")

# 7. 가장 높은 확률의 상황
print("\n" + "="*50)
best_scenario, best_prob = max(results, key=lambda x: x[1])
print(f"🎯 가장 가능성 높은 상황:")
print(f"   → {best_scenario}")
print(f"   → 확률: {best_prob:.4f} ({best_prob*100:.2f}%)")

# 8. 신뢰도 평가
sorted_probs = sorted(probabilities, reverse=True)
if len(sorted_probs) > 1:
    confidence = sorted_probs[0] - sorted_probs[1]
    if confidence > 0.3:
        confidence_level = "높음 ⭐⭐⭐"
    elif confidence > 0.15:
        confidence_level = "중간 ⭐⭐"
    else:
        confidence_level = "낮음 ⭐"
    
    print(f"\n📈 신뢰도: {confidence_level} (차이: {confidence:.4f})")

# 9. Object Detection으로 추가 분석
print("\n" + "="*50)
print("🔍 추가 Object Detection 분석:")
print("="*50)

task = "<OD>"
inputs = processor(text=task, images=image, return_tensors="pt").to(device)

with torch.no_grad():
    generated_ids = model.generate(
        input_ids=inputs["input_ids"],
        pixel_values=inputs["pixel_values"],
        max_new_tokens=1024,
        num_beams=3,
        do_sample=False
    )
    
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    
    # OD 결과 파싱 (수동)
    od_result = generated_text.replace(task, "").strip()
    
    # 객체 추출 (간단한 파싱)
    if od_result:
        # Florence-2 OD 출력 형식: "obj<loc>coords</loc>..."
        objects = re.findall(r'([a-zA-Z\s]+)<loc>', od_result)
        if objects:
            unique_objects = list(set([obj.strip() for obj in objects]))
            print(f"탐지된 객체들: {', '.join(unique_objects)}")
            
            # 사람 관련 객체 확인
            person_keywords = ['person', 'people', 'man', 'men', 'woman', 'women', 'human']
            person_count = sum(1 for obj in objects if any(keyword in obj.lower() for keyword in person_keywords))
            
            if person_count >= 2:
                print(f"  → {person_count}명의 사람 탐지됨")
            
            # 특정 객체 확인
            if any('fight' in obj.lower() or 'combat' in obj.lower() for obj in objects):
                print("  → 싸움 관련 동작 탐지")
        else:
            print("  → 객체 파싱 실패 (형식 불일치)")
    else:
        print("  → Object Detection 결과 없음")

print("\n" + "="*50)
print("✅ 분석 완료!")
print("="*50)

# 10. 요약 정보
print("\n📋 요약:")
print(f"  • 입력 이미지: {image_path}")
print(f"  • 이미지 크기: {image.size}")
print(f"  • 최종 예측: {best_scenario}")
print(f"  • 확률: {best_prob:.2%}")
print("="*50)