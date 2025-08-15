import os
import time
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModel

# SigLIP 2를 사용하려면 최신 transformers가 필요합니다
# pip install git+https://github.com/huggingface/transformers@v4.49.0-SigLIP-2

def load_and_process_image(image_path):
    """이미지 로드 및 전처리"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    image = Image.open(image_path).convert("RGB")
    print(f"Image size: {image.size}")
    return image

def setup_model(model_name="google/siglip2-large-patch16-384"):
    """모델 및 프로세서 설정"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    print("Loading model and processor...")
    model_load_start = time.time()
    
    try:
        # SigLIP 2의 경우 AutoModel과 AutoProcessor 사용
        model = AutoModel.from_pretrained(model_name).to(device)
        processor = AutoProcessor.from_pretrained(model_name)
        
        print(f"Model load time: {time.time() - model_load_start:.4f} sec")
        
        # GPU 메모리 정보 출력
        if device == "cuda":
            print(f"GPU memory allocated: {torch.cuda.memory_allocated()/1024**2:.2f} MB")
            
        return model, processor, device
        
    except Exception as e:
        print(f"Error loading model: {e}")
        print("Trying fallback to SigLIP v1...")
        
        # SigLIP v1으로 fallback
        try:
            from transformers import SiglipProcessor, SiglipModel
            fallback_model = "google/siglip-base-patch16-224"
            print(f"Loading fallback model: {fallback_model}")
            
            model = SiglipModel.from_pretrained(fallback_model).to(device)
            processor = SiglipProcessor.from_pretrained(fallback_model)
            
            print(f"Fallback model load time: {time.time() - model_load_start:.4f} sec")
            return model, processor, device
            
        except Exception as fallback_error:
            print(f"Fallback also failed: {fallback_error}")
            raise

def calculate_similarities(model, processor, device, image, texts_list):
    """이미지-텍스트 유사도 계산"""
    # 입력 전처리 (SigLIP 2는 특별한 패딩이 필요)
    inputs = processor(
        text=texts_list,
        images=image,
        return_tensors="pt",
        padding="max_length",  # SigLIP 2에서 중요
        max_length=64         # SigLIP 2 기본값
    ).to(device)
    
    # 추론 실행
    start_time = time.time()
    with torch.no_grad():
        outputs = model(**inputs)
    inference_time = time.time() - start_time
    
    # 임베딩 추출
    image_embeds = outputs.image_embeds
    text_embeds = outputs.text_embeds
    
    # 정규화 (선택사항 - 더 안정적인 결과)
    image_embeds_norm = image_embeds / image_embeds.norm(dim=-1, keepdim=True)
    text_embeds_norm = text_embeds / text_embeds.norm(dim=-1, keepdim=True)
    
    # 유사도 계산
    logits = image_embeds_norm @ text_embeds_norm.T
    
    # SigLIP는 sigmoid 활성화 사용
    probs = torch.sigmoid(logits).cpu().numpy()
    
    return probs, inference_time

def main():
    # 전체 실행 시작 시간
    total_start = time.time()
    
    try:
        # 1. 모델 설정
        model, processor, device = setup_model()
        
        # 2. 이미지 로드
        image_path = "clip_images/tmpeb_qopzg.PNG"
        # image_path = r"media\screenshots\3_20250813_113219_object_9.jpg"
        image = load_and_process_image(image_path)
        
        # 3. 텍스트 리스트
        texts_list = [
            "computer monitor screen with black frame",    # 모니터의 시각적 특징 강조
            "keyboard with rows of keys and letters",      # 키보드의 독특한 특징
            "speaker with round driver and mesh grille"    # 스피커의 독특한 특징
        ]
        
        # 4. 유사도 계산
        probs, inference_time = calculate_similarities(
            model, processor, device, image, texts_list
        )
        
        print(f"Inference time: {inference_time:.4f} sec")
        
        # 5. 결과 출력
        print("\nResults:")
        for text, prob in zip(texts_list, probs[0]):
            confidence = "High" if prob > 0.7 else "Medium" if prob > 0.3 else "Low"
            print(f"'{text}': {prob:.4f} ({confidence})")
        
        # 6. 가장 높은 확률의 항목
        best_match_idx = probs[0].argmax()
        print(f"\nBest match: '{texts_list[best_match_idx]}' ({probs[0][best_match_idx]:.4f})")
        
        # 7. GPU 메모리 정리
        if device == "cuda":
            torch.cuda.empty_cache()
            
    except Exception as e:
        print(f"Error during execution: {e}")
        
    finally:
        # 8. 전체 실행 시간
        print(f"\nTotal execution time: {time.time() - total_start:.4f} sec")

if __name__ == "__main__":
    main()