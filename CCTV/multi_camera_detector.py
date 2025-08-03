import cv2
import torch
import clip
from ultralytics import YOLO
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import threading
import time
from queue import Queue
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CameraConfig:
    """카메라 설정"""
    name: str
    rtsp_url: str
    width: int = 640
    height: int = 480
    fps: int = 30

@dataclass
class Detection:
    """탐지 결과"""
    camera_name: str
    bbox: Tuple[int, int, int, int]
    confidence: float
    label: str
    timestamp: float

class MultiCameraDetector:
    """다중 카메라 객체 탐지 시스템"""
    
    def __init__(self, detection_targets = None):
        # GPU/CPU 설정
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        
        # 모델 로드 (전역으로 한번만)
        self.yolo = YOLO("yolo11n.pt")
        self.clip_model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        
        # 탐지 대상 설정 (딕셔너리 또는 리스트 지원)
        if detection_targets is None:
            self.detection_targets = {"사람": "person", "자동차": "car", "자전거": "bicycle"}
        elif isinstance(detection_targets, dict):
            self.detection_targets = detection_targets
        else:
            # 기존 리스트 형태 호환성 유지
            self.detection_targets = {target: target for target in detection_targets}
        
        self._prepare_clip_features()
        
        # 카메라 관리
        self.cameras: Dict[str, CameraConfig] = {}
        self.camera_threads: Dict[str, threading.Thread] = {}
        self.camera_caps: Dict[str, cv2.VideoCapture] = {}
        self.frame_queues: Dict[str, Queue] = {}
        
        # 탐지 결과 큐
        self.detection_queue = Queue(maxsize=100)
        
        # 실행 상태
        self.running = False
        
        # 한글 폰트 설정
        self._setup_korean_font()
    
    def _setup_korean_font(self):
        """한글 폰트 설정"""
        try:
            # Windows 기본 한글 폰트
            self.font = ImageFont.truetype("malgun.ttf", 20)
            self.font_small = ImageFont.truetype("malgun.ttf", 16)
        except:
            try:
                # 다른 한글 폰트 시도
                self.font = ImageFont.truetype("NanumGothic.ttf", 20)
                self.font_small = ImageFont.truetype("NanumGothic.ttf", 16)
            except:
                # 기본 폰트 사용
                self.font = ImageFont.load_default()
                self.font_small = ImageFont.load_default()
                logger.warning("Korean font not found. Using default font.")
    
    def _put_korean_text(self, img, text, position, font, color=(0, 255, 0)):
        """한글 텍스트를 이미지에 삽입"""
        # OpenCV 이미지를 PIL 이미지로 변환
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        
        # 텍스트 그리기
        draw.text(position, text, font=font, fill=color[::-1])  # BGR to RGB
        
        # PIL 이미지를 OpenCV 이미지로 변환
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        
    def _prepare_clip_features(self):
        """CLIP 특징 미리 계산"""
        # 딕셔너리의 value(상세 설명)를 CLIP 프롬프트로 사용
        text_prompts = list(self.detection_targets.values())
        with torch.no_grad():
            text_tokens = clip.tokenize(text_prompts).to(self.device)
            self.text_features = self.clip_model.encode_text(text_tokens)
            self.text_features = self.text_features / self.text_features.norm(dim=-1, keepdim=True)
        
        # 라벨(key) 목록 저장
        self.target_labels = list(self.detection_targets.keys())
        logger.info(f"CLIP features prepared for: {dict(zip(self.target_labels, text_prompts))}")
    
    def add_camera(self, name: str, rtsp_url: str, width: int = 640, height: int = 480):
        """카메라 추가"""
        self.cameras[name] = CameraConfig(name, rtsp_url, width, height)
        self.frame_queues[name] = Queue(maxsize=2)
        logger.info(f"Camera added: {name} -> {rtsp_url}")
    
    def _camera_thread(self, camera_name: str):
        """개별 카메라 스레드"""
        config = self.cameras[camera_name]
        cap = cv2.VideoCapture(config.rtsp_url)
        
        # 해상도 설정
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        cap.set(cv2.CAP_PROP_FPS, config.fps)
        
        self.camera_caps[camera_name] = cap
        frame_queue = self.frame_queues[camera_name]
        
        logger.info(f"Camera thread started: {camera_name}")
        
        while self.running:
            ret, frame = cap.read()
            if ret:
                # 최신 프레임만 유지
                if frame_queue.full():
                    try:
                        frame_queue.get_nowait()
                    except:
                        pass
                frame_queue.put((frame, time.time()))
            else:
                logger.warning(f"Failed to read from camera: {camera_name}")
                time.sleep(0.1)
        
        cap.release()
        logger.info(f"Camera thread stopped: {camera_name}")
    
    def _detect_objects(self, frame: np.ndarray, camera_name: str, timestamp: float) -> List[Detection]:
        """객체 탐지 수행"""
        detections = []
        
        # YOLO 탐지
        results = self.yolo(frame, verbose=False)
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return detections

        # 사람만 필터링 (YOLO class 0)
        valid_boxes = []
        for box in boxes:
            if int(box.cls[0]) == 0 and box.conf[0] > 0.5:  # 사람, 신뢰도 0.5 이상
                x1, y1, x2, y2 = box.xyxy[0].int().cpu().numpy()
                valid_boxes.append((x1, y1, x2, y2, float(box.conf[0])))
        
        if not valid_boxes:
            return detections
        
        # CLIP으로 세부 분류
        cropped_images = []
        for x1, y1, x2, y2, conf in valid_boxes:
            crop = frame[y1:y2, x1:x2]
            if crop.size > 0:
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(crop_rgb)
                cropped_images.append(self.preprocess(pil_img).unsqueeze(0))
        
        if cropped_images:
            # 배치 처리
            image_batch = torch.cat(cropped_images).to(self.device)
            
            with torch.no_grad():
                image_features = self.clip_model.encode_image(image_batch)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                similarities = image_features @ self.text_features.T
            
            # 결과 생성
            for i, (bbox_conf, sim) in enumerate(zip(valid_boxes, similarities)):
                x1, y1, x2, y2, yolo_conf = bbox_conf
                
                # 가장 높은 유사도의 라벨 선택
                best_idx = torch.argmax(sim).item()
                best_similarity = sim[best_idx].item()
                
                if best_similarity > 0.2:  # 임계값
                    # 딕셔너리의 key(간단한 라벨) 사용
                    label = self.target_labels[best_idx]
                    detections.append(Detection(
                        camera_name=camera_name,
                        bbox=(x1, y1, x2, y2),
                        confidence=yolo_conf,
                        label=label,
                        timestamp=timestamp
                    ))
        
        return detections
    
    def _detection_thread(self):
        """탐지 처리 스레드"""
        logger.info("Detection thread started")
        frame_counters = {name: 0 for name in self.cameras.keys()}
        
        while self.running:
            for camera_name in self.cameras.keys():
                frame_queue = self.frame_queues[camera_name]
                
                if not frame_queue.empty():
                    frame, timestamp = frame_queue.get()
                    frame_counters[camera_name] += 1
                    
                    # 프레임 스킵으로 성능 최적화 (매 3번째 프레임만 처리)
                    if frame_counters[camera_name] % 3 == 0:
                        detections = self._detect_objects(frame, camera_name, timestamp)
                        
                        # 탐지 결과를 큐에 추가
                        for detection in detections:
                            if not self.detection_queue.full():
                                self.detection_queue.put(detection)
            
            time.sleep(0.01)  # CPU 사용률 조절
        
        logger.info("Detection thread stopped")
    
    def _display_thread(self):
        """디스플레이 스레드"""
        logger.info("Display thread started")
        
        while self.running:
            frames_to_display = {}
            
            # 각 카메라의 최신 프레임 수집
            for camera_name in self.cameras.keys():
                frame_queue = self.frame_queues[camera_name]
                if not frame_queue.empty():
                    frame, _ = frame_queue.get()
                    frames_to_display[camera_name] = frame
            
            # 탐지 결과 오버레이
            recent_detections = {}
            while not self.detection_queue.empty():
                detection = self.detection_queue.get()
                if detection.camera_name not in recent_detections:
                    recent_detections[detection.camera_name] = []
                recent_detections[detection.camera_name].append(detection)
            
            # 프레임에 탐지 결과 그리기
            for camera_name, frame in frames_to_display.items():
                if camera_name in recent_detections:
                    for detection in recent_detections[camera_name]:
                        x1, y1, x2, y2 = detection.bbox
                        
                        # 라벨별 색상
                        color = (0, 255, 0) if detection.label == "person" else (255, 0, 0)
                        
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        label_text = f"{detection.label} ({detection.confidence:.2f})"
                        
                        # 한글 텍스트 표시
                        frame = self._put_korean_text(frame, label_text, (x1, y1-25), 
                                                    self.font_small, color)
                
                # 화면 크기 조절
                frame = cv2.resize(frame, (960, 540))
                # 윈도우 표시
                cv2.imshow(f"Camera: {camera_name}", frame)
            
            # 종료 체크
            if cv2.waitKey(1) & 0xFF == ord('q'):
                self.stop()
                break
        
        cv2.destroyAllWindows()
        logger.info("Display thread stopped")
    
    def start(self):
        """시스템 시작"""
        if not self.cameras:
            logger.error("No cameras configured!")
            return
            
        self.running = True
        
        # 카메라 스레드 시작
        for camera_name in self.cameras.keys():
            thread = threading.Thread(target=self._camera_thread, args=(camera_name,))
            thread.daemon = True
            thread.start()
            self.camera_threads[camera_name] = thread
        
        # 탐지 스레드 시작
        detection_thread = threading.Thread(target=self._detection_thread)
        detection_thread.daemon = True
        detection_thread.start()
        
        # 디스플레이 스레드 시작
        display_thread = threading.Thread(target=self._display_thread)
        display_thread.daemon = True
        display_thread.start()
        
        logger.info(f"Multi-camera detection system started with {len(self.cameras)} cameras")
        
        # 메인 스레드 대기
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """시스템 정지"""
        logger.info("Stopping multi-camera detection system...")
        self.running = False
        
        # 카메라 해제
        for cap in self.camera_caps.values():
            cap.release()
        
        cv2.destroyAllWindows()
    
    def set_detection_targets(self, targets):
        """탐지 대상 변경 (딕셔너리 또는 리스트)"""
        if isinstance(targets, dict):
            self.detection_targets = targets
        else:
            # 리스트인 경우 딕셔너리로 변환
            self.detection_targets = {target: target for target in targets}
        
        self._prepare_clip_features()
        logger.info(f"Detection targets updated: {self.detection_targets}")

# 사용 예시
if __name__ == "__main__":
    # 탐지할 객체 목록 설정 (딕셔너리 형태로 라벨:상세설명)
    custom_targets = {
        "사람": "a person standing or sitting",  # 영어로 변경
        "쓰러진사람": "a person lying on the ground"
    }
    
    # 탐지기 생성
    detector = MultiCameraDetector(detection_targets=custom_targets)
    
    # 카메라 추가 (여러 대 가능)
    detector.add_camera("Camera1", "rtsp://admin:Password12!@192.168.0.25:554/stream1", 640, 480)
    # detector.add_camera("Camera2", "rtsp://admin:password@192.168.0.26:554/stream1", 640, 480)
    # detector.add_camera("Webcam", 0, 640, 480)  # 웹캠도 가능
    
    # 실행 중에 탐지 대상 변경 가능 (딕셔너리 또는 리스트)
    # detector.set_detection_targets({
    #     "위험물": "폭발물이나 화학물질 같은 위험한 물건",
    #     "화재": "불꽃이나 연기가 나는 상황"
    # })
    
    # 시스템 시작
    detector.start()