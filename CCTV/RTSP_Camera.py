import clip
import torch
from ultralytics import YOLO
import cv2
from PIL import Image
import numpy as np
import datetime
import os
from threading import Thread, Lock
from queue import Queue
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
import logging
import json
from concurrent.futures import ThreadPoolExecutor
import base64
from collections import deque

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Detection:
    """감지된 객체 정보"""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    label: str
    timestamp: float
    camera_id: str = None

@dataclass
class CameraConfig:
    """카메라 설정 정보"""
    camera_id: str
    name: str
    rtsp_url: str
    detection_objects: Dict[str, str]
    detection_alerts: Dict[str, bool] = None  # display_name -> has_alert 매핑
    max_fps: int = 15
    is_active: bool = True

class KalmanTracker:
    """칼만 필터 기반 추적기"""
    def __init__(self, initial_bbox):
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.measurementMatrix = np.array([[1, 0, 0, 0],
                                              [0, 1, 0, 0]], np.float32)
        self.kf.transitionMatrix = np.array([[1, 0, 1, 0],
                                             [0, 1, 0, 1],
                                             [0, 0, 1, 0],
                                             [0, 0, 0, 1]], np.float32)
        self.kf.processNoiseCov = 0.03 * np.eye(4, dtype=np.float32)
        
        # 초기 위치 설정
        cx = (initial_bbox[0] + initial_bbox[2]) / 2
        cy = (initial_bbox[1] + initial_bbox[3]) / 2
        self.kf.statePre = np.array([cx, cy, 0, 0], dtype=np.float32)
        self.kf.statePost = np.array([cx, cy, 0, 0], dtype=np.float32)
        
        self.width = initial_bbox[2] - initial_bbox[0]
        self.height = initial_bbox[3] - initial_bbox[1]
        self.missed_frames = 0
        
    def predict(self):
        """다음 위치 예측"""
        prediction = self.kf.predict()
        cx, cy = prediction[0], prediction[1]
        return (int(cx - self.width/2), int(cy - self.height/2),
                int(cx + self.width/2), int(cy + self.height/2))
    
    def update(self, bbox):
        """측정값으로 업데이트"""
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        self.width = bbox[2] - bbox[0]
        self.height = bbox[3] - bbox[1]
        
        measurement = np.array([[cx], [cy]], dtype=np.float32)
        self.kf.correct(measurement)
        self.missed_frames = 0
        
    def mark_missed(self):
        """프레임 놓침 표시"""
        self.missed_frames += 1

class SmartObjectTracker:
    """스마트 객체 추적 시스템 (사용자 정의 객체 지원)"""
    def __init__(self, track_id: int, initial_detection: Detection):
        self.id = track_id
        self.tracker = KalmanTracker(initial_detection.bbox)
        self.label = initial_detection.label
        self.confidence_history = [initial_detection.confidence]
        self.label_history = [initial_detection.label]
        self.last_update = initial_detection.timestamp
        self.creation_time = initial_detection.timestamp
        self.camera_id = initial_detection.camera_id
        
        # 상태 안정화를 위한 변수
        self.stable_label_count = 0
        self.current_stable_label = initial_detection.label
        
    def predict_bbox(self) -> Tuple[int, int, int, int]:
        """예측된 바운딩 박스 반환"""
        return self.tracker.predict()
    
    def update(self, detection: Detection):
        """추적기 업데이트"""
        self.tracker.update(detection.bbox)
        self.last_update = detection.timestamp
        
        # 라벨 히스토리 업데이트 (최근 5개만 유지)
        self.label_history.append(detection.label)
        if len(self.label_history) > 5:
            self.label_history.pop(0)
        
        # 안정적인 라벨 결정
        label_counts = {}
        for label in self.label_history:
            label_counts[label] = label_counts.get(label, 0) + 1
        
        most_common_label = max(label_counts, key=label_counts.get)
        if most_common_label == self.current_stable_label:
            self.stable_label_count += 1
        else:
            self.stable_label_count = 1
            self.current_stable_label = most_common_label
        
        # 3프레임 이상 같은 라벨이면 변경
        if self.stable_label_count >= 3:
            self.label = self.current_stable_label
    
    def mark_missed(self):
        """놓친 프레임 처리"""
        self.tracker.mark_missed()
    
    def should_remove(self, current_time: float) -> bool:
        """제거 여부 판단"""
        # 너무 많은 프레임을 놓쳤거나 오랫동안 업데이트 안됨
        return (self.tracker.missed_frames > 3 or 
                current_time - self.last_update > 1.0)

class MultiCameraObjectDetector:
    """다중 카메라 객체 감지 시스템"""
    def __init__(self, camera_configs: List[CameraConfig] = None):
        # 장치 설정
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        
        # 모델 로드 (한 번만 로드)
        self.clip_model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        self.yolo = YOLO("yolo11n.pt")
        
        # 카메라 설정 (빈 리스트로 시작)
        self.camera_configs = []
        self.cameras = {}  # camera_id: cv2.VideoCapture
        self.camera_threads = {}  # camera_id: Thread
        self.camera_queues = {}  # camera_id: Queue
        
        
        # 추적 관련 (카메라별)
        self.trackers = {}  # camera_id: {tracker_id: tracker}
        self.next_tracker_ids = {}  # camera_id: int
        self.tracker_locks = {}  # camera_id: Lock
        
        # 프레임 버퍼 (카메라별)
        self.frame_queues = {}  # camera_id: Queue
        
        # 웹 스트리밍을 위한 프레임 버퍼
        self.latest_frames = {}  # camera_id: (frame, timestamp)
        self.frame_locks = {}  # camera_id: Lock (for web access)
        
        # 성능 모니터링
        self.frame_times = {}
        
        # 웹 모드 설정
        self.web_mode = False
        
        # 스크린샷 설정
        self.screenshot_dir = "object_detection_screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.last_detection_screenshot = {}  # camera_id: {tracker_id: timestamp}
        
        # CLIP 텍스트 특징 (동적 생성)
        self.text_features_cache = {}  # detection_objects의 해시: features
        
        # 실행 제어
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=10)  # 고정 값으로 설정
        
        # 초기 카메라 설정이 있으면 추가 (단, 연결 실패 시 무시)
        if camera_configs:
            for config in camera_configs:
                self.add_camera(config)
    
    def _prepare_clip_features(self, detection_objects: Dict[str, str]) -> Tuple[torch.Tensor, List[str]]:
        """CLIP 특징 동적 계산 (캐싱)"""
        # 영어 토큰만 추출
        english_tokens = list(detection_objects.values())
        korean_labels = list(detection_objects.keys())
        
        objects_key = tuple(sorted(english_tokens))
        if objects_key in self.text_features_cache:
            return self.text_features_cache[objects_key], korean_labels
        
        with torch.no_grad():
            text_tokens = clip.tokenize(english_tokens).to(self.device)
            text_features = self.clip_model.encode_text(text_tokens)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            self.text_features_cache[objects_key] = text_features
            return text_features, korean_labels
    
    def add_camera(self, config: CameraConfig):
        """카메라 추가"""
        # camera_id를 문자열로 통일
        camera_id = str(config.camera_id)
        
        if camera_id in self.cameras:
            logger.warning(f"Camera {camera_id} already exists")
            return False
        
        cap = cv2.VideoCapture(config.rtsp_url)
        
        if not cap.isOpened():
            logger.error(f"Failed to open camera {camera_id}: {config.rtsp_url}")
            cap.release()  # 연결 실패 시 리소스 해제
            return False
        
        self.cameras[camera_id] = cap
        
        # config.camera_id도 문자열로 변경
        config.camera_id = camera_id
        
        self.camera_configs.append(config)
        self.cameras[camera_id] = cap
        self.camera_queues[camera_id] = Queue(maxsize=2)
        self.frame_queues[camera_id] = Queue(maxsize=2)
        self.trackers[camera_id] = {}
        self.next_tracker_ids[camera_id] = 0
        self.tracker_locks[camera_id] = Lock()
        self.frame_times[camera_id] = []
        self.last_detection_screenshot[camera_id] = {}
        
        # 웹 스트리밍을 위한 추가 설정
        self.latest_frames[camera_id] = (None, 0)
        self.frame_locks[camera_id] = Lock()
        
        logger.info(f"Camera {camera_id} added successfully")
        return True
    
    def remove_camera(self, camera_id: str):
        """카메라 제거"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        
        if camera_id not in self.cameras:
            logger.warning(f"Camera {camera_id} not found")
            return False
        
        # 카메라 정리
        self.cameras[camera_id].release()
        del self.cameras[camera_id]
        del self.camera_queues[camera_id]
        del self.frame_queues[camera_id]
        del self.trackers[camera_id]
        del self.next_tracker_ids[camera_id]
        del self.tracker_locks[camera_id]
        del self.frame_times[camera_id]
        del self.last_detection_screenshot[camera_id]
        del self.latest_frames[camera_id]
        del self.frame_locks[camera_id]
        
        # 설정에서 제거
        self.camera_configs = [c for c in self.camera_configs if c.camera_id != camera_id]
        
        logger.info(f"Camera {camera_id} removed successfully")
        return True
    
    def _calculate_iou(self, box1: Tuple, box2: Tuple) -> float:
        """IOU 계산 (최적화)"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def _frame_reader_thread(self, camera_id: str):
        """카메라별 프레임 읽기 스레드"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        
        if camera_id not in self.cameras:
            logger.error(f"Camera {camera_id} not found in _frame_reader_thread")
            return
            
        cap = self.cameras[camera_id]
        frame_queue = self.frame_queues[camera_id]
        
        while self.running:
            ret, frame = cap.read()
            if ret:
                # 오래된 프레임 버리고 최신 프레임만 유지
                if frame_queue.full():
                    try:
                        frame_queue.get_nowait()
                    except:
                        pass
                frame_queue.put(frame)
            else:
                logger.warning(f"Failed to read from camera {camera_id}")
                time.sleep(0.5)
    
    def _process_detections_batch(self, camera_id: str, frame: np.ndarray, boxes, detection_objects: Dict[str, str]) -> List[Detection]:
        """배치 단위로 감지 처리"""
        detections = []
        current_time = time.time()
        
        # YOLO 감지 필터링 (사람 객체만)
        valid_indices = []
        valid_boxes = []
        
        for i, box in enumerate(boxes):
            if int(box.cls[0]) == 0 and box.conf[0] > 0.5:  # person class, confidence > 0.5
                x1, y1, x2, y2 = box.xyxy[0].int().cpu().numpy()
                valid_indices.append(i)
                valid_boxes.append((x1, y1, x2, y2))
        
        if not valid_boxes:
            return detections
        
        # CLIP 특징 준비
        text_features, korean_labels = self._prepare_clip_features(detection_objects)
        
        # CLIP 처리를 위한 이미지 배치 준비
        cropped_images = []
        for x1, y1, x2, y2 in valid_boxes:
            crop = frame[y1:y2, x1:x2]
            if crop.size > 0:  # 유효한 크롭인지 확인
                crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(crop_rgb)
                cropped_images.append(self.preprocess(pil_img).unsqueeze(0))
        
        if cropped_images:
            # 배치 처리
            image_batch = torch.cat(cropped_images).to(self.device)
            
            with torch.no_grad():
                image_features = self.clip_model.encode_image(image_batch)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                similarities = image_features @ text_features.T
            
            # 결과 수집
            for i, (box, sim) in enumerate(zip(valid_boxes, similarities)):
                # 가장 높은 유사도의 한국어 라벨 선택
                best_idx = torch.argmax(sim).item()
                label = korean_labels[best_idx]
                confidence = float(boxes[valid_indices[i]].conf[0])
                
                detections.append(Detection(
                    bbox=box,
                    confidence=confidence,
                    label=label,
                    timestamp=current_time,
                    camera_id=camera_id
                ))
        
        return detections
    
    def _update_trackers(self, camera_id: str, detections: List[Detection], current_time: float):
        """추적기 업데이트 (헝가리안 알고리즘 스타일)"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        
        if camera_id not in self.tracker_locks:
            logger.error(f"Camera {camera_id} not found in _update_trackers")
            return
            
        with self.tracker_locks[camera_id]:
            camera_trackers = self.trackers[camera_id]
            # 예측된 위치와 감지 매칭
            if camera_trackers and detections:
                # 비용 매트릭스 계산
                cost_matrix = np.zeros((len(camera_trackers), len(detections)))
                tracker_ids = list(camera_trackers.keys())
                
                for i, tracker_id in enumerate(tracker_ids):
                    tracker = camera_trackers[tracker_id]
                    predicted_bbox = tracker.predict_bbox()
                    
                    for j, detection in enumerate(detections):
                        iou = self._calculate_iou(predicted_bbox, detection.bbox)
                        cost_matrix[i, j] = 1 - iou  # IOU를 비용으로 변환
                
                # 간단한 그리디 매칭
                matched_trackers = set()
                matched_detections = set()
                
                # IOU 기준으로 정렬하여 매칭
                matches = []
                for i in range(len(tracker_ids)):
                    for j in range(len(detections)):
                        if cost_matrix[i, j] < 0.7:  # IOU > 0.3
                            matches.append((cost_matrix[i, j], i, j))
                
                matches.sort()  # 낮은 비용부터
                
                for cost, i, j in matches:
                    if i not in matched_trackers and j not in matched_detections:
                        tracker_id = tracker_ids[i]
                        camera_trackers[tracker_id].update(detections[j])
                        matched_trackers.add(i)
                        matched_detections.add(j)
                
                # 매칭되지 않은 추적기 처리
                for i, tracker_id in enumerate(tracker_ids):
                    if i not in matched_trackers:
                        camera_trackers[tracker_id].mark_missed()
                
                # 새로운 감지 추가
                for j, detection in enumerate(detections):
                    if j not in matched_detections:
                        camera_trackers[self.next_tracker_ids[camera_id]] = SmartObjectTracker(
                            self.next_tracker_ids[camera_id], detection
                        )
                        self.next_tracker_ids[camera_id] += 1
            
            elif detections:  # 추적기 없고 감지만 있음
                for detection in detections:
                    camera_trackers[self.next_tracker_ids[camera_id]] = SmartObjectTracker(
                        self.next_tracker_ids[camera_id], detection
                    )
                    self.next_tracker_ids[camera_id] += 1
            
            # 오래된 추적기 제거
            trackers_to_remove = []
            for tracker_id, tracker in camera_trackers.items():
                if tracker.should_remove(current_time):
                    trackers_to_remove.append(tracker_id)
            
            for tracker_id in trackers_to_remove:
                del camera_trackers[tracker_id]
    
    def _draw_and_save(self, camera_id: str, frame: np.ndarray, config: CameraConfig) -> np.ndarray:
        """시각화 및 저장"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        
        current_time = time.time()
        display_frame = frame.copy()
        
        if camera_id not in self.tracker_locks:
            logger.error(f"Camera {camera_id} not found in _draw_and_save")
            return display_frame
            
        with self.tracker_locks[camera_id]:
            camera_trackers = self.trackers[camera_id]
            for tracker_id, tracker in camera_trackers.items():
                bbox = tracker.predict_bbox()
                label = tracker.label
                
                # has_alert 기반 색상 설정
                if config.detection_alerts and label in config.detection_alerts:
                    has_alert = config.detection_alerts[label]
                    color = (0, 0, 255) if has_alert else (0, 255, 0)  # 빨강 or 초록
                else:
                    color = (128, 128, 128)  # 기본 회색
                
                # 투명도 효과 (놓친 프레임에 따라)
                alpha = max(0.3, 1.0 - (tracker.tracker.missed_frames * 0.3))
                thickness = max(1, int(2 * alpha))
                
                # 박스 그리기
                cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), 
                            color, thickness)
                
                # 라벨 텍스트 (한국어 지원을 위해 PIL 사용)
                text = f"{label} #{tracker_id}"
                try:
                    # PIL로 한글 텍스트 렌더링
                    from PIL import ImageFont, ImageDraw
                    pil_img = Image.fromarray(cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB))
                    draw = ImageDraw.Draw(pil_img)
                    
                    # 기본 폰트 사용 (시스템에 따라 다를 수 있음)
                    try:
                        font = ImageFont.truetype("malgun.ttf", 20)  # Windows 맑은 고딕
                    except:
                        try:
                            font = ImageFont.truetype("NanumGothic.ttf", 20)  # 나눔고딕
                        except:
                            font = ImageFont.load_default()
                    
                    # RGB 색상으로 변환 (BGR -> RGB)
                    rgb_color = (color[2], color[1], color[0])
                    draw.text((bbox[0], bbox[1] - 25), text, font=font, fill=rgb_color)
                    
                    # PIL 이미지를 다시 OpenCV로 변환
                    display_frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                except Exception as e:
                    # PIL 실패 시 기본 OpenCV 텍스트로 폴백
                    cv2.putText(display_frame, text, (bbox[0], bbox[1] - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, thickness)
                
                # has_alert가 true인 객체만 스크린샷 저장
                if (label in config.detection_objects.keys() and 
                    config.detection_alerts and 
                    label in config.detection_alerts and 
                    config.detection_alerts[label]):  # has_alert가 True인 경우만
                    
                    camera_screenshots = self.last_detection_screenshot[camera_id]
                    last_screenshot = camera_screenshots.get(tracker_id, 0)
                    if current_time - last_screenshot > 5.0:  # 5초 간격
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        safe_label = label.replace(" ", "_").replace("/", "_")
                        filename = f"{self.screenshot_dir}/ALERT_{safe_label}_{camera_id}_{tracker_id}_{timestamp}.jpg"
                        cv2.imwrite(filename, frame)
                        logger.info(f"경고 객체 감지! Camera: {camera_id}, Object: {label}, ID: {tracker_id}, File: {filename}")
                        camera_screenshots[tracker_id] = current_time
        
        # 카메라 정보 및 FPS 표시
        cv2.putText(display_frame, f"Camera: {config.name}", (10, 30),
                  cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        if camera_id in self.frame_times and self.frame_times[camera_id]:
            avg_fps = len(self.frame_times[camera_id]) / sum(self.frame_times[camera_id])
            cv2.putText(display_frame, f"FPS: {avg_fps:.1f}", (10, 60),
                      cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return display_frame
        
    def _process_camera(self, config: CameraConfig):
        """개별 카메라 처리 스레드"""
        # camera_id를 문자열로 통일
        camera_id = str(config.camera_id)
        
        if camera_id not in self.frame_queues:
            logger.error(f"Camera {camera_id} not found in _process_camera")
            return
            
        frame_queue = self.frame_queues[camera_id]
        frame_count = 0
        process_every_n = max(1, int(30 / config.max_fps))  # FPS 제한
        
        while self.running:
            if not frame_queue.empty():
                frame = frame_queue.get()
                frame_start = time.time()
                
                # 주기적 처리
                if frame_count % process_every_n == 0:
                    # YOLO 감지
                    results = self.yolo(frame, verbose=False)
                    
                    # 배치 처리
                    detections = self._process_detections_batch(
                        camera_id, frame, results[0].boxes, config.detection_objects
                    )
                    
                    # 추적기 업데이트
                    self._update_trackers(camera_id, detections, frame_start)
                
                # 시각화
                display_frame = self._draw_and_save(camera_id, frame, config)
                
                # 웹 스트리밍을 위한 프레임 저장
                if camera_id in self.frame_locks:
                    with self.frame_locks[camera_id]:
                        self.latest_frames[camera_id] = (display_frame.copy(), time.time())
                else:
                    logger.warning(f"Frame lock not found for camera {camera_id}")
                
                # 데스크톱 모드에서만 화면 표시
                if not self.web_mode:
                    resized_frame = cv2.resize(display_frame, (640, 480))
                    cv2.imshow(f'Detection System - {config.name}', resized_frame)
                
                # 성능 모니터링
                frame_time = time.time() - frame_start
                if camera_id not in self.frame_times:
                    self.frame_times[camera_id] = []
                self.frame_times[camera_id].append(frame_time)
                if len(self.frame_times[camera_id]) > 30:
                    self.frame_times[camera_id].pop(0)
                
                frame_count += 1
            
            # 데스크톱 모드에서만 키보드 입력 체크
            if not self.web_mode and cv2.waitKey(1) & 0xFF == ord('q'):
                self.running = False
                break
            
            time.sleep(0.01)  # CPU 사용률 조절
    
    def run(self, web_mode=False):
        """메인 실행 루프"""
        if not self.camera_configs:
            logger.error("No camera configurations provided")
            return
        
        self.web_mode = web_mode
        self.running = True
        
        # 실제 연결된 카메라만 스레드 시작
        started_cameras = 0
        for config in self.camera_configs:
            camera_id = str(config.camera_id)
            
            # 카메라가 실제로 연결되어 있고 활성화되어 있는지 확인
            if config.is_active and camera_id in self.cameras:
                # 프레임 읽기 스레드
                reader_thread = Thread(target=self._frame_reader_thread, args=(camera_id,))
                reader_thread.daemon = True
                reader_thread.start()
                
                # 카메라 처리 스레드
                process_thread = Thread(target=self._process_camera, args=(config,))
                process_thread.daemon = True
                process_thread.start()
                
                self.camera_threads[camera_id] = (reader_thread, process_thread)
                started_cameras += 1
            else:
                logger.warning(f"Skipping camera {camera_id} - not connected or inactive")
        
        logger.info(f"Started {started_cameras} camera(s)")
        
        try:
            # 메인 스레드는 종료 신호만 대기
            if not self.web_mode:
                while self.running:
                    key = cv2.waitKey(100) & 0xFF
                    if key == ord('q'):
                        logger.info("Quit signal received")
                        break
                    elif key == ord('s'):  # 스크린샷 저장
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        logger.info(f"Manual screenshot saved at {timestamp}")
            else:
                # 웹 모드에서는 무한 대기
                while self.running:
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """리소스 정리"""
        logger.info("Cleaning up resources...")
        self.running = False
        
        # 카메라 해제
        for camera_id, cap in self.cameras.items():
            cap.release()
            logger.info(f"Camera {camera_id} released")
        
        # ThreadPoolExecutor 종료
        self.executor.shutdown(wait=True)
        
        # OpenCV 윈도우 정리 (데스크톱 모드에서만)
        if not self.web_mode:
            cv2.destroyAllWindows()
        logger.info("Cleanup completed")
    
    @classmethod
    def from_django_config(cls, django_camera_configs):
        """Django 모델에서 설정 로드 (Camera와 TargetLabel 모델 사용)"""
        camera_configs = []
        for django_config in django_camera_configs:
            # TargetLabel에서 감지 객체 설정과 알림 설정 가져오기
            detection_objects = {}
            detection_alerts = {}
            for target_label in django_config.target_labels.all():
                detection_objects[target_label.display_name] = target_label.label_name
                detection_alerts[target_label.display_name] = target_label.has_alert
            
            # 기본 감지 객체 설정 (TargetLabel이 없는 경우)
            if not detection_objects:
                detection_objects = {
                    "서 있는 사람": "a standing person",
                    "쓰러진 사람": "a fallen person lying on the ground",
                    "앉아 있는 사람": "a sitting person",
                    "걷는 사람": "a walking person",
                    "뛰는 사람": "a running person"
                }
                detection_alerts = {
                    "서 있는 사람": False,
                    "쓰러진 사람": True,
                    "앉아 있는 사람": False,
                    "걷는 사람": False,
                    "뛰는 사람": False
                }
            
            config = CameraConfig(
                camera_id=str(django_config.id),
                name=django_config.name,
                rtsp_url=django_config.rtsp_url,
                detection_objects=detection_objects,
                detection_alerts=detection_alerts,
                max_fps=15,  # 기본값
                is_active=True
            )
            camera_configs.append(config)
        
        # 인스턴스 생성 후 실제 카메라 연결 확인
        detector = cls([])
        for config in camera_configs:
            success = detector.add_camera(config)
            if not success:
                logger.warning(f"Failed to add camera {config.camera_id} ({config.name})")
        
        return detector
    
    def get_camera_status(self) -> Dict[str, Any]:
        """모든 카메라 상태 반환"""
        status = {}
        for config in self.camera_configs:
            camera_id = str(config.camera_id)
            status[camera_id] = {
                'name': config.name,
                'is_active': config.is_active,
                'is_connected': camera_id in self.cameras and self.cameras[camera_id].isOpened(),
                'tracker_count': len(self.trackers.get(camera_id, {})),
                'avg_fps': (
                    len(self.frame_times[camera_id]) / sum(self.frame_times[camera_id])
                    if camera_id in self.frame_times and self.frame_times[camera_id]
                    else 0
                )
            }
        return status
    
    def update_detection_objects(self, camera_id: str, detection_objects: Dict[str, str], detection_alerts: Dict[str, bool] = None):
        """특정 카메라의 감지 객체 목록 업데이트"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        
        for config in self.camera_configs:
            if str(config.camera_id) == camera_id:
                config.detection_objects = detection_objects
                if detection_alerts:
                    config.detection_alerts = detection_alerts
                # 캐시 초기화 (새로운 객체 목록에 따른)
                english_tokens = tuple(sorted(detection_objects.values()))
                if english_tokens in self.text_features_cache:
                    del self.text_features_cache[english_tokens]
                logger.info(f"Updated detection objects for camera {camera_id}: {detection_objects}")
                if detection_alerts:
                    logger.info(f"Updated detection alerts for camera {camera_id}: {detection_alerts}")
                return True
        return False
    
    def get_available_detection_objects(self) -> Dict[str, str]:
        """사용 가능한 감지 객체 목록 반환"""
        return {
            "서 있는 사람": "a standing person",
            "쓰러진 사람": "a fallen person lying on the ground",
            "앉아 있는 사람": "a sitting person",
            "걷는 사람": "a walking person",
            "뛰는 사람": "a running person",
            "누워 있는 사람": "a lying person",
            "올라가는 사람": "a person climbing up",
            "내려가는 사람": "a person going down",
            "손을 든 사람": "a person with raised hands",
            "가방을 든 사람": "a person carrying a bag",
            "우산을 든 사람": "a person holding an umbrella",
            "안전모를 쓴 사람": "a person wearing a helmet",
            "마스크를 쓴 사람": "a person wearing a mask"
        }
    
    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """웹 스트리밍을 위한 최신 프레임 가져오기"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        
        if camera_id not in self.latest_frames:
            return None
        
        with self.frame_locks[camera_id]:
            frame, timestamp = self.latest_frames[camera_id]
            # 5초 이상 오래된 프레임은 None 반환
            if frame is not None and time.time() - timestamp < 5.0:
                return frame.copy()
        return None
    
    def get_frame_as_jpeg(self, camera_id: str, quality: int = 80) -> Optional[bytes]:
        """프레임을 JPEG 바이트로 변환"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        frame = self.get_latest_frame(camera_id)
        if frame is None:
            return None
        
        # JPEG 인코딩
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        success, buffer = cv2.imencode('.jpg', frame, encode_params)
        
        if success:
            return buffer.tobytes()
        return None
    
    def generate_mjpeg_stream(self, camera_id: str):
        """미 스트리밍 제너레이터"""
        # camera_id를 문자열로 통일
        camera_id = str(camera_id)
        
        while self.running:
            jpeg_bytes = self.get_frame_as_jpeg(camera_id)
            if jpeg_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
            else:
                time.sleep(0.1)  # 프레임이 없으면 잠시 대기
    
    def start_web_mode(self):
        """웹 모드로 시작"""
        self.run(web_mode=True)
    
    def stop(self):
        """강제 종료"""
        self.running = False

# 메인 실행
if __name__ == "__main__":
    # Django 환경 설정
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    # Django 모델 임포트
    from CCTV.models import Camera
    
    try:
        # 데이터베이스에서 Camera 정보 가져오기
        cameras = Camera.objects.all()
        
        if cameras.exists():
            # Django 모델을 사용하여 detector 생성
            detector = MultiCameraObjectDetector.from_django_config(cameras)
            detector.run(web_mode=True)  # 웹 모드
        else:
            logger.error("No cameras found in database")
            
    except Exception as e:
        logger.error(f"Error loading cameras from database: {e}")
        # 예제 설정으로 폴백
        example_configs = [
            CameraConfig(
                camera_id="camera_1",
                name="Front Door",
                rtsp_url="rtsp://admin:Password12!@192.168.0.25:554/stream1",
                detection_objects={
                    "서 있는 사람": "a standing person",
                    "쓰러진 사람": "a fallen person lying on the ground",
                    "앉아 있는 사람": "a sitting person"
                },
                detection_alerts={
                    "서 있는 사람": False,
                    "쓰러진 사람": True,
                    "앉아 있는 사람": False
                },
                max_fps=15,
                is_active=True
            )
        ]
        
        detector = MultiCameraObjectDetector(example_configs)
        detector.run(web_mode=True)  # 웹 모드