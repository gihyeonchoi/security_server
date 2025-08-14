import torch
import numpy as np
from PIL import Image, ImageDraw
from transformers import OwlViTProcessor, OwlViTForObjectDetection
import matplotlib.pyplot as plt

class ImprovedObjectClassifier:
    def __init__(self):
        self.load_owlvit()
        
    def load_owlvit(self):
        """OWL-ViT 모델 로드"""
        print("Loading OWL-ViT...")
        self.processor = OwlViTProcessor.from_pretrained("google/owlvit-base-patch32")
        self.model = OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32")
        print("✅ OWL-ViT loaded successfully")
    
    def classify_cropped_objects(self, image_crops, text_queries, confidence_threshold=0.3):
        """크롭된 객체들을 정확히 분류"""
        results = []
        
        for i, crop in enumerate(image_crops):
            print(f"\n🔍 Crop {i+1} 분석 중...")
            
            # OWL-ViT로 분류
            inputs = self.processor(text=text_queries, images=crop, return_tensors="pt")
            
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # 결과 후처리
            target_sizes = torch.Tensor([crop.size[::-1]])
            results_per_crop = self.processor.post_process_object_detection(
                outputs=outputs, 
                target_sizes=target_sizes, 
                threshold=confidence_threshold
            )
            
            # 가장 높은 신뢰도의 탐지 결과 선택
            if len(results_per_crop[0]["scores"]) > 0:
                best_idx = torch.argmax(results_per_crop[0]["scores"])
                best_score = results_per_crop[0]["scores"][best_idx].item()
                best_label_idx = results_per_crop[0]["labels"][best_idx].item()
                best_text = text_queries[best_label_idx]
                
                # 모든 클래스의 점수 계산 (추가 분석용)
                all_scores = {}
                for j, query in enumerate(text_queries):
                    mask = results_per_crop[0]["labels"] == j
                    if mask.any():
                        scores_for_class = results_per_crop[0]["scores"][mask]
                        all_scores[query] = scores_for_class.max().item()
                    else:
                        all_scores[query] = 0.0
                
                result = {
                    'crop_index': i,
                    'best_match': best_text,
                    'confidence': best_score,
                    'all_scores': all_scores,
                    'is_confident': best_score > confidence_threshold
                }
            else:
                result = {
                    'crop_index': i,
                    'best_match': 'unknown',
                    'confidence': 0.0,
                    'all_scores': {query: 0.0 for query in text_queries},
                    'is_confident': False
                }
            
            results.append(result)
            
            # 결과 출력
            print(f"   Best match: {result['best_match']} ({result['confidence']:.4f})")
            for query, score in result['all_scores'].items():
                print(f"   '{query}': {score:.4f}")
        
        return results
    
    def improved_text_queries_generator(self, base_objects):
        """더 구체적이고 구별하기 쉬운 텍스트 쿼리 생성"""
        improved_queries = {}
        
        # 기본 객체별로 더 구체적인 설명 추가
        object_descriptions = {
            'monitor': [
                'computer monitor screen',
                'desktop display screen',
                'LCD monitor with black frame',
                'computer screen showing display'
            ],
            'keyboard': [
                'computer keyboard with keys',
                'QWERTY keyboard layout',
                'keyboard with multiple keys arranged in rows',
                'typing keyboard with letter keys'
            ],
            'speaker': [
                'desktop speaker with driver cone',
                'audio speaker with round driver',
                'computer speaker with mesh grille',
                'speaker with visible driver unit'
            ],
            'mouse': [
                'computer mouse with buttons',
                'optical computer mouse',
                'desktop mouse with scroll wheel',
                'computer pointing device mouse'
            ]
        }
        
        for obj in base_objects:
            if obj in object_descriptions:
                improved_queries[obj] = object_descriptions[obj]
            else:
                improved_queries[obj] = [f'a {obj}']
        
        return improved_queries
    
    def multi_query_classification(self, image_crops, base_objects):
        """여러 쿼리를 사용한 강화된 분류"""
        improved_queries = self.improved_text_queries_generator(base_objects)
        
        final_results = []
        
        for i, crop in enumerate(image_crops):
            print(f"\n🔍 Multi-query analysis for Crop {i+1}")
            
            object_scores = {}
            
            # 각 객체별로 여러 쿼리로 테스트
            for obj_name, queries in improved_queries.items():
                scores_for_object = []
                
                for query in queries:
                    inputs = self.processor(text=[query], images=crop, return_tensors="pt")
                    
                    with torch.no_grad():
                        outputs = self.model(**inputs)
                    
                    target_sizes = torch.Tensor([crop.size[::-1]])
                    results = self.processor.post_process_object_detection(
                        outputs=outputs, 
                        target_sizes=target_sizes, 
                        threshold=0.1  # 낮은 임계값으로 더 많은 결과 수집
                    )
                    
                    if len(results[0]["scores"]) > 0:
                        max_score = results[0]["scores"].max().item()
                        scores_for_object.append(max_score)
                    else:
                        scores_for_object.append(0.0)
                
                # 해당 객체의 평균 점수
                object_scores[obj_name] = np.mean(scores_for_object) if scores_for_object else 0.0
                print(f"   {obj_name}: {object_scores[obj_name]:.4f} (queries: {len(queries)})")
            
            # 최고 점수 객체 선택
            best_object = max(object_scores.keys(), key=lambda k: object_scores[k])
            best_score = object_scores[best_object]
            
            # 신뢰도 계산 (최고 점수와 두 번째 점수의 차이)
            sorted_scores = sorted(object_scores.values(), reverse=True)
            confidence_gap = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]
            
            result = {
                'crop_index': i,
                'best_match': best_object,
                'confidence': best_score,
                'confidence_gap': confidence_gap,
                'all_scores': object_scores,
                'is_confident': confidence_gap > 0.15  # 차이가 0.15 이상이면 신뢰할만함
            }
            
            final_results.append(result)
            
            print(f"   ✅ Final: {best_object} (score: {best_score:.4f}, gap: {confidence_gap:.4f})")
        
        return final_results
    
    def visualize_classification_results(self, image_crops, results):
        """분류 결과 시각화"""
        num_crops = len(image_crops)
        fig, axes = plt.subplots(2, num_crops, figsize=(4*num_crops, 8))
        
        if num_crops == 1:
            axes = axes.reshape(2, 1)
        
        for i, (crop, result) in enumerate(zip(image_crops, results)):
            # 원본 크롭 이미지
            axes[0, i].imshow(crop)
            axes[0, i].set_title(f"Crop {i+1}")
            axes[0, i].axis('off')
            
            # 분류 결과 바차트
            objects = list(result['all_scores'].keys())
            scores = list(result['all_scores'].values())
            
            colors = ['red' if obj == result['best_match'] else 'lightblue' for obj in objects]
            
            axes[1, i].bar(range(len(objects)), scores, color=colors)
            axes[1, i].set_xticks(range(len(objects)))
            axes[1, i].set_xticklabels(objects, rotation=45, ha='right')
            axes[1, i].set_ylim(0, 1)
            axes[1, i].set_title(f"Best: {result['best_match']}\n"
                               f"Conf: {result['confidence']:.3f}")
            axes[1, i].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()

# 사용 예시 함수
def test_with_your_image():
    """실제 사용 예시"""
    classifier = ImprovedObjectClassifier()
    
    # 여러분의 크롭된 이미지들을 로드
    # (YOLO 결과에서 나온 크롭들)
    
    # 예시 - 실제로는 YOLO에서 나온 크롭 이미지들을 사용
    image_crops = [
        Image.open("clip_images/tmpeb_qopzg.PNG"),  # 모니터 크롭
        # Image.open("crop_2.jpg"),  # 키보드 크롭
        # Image.open("crop_3.jpg"),  # 스피커 크롭
    ]
    
    # 탐지하고 싶은 객체들
    target_objects = ['monitor', 'keyboard', 'speaker', 'mouse']
    
    # 개선된 분류 실행
    results = classifier.multi_query_classification(image_crops, target_objects)
    
    # 결과 시각화
    classifier.visualize_classification_results(image_crops, results)
    
    return results

if __name__ == "__main__":
    print("🎯 개선된 객체 분류기")
    print("="*50)
    print("특징:")
    print("- OWL-ViT 기반으로 더 정확한 객체 탐지")
    print("- 다중 쿼리로 신뢰도 향상")
    print("- 신뢰도 갭으로 불확실성 측정")
    print()
    print("설치 명령:")
    print("pip install transformers torch torchvision matplotlib pillow")
    print()
    print("사용법:")
    print("classifier = ImprovedObjectClassifier()")
    print("results = classifier.multi_query_classification(image_crops, target_objects)")

    test_with_your_image()