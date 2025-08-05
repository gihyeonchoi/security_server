import clip
import torch
from ultralytics import YOLO
import cv2
from PIL import Image
import numpy as np
import datetime
import os
from threading import Thread, Lock, Event
from queue import Queue
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
import logging
from concurrent.futures import ThreadPoolExecutor
import gc

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
    detection_alerts: Dict[str, bool] = None
    max_fps: int = 15
    is_active: bool = True
    resize_width: int = 640  # 처리할 프레임 크기
    skip_frames: int = 2  # 건너뛸 프레임 수
    detection_interval: float = 0.5  # 감지 간격 (초)

class SimpleTracker:
    """간단한 객체 추적기"""
    def __init__(self, track_id: int, initial_detection: Detection):
        self.id = track_id
        self.bbox = initial_detection.bbox
        self.label = initial_detection.label
        self.last_update = initial_detection.timestamp
        self.missed_frames = 0
        
    def update(self, detection: Detection):
        """추적기 업데이트"""
        self.bbox = detection.bbox
        self.label = detection.label
        self.last_update = detection.timestamp
        self.missed_frames = 0
    
    def mark_missed(self):
        """놓친 프레임 처리"""
        self.missed_frames += 1
    
    def should_remove(self, current_time: float) -> bool:
        """제거 여부 판단"""
        return self.missed_frames > 10 or current_time - self.last_update > 3.0

class MultiCameraObjectDetector:
    """CPU 최적화된 다중 카메라 객체 감지 시스템"""
    def __init__(self, camera_configs: List[CameraConfig] = None):
        # 장치 설정
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        
        # CPU 최적화 설정
        if self.device == "cpu":
            torch.set_num_threads(4)  # CPU 스레드 제한
            os.environ['OMP_NUM_THREADS'] = '4'
            os.environ['MKL_NUM_THREADS'] = '4'
        
        # 모델 로드 (지연 로딩)
        self._clip_model = None
        self._preprocess = None
        self._yolo = None
        
        # 카메라 관리
        self.camera_configs = []
        self.cameras = {}
        self.camera_threads = {}
        self.trackers = {}
        self.next_tracker_ids = {}
        self.tracker_locks = {}
        
        # 프레임 버퍼
        self.latest_frames = {}
        self.frame_locks = {}
        self.frame_times = {}
        self.last_detection_time = {}  # 마지막 감지 시간
        
        # CLIP 특징 캐시
        self.text_features_cache = {}
        
        # 스크린샷 설정
        self.screenshot_dir = "object_detection_screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.last_detection_screenshot = {}
        
        # 실행 제어
        self.running = False
        self.web_mode = False
        self.detection_events = {}  # 감지 이벤트 제어
        
        # 처리 스레드 풀 (제한된 수)
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # 초기 카메라 추가
        if camera_configs:
            for config in camera_configs:
                self.add_camera(config)
    
    @property
    def clip_model(self):
        """CLIP 모델 지연 로딩"""
        if self._clip_model is None:
            logger.info("Loading CLIP model...")
            self._clip_model, self._preprocess = clip.load("ViT-B/32", device=self.device)
            # 평가 모드로 설정
            self._clip_model.eval()
            logger.info("CLIP model loaded")
        return self._clip_model
    
    @property
    def preprocess(self):
        """CLIP 전처리 함수"""
        if self._preprocess is None:
            self.clip_model  # 모델 로드 트리거
        return self._preprocess
    
    @property
    def yolo(self):
        """YOLO 모델 지연 로딩"""
        if self._yolo is None:
            logger.info("Loading YOLO model...")
            self._yolo = YOLO("yolo11n.pt", verbose=False)
            # CPU 최적화
            if self.device == "cpu":
                self._yolo.overrides['batch'] = 1  # 배치 크기 제한
                self._yolo.overrides['imgsz'] = 640  # 이미지 크기 고정
            logger.info("YOLO model loaded")
        return self._yolo
    
    def _prepare_clip_features(self, detection_objects: Dict[str, str]) -> Tuple[torch.Tensor, List[str]]:
        """CLIP 특징 계산 (캐싱)"""
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
    
    def add_camera(self, config: CameraConfig) -> bool:
        """카메라 추가"""
        camera_id = str(config.camera_id)
        
        if camera_id in self.cameras:
            logger.warning(f"Camera {camera_id} already exists")
            return False
        
        # RTSP 연결 (최적화된 설정)
        cap = cv2.VideoCapture(config.rtsp_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, config.max_fps)
        
        # 추가 최적화 설정
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        
        # 연결 확인
        if not cap.isOpened():
            logger.error(f"Failed to open camera {camera_id}")
            cap.release()
            return False
        
        # 첫 프레임 테스트
        ret, test_frame = cap.read()
        if not ret or test_frame is None:
            logger.error(f"Failed to read test frame from camera {camera_id}")
            cap.release()
            return False
        
        # camera_id를 문자열로 통일
        config.camera_id = camera_id
        
        # 초기화
        self.cameras[camera_id] = cap
        self.camera_configs.append(config)
        self.trackers[camera_id] = {}
        self.next_tracker_ids[camera_id] = 0
        self.tracker_locks[camera_id] = Lock()
        self.latest_frames[camera_id] = (None, 0)
        self.frame_locks[camera_id] = Lock()
        self.frame_times[camera_id] = []
        self.last_detection_screenshot[camera_id] = {}
        self.last_detection_time[camera_id] = 0
        self.detection_events[camera_id] = Event()
        
        logger.info(f"Camera {camera_id} added successfully")
        return True
    
    def _calculate_iou(self, box1: Tuple, box2: Tuple) -> float:
        """IOU 계산 (최적화)"""
        # 벡터화된 계산
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        return intersection / (area1 + area2 - intersection)
    
    def _process_detection(self, camera_id: str, frame: np.ndarray, config: CameraConfig):
        """감지 처리 (별도 스레드에서 실행)"""
        try:
            current_time = time.time()
            
            # 프레임 리사이즈 (속도 향상)
            height, width = frame.shape[:2]
            if width > config.resize_width:
                scale = config.resize_width / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                resized_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
            else:
                resized_frame = frame
                scale = 1.0
            
            # YOLO 감지 (리사이즈된 프레임에서)
            results = self.yolo(resized_frame, verbose=False, conf=0.5)
            boxes = results[0].boxes
            
            # 사람 객체만 필터링
            detections = []
            if boxes is not None:
                for box in boxes:
                    if int(box.cls[0]) == 0:  # person class
                        # 좌표를 원본 크기로 변환
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        bbox = (
                            int(x1 / scale),
                            int(y1 / scale),
                            int(x2 / scale),
                            int(y2 / scale)
                        )
                        
                        # CLIP 분류 (선택적 - CPU 부하 고려)
                        if len(detections) < 5:  # 최대 5개만 CLIP 처리
                            crop = frame[bbox[1]:bbox[3], bbox[0]:bbox[2]]
                            if crop.size > 0:
                                label = self._classify_with_clip(crop, config.detection_objects)
                                detections.append(Detection(
                                    bbox=bbox,
                                    confidence=float(box.conf[0]),
                                    label=label,
                                    timestamp=current_time,
                                    camera_id=camera_id
                                ))
            
            # 추적기 업데이트
            self._update_trackers(camera_id, detections, current_time)
            
        except Exception as e:
            logger.error(f"Error in detection processing for camera {camera_id}: {e}")
    
    def _classify_with_clip(self, crop: np.ndarray, detection_objects: Dict[str, str]) -> str:
        """CLIP으로 객체 분류 (최적화)"""
        try:
            # 크롭 크기 제한
            max_size = 224
            h, w = crop.shape[:2]
            if h > max_size or w > max_size:
                scale = max_size / max(h, w)
                crop = cv2.resize(crop, (int(w * scale), int(h * scale)))
            
            text_features, korean_labels = self._prepare_clip_features(detection_objects)
            
            # 이미지 전처리
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(crop_rgb)
            image_input = self.preprocess(pil_img).unsqueeze(0).to(self.device)
            
            # 유사도 계산
            with torch.no_grad():
                image_features = self.clip_model.encode_image(image_input)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                similarities = (image_features @ text_features.T).squeeze()
            
            # 가장 유사한 라벨 반환
            best_idx = torch.argmax(similarities).item()
            return korean_labels[best_idx]
            
        except Exception as e:
            logger.error(f"Error in CLIP classification: {e}")
            return "사람"  # 기본값
    
    def _update_trackers(self, camera_id: str, detections: List[Detection], current_time: float):
        """추적기 업데이트 (최적화)"""
        with self.tracker_locks[camera_id]:
            trackers = self.trackers[camera_id]
            
            if not detections and not trackers:
                return
            
            # 간단한 매칭 (거리 기반)
            matched_trackers = set()
            matched_detections = set()
            
            for tracker_id, tracker in list(trackers.items()):
                min_distance = float('inf')
                best_detection_idx = -1
                
                for idx, detection in enumerate(detections):
                    if idx not in matched_detections:
                        # 중심점 거리 계산 (IOU보다 빠름)
                        t_cx = (tracker.bbox[0] + tracker.bbox[2]) / 2
                        t_cy = (tracker.bbox[1] + tracker.bbox[3]) / 2
                        d_cx = (detection.bbox[0] + detection.bbox[2]) / 2
                        d_cy = (detection.bbox[1] + detection.bbox[3]) / 2
                        
                        distance = ((t_cx - d_cx) ** 2 + (t_cy - d_cy) ** 2) ** 0.5
                        
                        if distance < min_distance and distance < 100:  # 픽셀 거리 임계값
                            min_distance = distance
                            best_detection_idx = idx
                
                if best_detection_idx >= 0:
                    tracker.update(detections[best_detection_idx])
                    matched_trackers.add(tracker_id)
                    matched_detections.add(best_detection_idx)
                else:
                    tracker.mark_missed()
            
            # 새로운 감지 추가
            for idx, detection in enumerate(detections):
                if idx not in matched_detections:
                    new_id = self.next_tracker_ids[camera_id]
                    trackers[new_id] = SimpleTracker(new_id, detection)
                    self.next_tracker_ids[camera_id] += 1
            
            # 오래된 추적기 제거
            for tracker_id in list(trackers.keys()):
                if trackers[tracker_id].should_remove(current_time):
                    del trackers[tracker_id]
    
    def _draw_detections(self, frame: np.ndarray, camera_id: str, config: CameraConfig) -> np.ndarray:
        """감지 결과 그리기 (최적화)"""
        display_frame = frame
        current_time = time.time()
        
        # 추적기가 있을 때만 복사
        if self.trackers[camera_id]:
            display_frame = frame.copy()
            
            with self.tracker_locks[camera_id]:
                for tracker_id, tracker in self.trackers[camera_id].items():
                    bbox = tracker.bbox
                    label = tracker.label
                    
                    # 색상 설정
                    if config.detection_alerts and label in config.detection_alerts:
                        has_alert = config.detection_alerts[label]
                        color = (0, 0, 255) if has_alert else (0, 255, 0)
                    else:
                        color = (128, 128, 128)
                    
                    # 박스 그리기
                    cv2.rectangle(display_frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
                    
                    # 텍스트
                    text = f"{label} #{tracker_id}"
                    cv2.putText(display_frame, text, (bbox[0], bbox[1] - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                    
                    # 경고 객체 스크린샷 (별도 스레드에서)
                    if (config.detection_alerts and 
                        label in config.detection_alerts and 
                        config.detection_alerts[label]):
                        
                        last_time = self.last_detection_screenshot[camera_id].get(tracker_id, 0)
                        if current_time - last_time > 10.0:  # 10초 간격
                            self.last_detection_screenshot[camera_id][tracker_id] = current_time
                            # 스크린샷 저장을 별도 스레드로
                            self.executor.submit(self._save_screenshot, camera_id, tracker_id, label, frame)
        
        # 카메라 정보
        cv2.putText(display_frame, f"Camera: {config.name}", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        # FPS 표시
        if camera_id in self.frame_times and len(self.frame_times[camera_id]) > 5:
            avg_time = sum(self.frame_times[camera_id][-10:]) / min(10, len(self.frame_times[camera_id]))
            fps = 1.0 / avg_time if avg_time > 0 else 0
            cv2.putText(display_frame, f"FPS: {fps:.1f}", (10, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        return display_frame
    
    def _save_screenshot(self, camera_id: str, tracker_id: int, label: str, frame: np.ndarray):
        """스크린샷 저장 (별도 스레드)"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_label = label.replace(" ", "_").replace("/", "_")
            filename = f"{self.screenshot_dir}/ALERT_{safe_label}_{camera_id}_{tracker_id}_{timestamp}.jpg"
            cv2.imwrite(filename, frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            logger.info(f"Alert screenshot saved: {filename}")
        except Exception as e:
            logger.error(f"Error saving screenshot: {e}")
    
    def _camera_thread(self, config: CameraConfig):
        """카메라별 처리 스레드 (최적화)"""
        camera_id = str(config.camera_id)
        cap = self.cameras[camera_id]
        
        frame_count = 0
        
        while self.running:
            try:
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Failed to read from camera {camera_id}")
                    time.sleep(1)
                    continue
                
                current_time = time.time()
                
                # 프레임 건너뛰기
                if frame_count % (config.skip_frames + 1) != 0:
                    frame_count += 1
                    continue
                
                # 감지 처리 (간격 제한)
                if current_time - self.last_detection_time[camera_id] >= config.detection_interval:
                    self.last_detection_time[camera_id] = current_time
                    # 별도 스레드에서 감지 실행
                    self.executor.submit(self._process_detection, camera_id, frame, config)
                
                # 시각화 (항상)
                display_frame = self._draw_detections(frame, camera_id, config)
                
                # 프레임 저장
                with self.frame_locks[camera_id]:
                    self.latest_frames[camera_id] = (display_frame, current_time)
                
                # 성능 모니터링
                if frame_count % 30 == 0:  # 30프레임마다
                    frame_time = time.time() - current_time
                    if len(self.frame_times[camera_id]) > 30:
                        self.frame_times[camera_id].pop(0)
                    self.frame_times[camera_id].append(frame_time)
                
                frame_count += 1
                
                # CPU 쉬는 시간
                time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in camera thread {camera_id}: {e}")
                time.sleep(1)
    
    def run(self, web_mode=False):
        """메인 실행"""
        if not self.camera_configs:
            logger.error("No camera configurations provided")
            return
            
        self.web_mode = web_mode
        self.running = True
        
        # 모델 사전 로드 (첫 프레임 지연 방지)
        logger.info("Preloading models...")
        _ = self.yolo
        _ = self.clip_model
        
        # 카메라 스레드 시작
        threads = []
        for config in self.camera_configs:
            if config.is_active and str(config.camera_id) in self.cameras:
                thread = Thread(target=self._camera_thread, args=(config,))
                thread.daemon = True
                thread.start()
                threads.append(thread)
                self.camera_threads[str(config.camera_id)] = thread
        
        logger.info(f"Started {len(threads)} camera threads")
        
        # 주기적 가비지 컬렉션
        gc_thread = Thread(target=self._periodic_gc)
        gc_thread.daemon = True
        gc_thread.start()
        
        try:
            while self.running:
                if not web_mode:
                    # 데스크톱 모드
                    for camera_id in self.cameras:
                        with self.frame_locks[camera_id]:
                            frame, _ = self.latest_frames[camera_id]
                            if frame is not None:
                                resized = cv2.resize(frame, (640, 480))
                                cv2.imshow(f'Camera {camera_id}', resized)
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                else:
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()
    
    def _periodic_gc(self):
        """주기적 가비지 컬렉션"""
        while self.running:
            time.sleep(30)  # 30초마다
            gc.collect()
            if self.device == "cuda":
                torch.cuda.empty_cache()
    
    def cleanup(self):
        """리소스 정리"""
        logger.info("Cleaning up resources...")
        self.running = False
        
        # 스레드 풀 종료
        self.executor.shutdown(wait=True)
        
        # 카메라 해제
        for camera_id, cap in self.cameras.items():
            cap.release()
            logger.info(f"Camera {camera_id} released")
        
        # 메모리 정리
        self.trackers.clear()
        self.latest_frames.clear()
        self.text_features_cache.clear()
        
        if not self.web_mode:
            cv2.destroyAllWindows()
        
        # 가비지 컬렉션
        gc.collect()
        
        logger.info("Cleanup completed")
    
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
                    1.0 / (sum(self.frame_times[camera_id][-10:]) / min(10, len(self.frame_times[camera_id])))
                    if camera_id in self.frame_times and len(self.frame_times[camera_id]) > 0
                    else 0
                )
            }
        return status
    
    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """웹 스트리밍을 위한 최신 프레임 가져오기"""
        camera_id = str(camera_id)
        
        if camera_id not in self.latest_frames:
            return None
        
        with self.frame_locks[camera_id]:
            frame, timestamp = self.latest_frames[camera_id]
            if frame is not None and time.time() - timestamp < 5.0:
                return frame
        return None
    
    def get_frame_as_jpeg(self, camera_id: str, quality: int = 90) -> Optional[bytes]:
        """프레임을 JPEG 바이트로 변환 (품질 낮춤)"""
        camera_id = str(camera_id)
        frame = self.get_latest_frame(camera_id)
        if frame is None:
            return None
        
        # 크기 제한
        # h, w = frame.shape[:2]
        # if w > 800:
        #     scale = 800 / w
        #     frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        success, buffer = cv2.imencode('.jpg', frame, encode_params)
        
        if success:
            return buffer.tobytes()
        return None
    
    def generate_mjpeg_stream(self, camera_id: str):
        """MJPEG 스트리밍 제너레이터"""
        camera_id = str(camera_id)
        
        while self.running:
            jpeg_bytes = self.get_frame_as_jpeg(camera_id)
            if jpeg_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
            time.sleep(0.05)  # 20 FPS 제한
    
    @classmethod
    def from_django_config(cls, django_camera_configs):
        """Django 모델에서 설정 로드"""
        configs = []
        for camera in django_camera_configs:
            detection_objects = {}
            detection_alerts = {}
            
            for target in camera.target_labels.all():
                detection_objects[target.display_name] = target.label_name
                detection_alerts[target.display_name] = target.has_alert
            
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
                camera_id=str(camera.id),
                name=camera.name,
                rtsp_url=camera.rtsp_url,
                detection_objects=detection_objects,
                detection_alerts=detection_alerts,
                max_fps=15,
                is_active=True,
                resize_width=640,  # 처리 크기
                skip_frames=1,  # 3프레임 중 1프레임만 처리
                detection_interval=0.5  # 0.5초마다 감지
            )
            configs.append(config)
        
        detector = cls([])
        for config in configs:
            success = detector.add_camera(config)
            if not success:
                logger.warning(f"Failed to add camera {config.camera_id} ({config.name})")
        
        return detector


# Django 실행 코드
if __name__ == "__main__":
    import os
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    
    from CCTV.models import Camera
    
    try:
        cameras = Camera.objects.all()
        
        if cameras.exists():
            detector = MultiCameraObjectDetector.from_django_config(cameras)
            detector.run(web_mode=True)
        else:
            logger.error("No cameras found in database")
            test_config = CameraConfig(
                camera_id="test_camera",
                name="Test Camera",
                rtsp_url="rtsp://admin:password@192.168.0.100:554/stream1",
                detection_objects={
                    "서 있는 사람": "a standing person",
                    "쓰러진 사람": "a fallen person lying on the ground"
                },
                detection_alerts={
                    "서 있는 사람": False,
                    "쓰러진 사람": True
                },
                resize_width=640,
                skip_frames=2,
                detection_interval=0.5
            )
            detector = MultiCameraObjectDetector([test_config])
            detector.run(web_mode=True)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()