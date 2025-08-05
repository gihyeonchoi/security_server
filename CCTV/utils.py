# CCTV/utils.py
import cv2
import threading
import time
import queue
import os
from django.http import StreamingHttpResponse
from django.conf import settings
import json
import numpy as np
from collections import deque
from ultralytics import YOLO
import torch
from PIL import Image
import clip
from datetime import datetime

class CameraStreamer:
    def __init__(self):
        self.cameras = {}
        self.global_lock = threading.Lock()
        self.active_streams = {}
        self.frame_queues = {}
        self.reader_threads = {}
    
    def get_camera_stream(self, rtsp_url):
        with self.global_lock:
            if rtsp_url not in self.cameras:
                self.cameras[rtsp_url] = {
                    'cap': None,
                    'is_connected': False,
                    'last_frame': None,
                    'fps_counter': 0,
                    'last_fps_time': time.time(),
                    'avg_fps': 0,
                    'tracker_count': 0,
                    'lock': threading.Lock(),
                    'stream_count': 0,
                    'reconnect_attempts': 0,
                    'last_reconnect_time': 0
                }
                # 각 카메라별 프레임 큐 생성 (최대 2개 프레임만 보관)
                self.frame_queues[rtsp_url] = queue.Queue(maxsize=2)
            return self.cameras[rtsp_url]
    
    def connect_camera(self, rtsp_url):
        camera_info = self.get_camera_stream(rtsp_url)
        
        with camera_info['lock']:
            # 재연결 시도 제한
            current_time = time.time()
            if camera_info['reconnect_attempts'] >= 3:
                if current_time - camera_info['last_reconnect_time'] < 30:
                    return False
                else:
                    camera_info['reconnect_attempts'] = 0
            
            if camera_info['cap'] is None or not camera_info['is_connected']:
                try:
                    if camera_info['cap']:
                        camera_info['cap'].release()
                        time.sleep(0.1)
                    
                    # OpenCV 설정 최적화
                    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
                    
                    # RTSP 스트림 최적화 설정
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 버퍼 크기 최소화
                    cap.set(cv2.CAP_PROP_FPS, 25)
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))
                    
                    # FFMPEG 옵션 설정
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
                    
                    if cap.isOpened():
                        # 첫 프레임 테스트
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            camera_info['cap'] = cap
                            camera_info['is_connected'] = True
                            camera_info['reconnect_attempts'] = 0
                            
                            # 프레임 읽기 스레드 시작
                            if rtsp_url not in self.reader_threads or not self.reader_threads[rtsp_url].is_alive():
                                reader_thread = threading.Thread(
                                    target=self._frame_reader_thread,
                                    args=(rtsp_url,),
                                    daemon=True
                                )
                                self.reader_threads[rtsp_url] = reader_thread
                                reader_thread.start()
                            
                            return True
                        else:
                            cap.release()
                            camera_info['reconnect_attempts'] += 1
                            camera_info['last_reconnect_time'] = current_time
                            return False
                    else:
                        camera_info['reconnect_attempts'] += 1
                        camera_info['last_reconnect_time'] = current_time
                        return False
                except Exception as e:
                    print(f"Camera connection error: {e}")
                    if 'cap' in locals() and cap:
                        cap.release()
                    camera_info['reconnect_attempts'] += 1
                    camera_info['last_reconnect_time'] = current_time
                    return False
            return camera_info['is_connected']
    
    def _frame_reader_thread(self, rtsp_url):
        """별도 스레드에서 프레임을 지속적으로 읽어서 큐에 저장"""
        camera_info = self.cameras.get(rtsp_url)
        frame_queue = self.frame_queues.get(rtsp_url)
        
        if not camera_info or not frame_queue:
            return
        
        consecutive_failures = 0
        
        while True:
            with camera_info['lock']:
                cap = camera_info['cap']
                if not cap or not camera_info['is_connected']:
                    break
                stream_count = camera_info['stream_count']
            
            if stream_count <= 0:
                time.sleep(0.1)
                continue
            
            try:
                ret, frame = cap.read()
                
                if ret and frame is not None:
                    consecutive_failures = 0
                    
                    # 이전 프레임 제거 (큐가 가득 찬 경우)
                    try:
                        frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    
                    # 새 프레임 추가
                    try:
                        frame_queue.put_nowait(frame)
                    except queue.Full:
                        pass
                    
                    # FPS 계산
                    with camera_info['lock']:
                        camera_info['fps_counter'] += 1
                        current_time = time.time()
                        if current_time - camera_info['last_fps_time'] >= 1.0:
                            camera_info['avg_fps'] = camera_info['fps_counter']
                            camera_info['fps_counter'] = 0
                            camera_info['last_fps_time'] = current_time
                else:
                    consecutive_failures += 1
                    if consecutive_failures > 10:
                        with camera_info['lock']:
                            camera_info['is_connected'] = False
                            if camera_info['cap']:
                                camera_info['cap'].release()
                                camera_info['cap'] = None
                        break
                
                # CPU 부하 감소를 위한 짧은 대기
                time.sleep(0.001)
                
            except Exception as e:
                print(f"Frame reading error: {e}")
                consecutive_failures += 1
                if consecutive_failures > 10:
                    with camera_info['lock']:
                        camera_info['is_connected'] = False
                        if camera_info['cap']:
                            camera_info['cap'].release()
                            camera_info['cap'] = None
                    break
    
    def generate_frames(self, rtsp_url):
        camera_info = self.get_camera_stream(rtsp_url)
        frame_queue = self.frame_queues.get(rtsp_url)
        
        with camera_info['lock']:
            camera_info['stream_count'] += 1
        
        last_frame = None
        error_count = 0
        
        try:
            while True:
                if not self.connect_camera(rtsp_url):
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + 
                           self.get_error_frame("Camera Disconnected") + b'\r\n')
                    time.sleep(2)
                    continue
                
                try:
                    # 큐에서 최신 프레임 가져오기 (타임아웃 설정)
                    frame = frame_queue.get(timeout=0.5)
                    last_frame = frame
                    error_count = 0
                except queue.Empty:
                    error_count += 1
                    if error_count > 10:
                        # 10회 이상 프레임을 못 받으면 연결 문제로 판단
                        with camera_info['lock']:
                            camera_info['is_connected'] = False
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + 
                               self.get_error_frame("No Signal") + b'\r\n')
                        continue
                    elif last_frame is not None:
                        # 마지막 프레임 재사용
                        frame = last_frame
                    else:
                        continue
                
                # JPEG 인코딩 (품질 조정으로 네트워크 부하 감소)
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + f'{len(frame_bytes)}'.encode() + b'\r\n\r\n' + 
                       frame_bytes + b'\r\n')
                
                # 프레임 레이트 제어 (25 FPS)
                time.sleep(0.04)
                
        except GeneratorExit:
            pass
        finally:
            with camera_info['lock']:
                camera_info['stream_count'] -= 1
                if camera_info['stream_count'] <= 0:
                    # 모든 스트림이 종료되면 리소스 정리
                    if camera_info['cap']:
                        camera_info['cap'].release()
                        camera_info['cap'] = None
                    camera_info['is_connected'] = False
                    
                    # 프레임 큐 비우기
                    try:
                        while not frame_queue.empty():
                            frame_queue.get_nowait()
                    except:
                        pass
    
    def get_error_frame(self, message="Camera Error"):
        """에러 메시지가 포함된 프레임 생성"""
        error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 배경색 설정 (어두운 회색)
        error_frame.fill(30)
        
        # 텍스트 크기 계산
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1
        thickness = 2
        text_size = cv2.getTextSize(message, font, font_scale, thickness)[0]
        
        # 텍스트 위치 계산 (중앙)
        text_x = (error_frame.shape[1] - text_size[0]) // 2
        text_y = (error_frame.shape[0] + text_size[1]) // 2
        
        # 텍스트 그리기
        cv2.putText(error_frame, message, (text_x, text_y), 
                   font, font_scale, (0, 0, 255), thickness)
        
        # 타임스탬프 추가
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(error_frame, timestamp, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        _, buffer = cv2.imencode('.jpg', error_frame)
        return buffer.tobytes()
    
    def get_camera_status(self, rtsp_url):
        camera_info = self.get_camera_stream(rtsp_url)
        with camera_info['lock']:
            return {
                'is_connected': camera_info['is_connected'],
                'avg_fps': camera_info['avg_fps'],
                'tracker_count': camera_info['tracker_count'],
                'stream_count': camera_info['stream_count'],
                'reconnect_attempts': camera_info['reconnect_attempts']
            }
    
    def cleanup_camera(self, rtsp_url):
        """카메라 리소스 정리"""
        with self.global_lock:
            if rtsp_url in self.cameras:
                camera_info = self.cameras[rtsp_url]
                with camera_info['lock']:
                    if camera_info['cap']:
                        camera_info['cap'].release()
                        camera_info['cap'] = None
                    camera_info['is_connected'] = False
                
                # 스레드 종료 대기
                if rtsp_url in self.reader_threads:
                    thread = self.reader_threads[rtsp_url]
                    if thread.is_alive():
                        thread.join(timeout=2.0)
                    del self.reader_threads[rtsp_url]
                
                # 큐 정리
                if rtsp_url in self.frame_queues:
                    del self.frame_queues[rtsp_url]
                
                del self.cameras[rtsp_url]

class AIDetectionSystem:
    def __init__(self):
        self.yolo_model = None
        self.clip_model = None
        self.clip_preprocess = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.detection_threads = {}
        self.detection_active = {}
        self.screenshot_dir = os.path.join(settings.MEDIA_ROOT, 'screenshots')
        self.load_models()
        self.ensure_screenshot_dir()
    
    def ensure_screenshot_dir(self):
        """스크린샷 저장 디렉토리 생성"""
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir, exist_ok=True)
    
    def load_models(self):
        """YOLO11 및 CLIP 모델 로드 (디버그 추가)"""
        print("\n🔧 AI 모델 로드 시작...")
        print(f"  - PyTorch 버전: {torch.__version__}")
        print(f"  - CUDA 사용 가능: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"  - CUDA 디바이스: {torch.cuda.get_device_name(0)}")
        
        try:
            # 리눅스/우분투 환경에서 디스플레이 서버 없이 OpenCV 실행 설정
            import platform
            if platform.system() == 'Linux':
                os.environ['DISPLAY'] = ':0'  # X11 디스플레이 설정
                # 헤드리스 환경에서 GUI 백엔드 비활성화
                import matplotlib
                matplotlib.use('Agg')
            
            # YOLO11 모델 로드
            yolo_path = os.path.join(settings.BASE_DIR, 'CCTV', 'yolo11n.pt')
            print(f"  - YOLO 모델 경로: {yolo_path}")
            print(f"  - YOLO 모델 존재: {os.path.exists(yolo_path)}")
            
            if os.path.exists(yolo_path):
                # 헤드리스 환경에서 YOLO 모델 로드 시 verbose=False 설정
                self.yolo_model = YOLO(yolo_path)
                # GPU 사용 불가능한 경우 CPU로 강제 설정
                if not torch.cuda.is_available():
                    self.device = "cpu"
                print(f"✅ YOLO11 모델 로드 완료: {yolo_path} (device: {self.device})")
                
                # YOLO 클래스 정보 출력
                if hasattr(self.yolo_model, 'model') and hasattr(self.yolo_model.model, 'names'):
                    print(f"  - YOLO 클래스 수: {len(self.yolo_model.model.names)}")
                    print(f"  - YOLO 주요 클래스: {list(self.yolo_model.model.names.values())[:10]}...")
            else:
                print(f"❌ YOLO11 모델 파일을 찾을 수 없습니다: {yolo_path}")
            
            # CLIP 모델 로드
            try:
                print(f"\n  - CLIP 모델 로드 중...")
                self.clip_model, self.clip_preprocess = clip.load("ViT-B/32", device=self.device)
                print(f"✅ CLIP 모델 로드 완료 (device: {self.device})")
            except Exception as clip_error:
                # CLIP 모델 로드 실패 시 CPU로 재시도
                print(f"⚠️ CLIP GPU 로드 실패, CPU로 재시도: {clip_error}")
                self.device = "cpu"
                self.clip_model, self.clip_preprocess = clip.load("ViT-B/32", device=self.device)
                print(f"✅ CLIP 모델 CPU 로드 완료")
            
        except Exception as e:
            print(f"❌ AI 모델 로드 실패: {e}")
            import traceback
            traceback.print_exc()
            # 모델 로드 실패 시에도 시스템이 계속 동작하도록 설정
            self.yolo_model = None
            self.clip_model = None
    
    def start_detection_for_camera(self, camera):
        """특정 카메라에 대한 탐지 시작"""
        if camera.id not in self.detection_active:
            self.detection_active[camera.id] = True
            detection_thread = threading.Thread(
                target=self._detection_worker,
                args=(camera,),
                daemon=True
            )
            self.detection_threads[camera.id] = detection_thread
            detection_thread.start()
            print(f"🎯 카메라 '{camera.name}' 탐지 시작")
    
    def stop_detection_for_camera(self, camera_id):
        """특정 카메라에 대한 탐지 중지"""
        if camera_id in self.detection_active:
            self.detection_active[camera_id] = False
            print(f"⏹️ 카메라 ID {camera_id} 탐지 중지")
    
    def _detection_worker(self, camera):
        """카메라별 탐지 워커 스레드 (디버그 로그 추가)"""
        from .models import TargetLabel, DetectionLog
        
        print(f"\n🚀 탐지 워커 시작: 카메라 '{camera.name}' (ID: {camera.id})")
        
        while self.detection_active.get(camera.id, False):
            try:
                # 카메라에서 최신 프레임 가져오기
                camera_info = camera_streamer.get_camera_stream(camera.rtsp_url)
                
                if not camera_info['is_connected']:
                    print(f"⚠️ 카메라 '{camera.name}' 연결되지 않음. 대기 중...")
                    time.sleep(2)
                    continue
                
                # 프레임 큐에서 최신 프레임 가져오기
                frame_queue = camera_streamer.frame_queues.get(camera.rtsp_url)
                if not frame_queue or frame_queue.empty():
                    time.sleep(0.5)
                    continue
                
                try:
                    frame = frame_queue.get_nowait()
                    print(f"\n📹 프레임 획득: 카메라 '{camera.name}' - 크기: {frame.shape}")
                except queue.Empty:
                    time.sleep(0.5)
                    continue
                
                # 타겟 라벨 가져오기
                target_labels = list(camera.target_labels.all())
                if not target_labels:
                    print(f"⚠️ 카메라 '{camera.name}'에 타겟 라벨이 없음")
                    time.sleep(2)
                    continue
                
                print(f"🎯 타겟 라벨 {len(target_labels)}개 로드")
                
                # 객체 탐지 수행
                detections = self._detect_objects(frame, target_labels)
                
                # 탐지 결과 처리
                if detections:
                    print(f"\n✨ 탐지 완료! {len(detections)}개 타겟 발견")
                    for detection in detections:
                        self._process_detection(camera, frame, detection, target_labels)
                else:
                    print(f"💤 탐지된 객체 없음")
                
                # 탐지 간격 (1.5초)
                time.sleep(1.5)
                
            except Exception as e:
                print(f"❌ 탐지 워커 오류 (카메라: {camera.name}): {e}")
                import traceback
                traceback.print_exc()
                time.sleep(2)
        
        print(f"🛑 탐지 워커 종료: 카메라 '{camera.name}'")
    
    def _detect_objects(self, frame, target_labels):
        """프레임에서 객체 탐지 (디버그 로그 추가)"""
        detections = []
        
        if self.yolo_model is None or self.clip_model is None:
            print("⚠️ 디버그: YOLO 또는 CLIP 모델이 로드되지 않음")
            return detections
        
        try:
            print(f"\n🔍 디버그: 객체 탐지 시작")
            print(f"  - 타겟 라벨: {[f'{tl.display_name}({tl.label_name})' for tl in target_labels]}")
            
            # YOLO로 1차 객체 탐지 (바운딩 박스 획득)
            results = self.yolo_model(frame, verbose=False)
            
            if not results or len(results) == 0:
                print("  - YOLO 탐지 결과: 없음")
                return detections
            
            yolo_result = results[0]
            
            # YOLO가 탐지한 각 바운딩 박스를 CLIP으로 분류
            if hasattr(yolo_result, 'boxes') and yolo_result.boxes is not None:
                boxes = yolo_result.boxes.xyxy.cpu().numpy()  # 바운딩 박스 좌표
                confidences = yolo_result.boxes.conf.cpu().numpy() if yolo_result.boxes.conf is not None else []
                classes = yolo_result.boxes.cls.cpu().numpy() if yolo_result.boxes.cls is not None else []
                
                print(f"  - YOLO 탐지 수: {len(boxes)}개")
                
                # YOLO 클래스 이름 출력 (디버그용)
                if len(classes) > 0:
                    class_names = yolo_result.names if hasattr(yolo_result, 'names') else {}
                    detected_classes = [class_names.get(int(cls), f'class_{int(cls)}') for cls in classes]
                    print(f"  - YOLO 탐지 클래스: {detected_classes}")
                    print(f"  - YOLO 신뢰도: {[f'{conf:.2f}' for conf in confidences]}")
                
                # 신뢰도 0.5 이상인 바운딩 박스만 사용
                high_conf_mask = confidences >= 0.5
                valid_boxes = boxes[high_conf_mask]
                valid_confidences = confidences[high_conf_mask]
                
                print(f"  - 신뢰도 0.5 이상: {len(valid_boxes)}개")
                
                if len(valid_boxes) == 0:
                    return detections
                
                # 각 타겟 라벨에 대해 CLIP으로 분류
                for target_label in target_labels:
                    print(f"\n  📍 타겟 라벨 '{target_label.display_name}' ({target_label.label_name}) 검사:")
                    
                    clip_count = 0
                    total_confidence = 0
                    box_details = []
                    
                    # 각 바운딩 박스 영역을 CLIP으로 분류
                    for idx, (box, yolo_conf) in enumerate(zip(valid_boxes, valid_confidences)):
                        x1, y1, x2, y2 = map(int, box)
                        
                        # 바운딩 박스 영역 추출
                        cropped_region = frame[y1:y2, x1:x2]
                        
                        if cropped_region.size > 0:
                            # CLIP으로 해당 영역 분류
                            pil_crop = Image.fromarray(cv2.cvtColor(cropped_region, cv2.COLOR_BGR2RGB))
                            crop_tensor = self.clip_preprocess(pil_crop).unsqueeze(0).to(self.device)
                            
                            # 텍스트 쿼리
                            text_query = f"a photo of {target_label.label_name}"
                            text_token = clip.tokenize([text_query]).to(self.device)
                            
                            with torch.no_grad():
                                crop_features = self.clip_model.encode_image(crop_tensor)
                                text_features = self.clip_model.encode_text(text_token)
                                
                                # 유사도 계산
                                similarity = (crop_features @ text_features.T).cpu().numpy()[0][0]
                                
                                box_details.append({
                                    'box_idx': idx,
                                    'coords': f"({x1},{y1})-({x2},{y2})",
                                    'yolo_conf': f"{yolo_conf:.2f}",
                                    'clip_sim': f"{similarity:.3f}"
                                })
                                
                                # CLIP 임계값 (0.2 이상이면 해당 객체로 판단)
                                if similarity > 0.2:
                                    clip_count += 1
                                    total_confidence += similarity
                                    print(f"     ✅ Box{idx}: CLIP 매칭! (유사도: {similarity:.3f})")
                                else:
                                    print(f"     ❌ Box{idx}: CLIP 미매칭 (유사도: {similarity:.3f})")
                    
                    # 박스별 상세 정보 출력
                    print(f"     박스 상세:")
                    for detail in box_details:
                        print(f"       - Box{detail['box_idx']}: {detail['coords']}, "
                            f"YOLO신뢰도={detail['yolo_conf']}, CLIP유사도={detail['clip_sim']}")
                    
                    # 해당 라벨로 분류된 객체가 있다면 탐지 결과에 추가
                    if clip_count > 0:
                        avg_confidence = total_confidence / clip_count
                        
                        detections.append({
                            'label': target_label,
                            'confidence': float(avg_confidence),
                            'count': clip_count,  # CLIP으로 정확히 센 개수
                            'has_alert': target_label.has_alert
                        })
                        
                        print(f"     🎯 최종 탐지: {clip_count}개 (평균 신뢰도: {avg_confidence:.3f})")
                        print(f"     🚨 알림 설정: {'활성화' if target_label.has_alert else '비활성화'}")
                    else:
                        print(f"     ⭕ 탐지되지 않음")
            
            print(f"\n📊 전체 탐지 결과: {len(detections)}개 타겟 발견")
            for det in detections:
                print(f"  - {det['label'].display_name}: {det['count']}개 (신뢰도: {det['confidence']:.3f})")
        
        except Exception as e:
            print(f"❌ 객체 탐지 오류: {e}")
            import traceback
            traceback.print_exc()
        
        return detections

    
    def _process_detection(self, camera, frame, detection, target_labels):
        """탐지 결과 처리 (로그 저장, 알림, 스크린샷) - 디버그 추가"""
        from .models import DetectionLog
        
        try:
            print(f"\n📝 탐지 결과 처리:")
            print(f"  - 카메라: {camera.name}")
            print(f"  - 객체: {detection['label'].display_name}")
            print(f"  - 개수: {detection['count']}")
            print(f"  - 신뢰도: {detection['confidence']:.3f}")
            print(f"  - 알림 여부: {'예' if detection['has_alert'] else '아니오'}")
            
            # 스크린샷 저장 (has_alert인 경우)
            screenshot_path = None
            if detection['has_alert']:
                screenshot_path = self._save_screenshot(camera, frame, detection)
                if screenshot_path:
                    print(f"  - 📸 스크린샷 저장: {screenshot_path}")
                else:
                    print(f"  - ⚠️ 스크린샷 저장 실패")
            
            # 탐지 로그 저장
            log = DetectionLog.objects.create(
                camera=camera,
                camera_name=camera.name,
                camera_location=camera.location,
                detected_object=detection['label'].display_name,
                object_count=detection['count'],
                confidence=detection['confidence'],
                has_alert=detection['has_alert'],
                screenshot_path=screenshot_path
            )
            
            print(f"  - 💾 DB 로그 저장 완료 (ID: {log.id})")
            
            # 실시간 알림 전송 (has_alert인 경우)
            if detection['has_alert']:
                self._send_realtime_alert(log)
                print(f"  - 📢 실시간 알림 전송 완료")
            
            print(f"🎯 탐지 로그: {log}")
            
        except Exception as e:
            print(f"❌ 탐지 결과 처리 오류: {e}")
            import traceback
            traceback.print_exc()
    

    def _save_screenshot(self, camera, frame, detection):
        """스크린샷 저장"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{camera.id}_{timestamp}_{detection['label'].display_name}.jpg"
            filepath = os.path.join(self.screenshot_dir, filename)
            
            cv2.imwrite(filepath, frame)
            return filepath
            
        except Exception as e:
            print(f"❌ 스크린샷 저장 오류: {e}")
            return None
    
    def _send_realtime_alert(self, log):
        """실시간 알림 전송 (SSE 큐에 추가)"""
        # SSE 알림 큐에 추가 (추후 구현)
        alert_data = {
            'type': 'detection_alert',
            'camera_name': log.camera_name,
            'camera_location': log.camera_location,
            'detected_object': log.detected_object,
            'object_count': log.object_count,
            'detected_at': log.detected_at.isoformat(),
            'has_screenshot': bool(log.screenshot_path)
        }
        
        # 글로벌 알림 큐에 추가 (추후 SSE에서 사용)
        if not hasattr(self, 'alert_queue'):
            self.alert_queue = queue.Queue()
        
        try:
            self.alert_queue.put_nowait(alert_data)
        except queue.Full:
            pass  # 큐가 가득 찬 경우 무시
    
    def start_all_detections(self):
        """모든 활성 카메라에 대한 탐지 시작"""
        from .models import Camera
        
        cameras = Camera.objects.all()
        for camera in cameras:
            if camera.target_labels.exists():  # 타겟 라벨이 있는 카메라만
                self.start_detection_for_camera(camera)
    
    def stop_all_detections(self):
        """모든 탐지 중지"""
        for camera_id in list(self.detection_active.keys()):
            self.stop_detection_for_camera(camera_id)

# 싱글톤 인스턴스
camera_streamer = CameraStreamer()
ai_detection_system = AIDetectionSystem()