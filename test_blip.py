import torch
from PIL import Image
from transformers import BlipProcessor, BlipForImageTextRetrieval

class SimpleBLIPITM:
    def __init__(self):
        print("Loading BLIP ITM model...")
        self.processor = BlipProcessor.from_pretrained("Salesforce/blip-itm-base-coco")
        self.model = BlipForImageTextRetrieval.from_pretrained(
            "Salesforce/blip-itm-base-coco",
            torch_dtype=torch.float16,  # 메모리 절약
            low_cpu_mem_usage=True
        )
        print("✅ Model loaded successfully")
    
    def get_similarity_score(self, image, text):
        """이미지와 텍스트 간 유사도 점수 계산 (0~1)"""
        inputs = self.processor(image, text, return_tensors="pt")
        
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        # ITM 점수 추출 (여러 형태 처리)
        if hasattr(outputs, 'itm_score'):
            score_tensor = outputs.itm_score
        elif hasattr(outputs, 'logits'):
            score_tensor = outputs.logits
        else:
            # 출력 구조 확인
            print(f"Available outputs: {dir(outputs)}")
            score_tensor = outputs[0] if len(outputs) > 0 else torch.tensor([0.5])
        
        # 텐서 차원 처리
        if score_tensor.dim() > 0:
            if score_tensor.shape[-1] == 2:  # [negative, positive] 형태
                score = torch.softmax(score_tensor, dim=-1)[..., 1]  # positive 점수만
            else:
                score = score_tensor.flatten()[0]  # 첫 번째 값
        else:
            score = score_tensor
        
        # 시그모이드 적용하여 0-1 범위로 정규화
        score = torch.sigmoid(score).item()
        return score
    
    def classify_image(self, image, candidate_texts):
        """여러 텍스트 중 가장 유사한 것 찾기"""
        scores = {}
        
        print(f"🔍 이미지 분석 중... (후보: {len(candidate_texts)}개)")
        
        for text in candidate_texts:
            score = self.get_similarity_score(image, text)
            scores[text] = score
            print(f"   '{text}': {score:.4f}")
        
        # 최고 점수 찾기
        best_text = max(scores.keys(), key=lambda k: scores[k])
        best_score = scores[best_text]
        
        # 신뢰도 계산 (최고점과 두번째 점수의 차이)
        sorted_scores = sorted(scores.values(), reverse=True)
        confidence_gap = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]
        
        return {
            'prediction': best_text,
            'confidence': best_score,
            'confidence_gap': confidence_gap,
            'all_scores': scores,
            'is_confident': confidence_gap > 0.1  # 차이가 0.1 이상이면 확신
        }

# 즉시 사용 가능한 테스트 함수
def quick_test(image_path, candidate_texts=None):
    """빠른 테스트 함수"""
    
    if candidate_texts is None:
        candidate_texts = ['monitor', 'keyboard', 'speaker', 'mouse']
    
    try:
        # 이미지 로드
        image = Image.open(image_path).convert("RGB")
        print(f"📷 이미지 로드: {image_path} ({image.size})")
        
        # 모델 초기화
        classifier = SimpleBLIPITM()
        
        # 분류 실행
        result = classifier.classify_image(image, candidate_texts)
        
        # 결과 출력
        print("\n" + "="*50)
        print("🎯 분류 결과:")
        print(f"   예측: {result['prediction']}")
        print(f"   점수: {result['confidence']:.4f}")
        print(f"   신뢰도 차이: {result['confidence_gap']:.4f}")
        print(f"   확신 여부: {'✅ 확신함' if result['is_confident'] else '❓ 불확실'}")
        
        print("\n📊 모든 점수:")
        for text, score in result['all_scores'].items():
            status = "👑" if text == result['prediction'] else "  "
            print(f"   {status} {text}: {score:.4f}")
        
        return result
        
    except Exception as e:
        print(f"❌ 오류: {e}")
        return None

# 배치 처리 함수
def test_multiple_images(image_paths, candidate_texts):
    """여러 이미지를 한번에 테스트"""
    
    classifier = SimpleBLIPITM()
    results = []
    
    for i, image_path in enumerate(image_paths):
        print(f"\n🔍 이미지 {i+1}/{len(image_paths)}: {image_path}")
        
        try:
            image = Image.open(image_path).convert("RGB")
            result = classifier.classify_image(image, candidate_texts)
            result['image_path'] = image_path
            results.append(result)
            
            print(f"   결과: {result['prediction']} ({result['confidence']:.3f})")
            
        except Exception as e:
            print(f"   ❌ 처리 실패: {e}")
            results.append({'image_path': image_path, 'error': str(e)})
    
    return results

# 임계값 테스트 함수
def test_with_threshold(image_path, candidate_texts, threshold=0.5):
    """임계값을 사용한 분류"""
    
    classifier = SimpleBLIPITM()
    image = Image.open(image_path).convert("RGB")
    
    print(f"🔍 임계값 테스트 (threshold: {threshold})")
    
    scores = {}
    for text in candidate_texts:
        score = classifier.get_similarity_score(image, text)
        scores[text] = score
        
        status = "✅ PASS" if score > threshold else "❌ FAIL"
        print(f"   '{text}': {score:.4f} {status}")
    
    # 임계값 이상인 항목들만 필터링
    passed_items = {k: v for k, v in scores.items() if v > threshold}
    
    if passed_items:
        best_item = max(passed_items.keys(), key=lambda k: passed_items[k])
        print(f"\n🎯 임계값 통과: {best_item} ({passed_items[best_item]:.4f})")
    else:
        print(f"\n❌ 임계값 통과 항목 없음 (최고점: {max(scores.values()):.4f})")
    
    return scores

# 디버깅 함수 추가
def debug_model_output(image_path, text="monitor"):
    """모델 출력 구조 확인"""
    from transformers import BlipProcessor, BlipForImageTextRetrieval
    
    print("🔧 모델 출력 디버깅...")
    
    processor = BlipProcessor.from_pretrained("Salesforce/blip-itm-base-coco")
    model = BlipForImageTextRetrieval.from_pretrained("Salesforce/blip-itm-base-coco")
    
    image = Image.open(image_path).convert("RGB")
    inputs = processor(image, text, return_tensors="pt")
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    print(f"출력 타입: {type(outputs)}")
    print(f"출력 속성: {dir(outputs)}")
    
    if hasattr(outputs, 'itm_score'):
        print(f"itm_score 형태: {outputs.itm_score.shape}")
        print(f"itm_score 값: {outputs.itm_score}")
    
    if hasattr(outputs, 'logits'):
        print(f"logits 형태: {outputs.logits.shape}")
        print(f"logits 값: {outputs.logits}")
    
    return outputs


print("🧪 BLIP ITM 간단 테스트")
print("="*50)

# 사용 예시
# print("사용법:")
# print("1. 단일 이미지 테스트:")
# print("   result = quick_test('your_image.jpg')")
# print()
# print("2. 커스텀 텍스트로 테스트:")
# print("   result = quick_test('image.jpg', ['computer', 'phone', 'tablet'])")
# print()
# print("3. 여러 이미지 배치 테스트:")
# print("   results = test_multiple_images(['img1.jpg', 'img2.jpg'], ['monitor', 'keyboard'])")
# print()
# print("4. 임계값 테스트:")
# print("   scores = test_with_threshold('image.jpg', ['monitor', 'keyboard'], 0.6)")
# print()
# print("설치 명령:")
# print("pip install transformers torch pillow")

# 실제 테스트 (이미지 경로를 실제 경로로 변경)
result = quick_test("clip_images/tmpeb_qopzg.PNG")