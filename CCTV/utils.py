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
from PIL import Image, ImageDraw, ImageFont
import clip
import threading
from datetime import datetime

# 전역 알림 큐 (모든 인스턴스가 공유)
GLOBAL_ALERT_QUEUE = queue.Queue(maxsize=100)
ALERT_LISTENERS = []  # SSE 리스너들을 저장

class CameraStreamer:
    def __init__(self):
        self.cameras = {}
        self.global_lock = threading.Lock()
        self.active_streams = {}
        self.frame_queues = {}
        self.reader_threads = {}
        self.background_streaming = {}  # 백그라운드 스트리밍 상태 추적
    
    def get_camera_stream(self, rtsp_url):
        # print(f"🔐 global_lock 획득 시도: {rtsp_url}")
        
        # 락 획득 시도 (타임아웃 5초)
        lock_acquired = self.global_lock.acquire(timeout=5.0)
        if not lock_acquired:
            # print(f"❌ global_lock 획득 실패 (타임아웃): {rtsp_url}")
            pass
            # 임시로 기본 카메라 정보 반환
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
                self.frame_queues[rtsp_url] = queue.Queue(maxsize=5)
            return self.cameras[rtsp_url]
        
        try:
            # print(f"✅ global_lock 획득 성공: {rtsp_url}")
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
                # 각 카메라별 프레임 큐 생성 (백그라운드 모드를 위해 약간 더 큰 큐)
                self.frame_queues[rtsp_url] = queue.Queue(maxsize=5)
            return self.cameras[rtsp_url]
        finally:
            self.global_lock.release()
            # print(f"🔓 global_lock 해제: {rtsp_url}")
    
    def connect_camera(self, rtsp_url):
        """카메라 연결 - 버퍼링 최소화 버전"""
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
                    
                    # GStreamer 백엔드 사용 (Linux/Windows with GStreamer)
                    # 또는 FFMPEG 백엔드 사용
                    backend = cv2.CAP_FFMPEG  # 또는 cv2.CAP_GSTREAMER
                    
                    # RTSP URL에 파라미터 추가 (낮은 지연시간)
                    # TCP 사용으로 패킷 손실 방지
                    rtsp_url_low_latency = rtsp_url
                    if '?' not in rtsp_url:
                        rtsp_url_low_latency = f"{rtsp_url}?tcp"
                    
                    cap = cv2.VideoCapture(rtsp_url_low_latency, backend)
                    
                    # 버퍼 크기를 1로 설정 (최소 버퍼)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    
                    # 추가 최적화 설정
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))
                    cap.set(cv2.CAP_PROP_FPS, 25)
                    
                    # FFMPEG 옵션 설정 - 타임아웃 단축
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)
                    
                    if cap.isOpened():
                        # 버퍼 비우기 - 최신 프레임까지 스킵
                        print(f"🔄 버퍼 비우기 시작: {rtsp_url}")
                        flush_start = time.time()
                        frames_flushed = 0
                        
                        # 최대 2초 동안 버퍼 비우기
                        while time.time() - flush_start < 2.0:
                            ret = cap.grab()  # grab()은 read()보다 빠름
                            if not ret:
                                break
                            frames_flushed += 1
                            
                            # 30프레임마다 실제 읽기 테스트
                            if frames_flushed % 30 == 0:
                                ret, test_frame = cap.retrieve()
                                if not ret or test_frame is None:
                                    break
                        
                        print(f"✅ 버퍼 비우기 완료: {frames_flushed}개 프레임 스킵")
                        
                        # 최신 프레임 테스트
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            camera_info['cap'] = cap
                            camera_info['is_connected'] = True
                            camera_info['reconnect_attempts'] = 0
                            
                            # 프레임 읽기 스레드 시작
                            if rtsp_url not in self.reader_threads or not self.reader_threads[rtsp_url].is_alive():
                                reader_thread = threading.Thread(
                                    target=self._frame_reader_thread_optimized,  # 최적화된 버전 사용
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
    
    def _frame_reader_thread_optimized(self, rtsp_url):
        """프레임 읽기 스레드 - 큐 관리 개선"""
        camera_info = self.cameras.get(rtsp_url)
        frame_queue = self.frame_queues.get(rtsp_url)
        
        if not camera_info or not frame_queue:
            return
        
        consecutive_failures = 0
        last_frame_time = time.time()
        frame_skip_counter = 0
        
        while True:
            with camera_info['lock']:
                cap = camera_info['cap']
                if not cap or not camera_info['is_connected']:
                    break
                stream_count = camera_info['stream_count']
            
            # 아무도 보고 있지 않으면 프레임 읽기 중단
            is_background = self.background_streaming.get(rtsp_url, False)
            if stream_count <= 0 and not is_background:
                # 큐 비우기
                while not frame_queue.empty():
                    try:
                        frame_queue.get_nowait()
                    except:
                        break
                time.sleep(0.5)
                continue
            
            try:
                current_time = time.time()
                
                # 프레임 읽기
                ret = cap.grab()
                
                if ret:
                    # 최신 프레임만 유지 (큐 크기 체크)
                    if frame_queue.qsize() >= 3:
                        # 큐가 3개 이상이면 하나 빼고 새로 넣기
                        try:
                            old_frame = frame_queue.get_nowait()
                            if isinstance(old_frame, dict):
                                # 로그 줄이기 (10번에 1번만)
                                if frame_skip_counter % 10 == 0:
                                    print(f"🔄 큐 정리 중 (크기: {frame_queue.qsize()})")
                        except queue.Empty:
                            pass
                    
                    ret, frame = cap.retrieve()
                    
                    if ret and frame is not None:
                        consecutive_failures = 0
                        frame_skip_counter += 1
                        last_frame_time = current_time
                        
                        # 타임스탬프 추가 (선택적)
                        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        
                        # 화면에 타임스탬프 표시 (디버깅용, 필요시 주석 처리)
                        # cv2.putText(frame, timestamp_str, (10, 30), 
                        #            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        
                        frame_data = {
                            'frame': frame,
                            'timestamp': current_time,
                            'timestamp_str': timestamp_str
                        }
                        
                        # 새 프레임 추가
                        try:
                            frame_queue.put_nowait(frame_data)
                        except queue.Full:
                            # 큐가 가득 차면 가장 오래된 것 제거 후 추가
                            try:
                                frame_queue.get_nowait()
                                frame_queue.put_nowait(frame_data)
                            except:
                                pass
                        
                        # FPS 계산
                        with camera_info['lock']:
                            camera_info['fps_counter'] += 1
                            if current_time - camera_info['last_fps_time'] >= 1.0:
                                camera_info['avg_fps'] = camera_info['fps_counter']
                                camera_info['fps_counter'] = 0
                                camera_info['last_fps_time'] = current_time
                
                # 적절한 대기 시간
                # time.sleep(0.04)  # 25 FPS
                
            except Exception as e:
                print(f"Frame reading error: {e}")
                consecutive_failures += 1
                if consecutive_failures > 10:
                    break

    def flush_camera_buffer(self, rtsp_url):
        """수동으로 카메라 버퍼 비우기. 자동으로 사용하지는 않음"""
        camera_info = self.cameras.get(rtsp_url)
        if not camera_info:
            return False
        
        with camera_info['lock']:
            cap = camera_info['cap']
            if not cap:
                return False
            
            print(f"🔄 버퍼 플러시 시작: {rtsp_url}")
            frames_flushed = 0
            flush_start = time.time()
            
            # 최대 1초 동안 버퍼 비우기
            while time.time() - flush_start < 1.0:
                ret = cap.grab()
                if not ret:
                    break
                frames_flushed += 1
                
                if frames_flushed >= 30:  # 최대 30프레임
                    break
            
            print(f"✅ 버퍼 플러시 완료: {frames_flushed}개 프레임 제거")
            return True
        
    def generate_frames(self, rtsp_url):
        """영상 스트리밍 - dict 형식 프레임 처리"""
        try:
            camera_info = self.get_camera_stream(rtsp_url)
            frame_queue = self.frame_queues.get(rtsp_url)
            
            with camera_info['lock']:
                camera_info['stream_count'] += 1
                
        except Exception as e:
            print(f"❌ generate_frames 초기화 오류: {e}")
            return
        
        last_frame = None
        error_count = 0
        
        try:
            while True:
                connection_result = self.connect_camera(rtsp_url)
                
                if not connection_result:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + 
                           self.get_error_frame("Camera Disconnected") + b'\r\n')
                    time.sleep(2)
                    continue
                
                try:
                    # 큐에서 프레임 가져오기
                    frame_data = frame_queue.get(timeout=0.5)
                    
                    # dict 형식인지 확인하고 프레임 추출
                    if isinstance(frame_data, dict):
                        frame = frame_data.get('frame')
                        timestamp_str = frame_data.get('timestamp_str', '')
                        
                        # 디버깅용 로그 (필요시 주석 해제)
                        # print(f"📺 스트리밍 프레임: {timestamp_str}")
                    else:
                        # 구버전 호환성 (프레임만 있는 경우)
                        frame = frame_data
                    
                    if frame is None:
                        continue
                    
                    last_frame = frame
                    error_count = 0
                    
                except queue.Empty:
                    error_count += 1
                    if error_count > 10:
                        with camera_info['lock']:
                            camera_info['is_connected'] = False
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + 
                               self.get_error_frame("No Signal") + b'\r\n')
                        continue
                    elif last_frame is not None:
                        frame = last_frame
                    else:
                        continue
                
                # JPEG 인코딩
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                frame_bytes = buffer.tobytes()
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + f'{len(frame_bytes)}'.encode() + b'\r\n\r\n' + 
                       frame_bytes + b'\r\n')
                
                # time.sleep(0.04)  # 25 FPS
                
        except GeneratorExit:
            pass
        finally:
            with camera_info['lock']:
                camera_info['stream_count'] -= 1
                is_background = self.background_streaming.get(rtsp_url, False)
                if camera_info['stream_count'] <= 0 and not is_background:
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
    
    def start_background_streaming(self, rtsp_url):
        """백그라운드 연속 스트리밍 시작"""
        print(f"🔄 백그라운드 스트리밍 시작 시도: {rtsp_url}")
        
        # 락 타임아웃으로 데드락 방지
        if self.global_lock.acquire(timeout=3.0):
            try:
                self.background_streaming[rtsp_url] = True
                print(f"🔄 백그라운드 스트리밍 플래그 설정: {rtsp_url}")
            finally:
                self.global_lock.release()
        else:
            print(f"⚠️ 백그라운드 스트리밍 락 타임아웃: {rtsp_url}")
            return False
            
        # 카메라 연결 확인 및 스트림 시작 (락 외부에서)
        if self.connect_camera(rtsp_url):
            print(f"✅ 백그라운드 스트리밍 활성화: {rtsp_url}")
            return True
        else:
            print(f"❌ 백그라운드 스트리밍 실패 (연결 불가): {rtsp_url}")
            return False
    
    def stop_background_streaming(self, rtsp_url):
        """백그라운드 연속 스트리밍 중지"""
        with self.global_lock:
            if rtsp_url in self.background_streaming:
                self.background_streaming[rtsp_url] = False
                del self.background_streaming[rtsp_url]
                print(f"⏹️ 백그라운드 스트리밍 중지: {rtsp_url}")
    
    def is_background_streaming(self, rtsp_url):
        """백그라운드 스트리밍 상태 확인"""
        return self.background_streaming.get(rtsp_url, False)
    
    def start_all_background_streaming(self):
        """모든 카메라의 백그라운드 스트리밍 시작"""
        from .models import Camera
        cameras = Camera.objects.all()
        
        for camera in cameras:
            try:
                self.start_background_streaming(camera.rtsp_url)
            except Exception as e:
                print(f"❌ 카메라 '{camera.name}' 백그라운드 스트리밍 실패: {e}")
    
    def stop_all_background_streaming(self):
        """모든 백그라운드 스트리밍 중지"""
        rtsp_urls = list(self.background_streaming.keys())
        for rtsp_url in rtsp_urls:
            self.stop_background_streaming(rtsp_url)
    
    def cleanup_all_resources(self):
        """모든 카메라 리소스 정리 (메모리 누수 방지)"""
        print("🧹 모든 카메라 리소스 정리 시작...")
        
        # 모든 백그라운드 스트리밍 중지
        self.stop_all_background_streaming()
        
        # 모든 카메라 연결 해제
        with self.global_lock:
            rtsp_urls = list(self.cameras.keys())
            for rtsp_url in rtsp_urls:
                self.cleanup_camera(rtsp_url)
        
        print("✅ 모든 카메라 리소스 정리 완료")

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
        
        # 전역 큐 사용
        self.alert_queue = GLOBAL_ALERT_QUEUE
        # 한글 폰트 설정
        self.setup_korean_font()
        # 전체 스크린샷 저장
        self.all_detection_dir = os.path.join(settings.MEDIA_ROOT, 'all_detections')
        self.ensure_all_detection_dir()

    def setup_korean_font(self):
        """한글 폰트 설정"""
        # Windows 환경
        font_paths = [
            "C:/Windows/Fonts/malgun.ttf",  # 맑은 고딕
            "C:/Windows/Fonts/gulim.ttc",   # 굴림
            "C:/Windows/Fonts/batang.ttc",  # 바탕
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # macOS
        ]
        
        self.korean_font = None
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    self.korean_font = font_path
                    print(f"✅ 한글 폰트 로드: {font_path}")
                    break
                except:
                    continue
        
        if not self.korean_font:
            print("⚠️ 한글 폰트를 찾을 수 없습니다. 영문만 표시됩니다.")
    
    def ensure_screenshot_dir(self):
        """스크린샷 저장 디렉토리 생성"""
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir, exist_ok=True)
    
    def ensure_all_detection_dir(self):
        """모든 탐지 저장 디렉토리 생성"""
        if not os.path.exists(self.all_detection_dir):
            os.makedirs(self.all_detection_dir, exist_ok=True)
    
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
            yolo_path = os.path.join(settings.BASE_DIR, 'CCTV', 'yolo11m.pt')
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
                    # print(f"  - YOLO 주요 클래스: {list(self.yolo_model.model.names.values())[:10]}...")
                    print(f"  - YOLO 주요 클래스: {list(self.yolo_model.model.names.values())}...")
            else:
                print(f"❌ YOLO11 모델 파일을 찾을 수 없습니다: {yolo_path}")
            
            # CLIP 모델 로드
            try:
                print(f"\n  - CLIP 모델 로드 중...")
                self.clip_model, self.clip_preprocess = clip.load("ViT-L/14@336px", device=self.device)
                print(f"✅ CLIP 모델 로드 완료 (device: {self.device})")
            except Exception as clip_error:
                # CLIP 모델 로드 실패 시 CPU로 재시도
                print(f"⚠️ CLIP GPU 로드 실패, CPU로 재시도: {clip_error}")
                self.device = "cpu"
                self.clip_model, self.clip_preprocess = clip.load("ViT-L/14@336px", device=self.device)
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
        """카메라별 탐지 워커 - 타임스탬프 표시 버전"""
        from .models import TargetLabel, DetectionLog
        
        print(f"\n🚀 탐지 워커 시작: 카메라 '{camera.name}' (ID: {camera.id})")
        last_detection_time = time.time()
        
        while self.detection_active.get(camera.id, False):
            try:
                camera_info = camera_streamer.get_camera_stream(camera.rtsp_url)
                
                if not camera_info['is_connected']:
                    print(f"⚠️ 카메라 '{camera.name}' 연결되지 않음")
                    time.sleep(2)
                    continue
                
                frame_queue = camera_streamer.frame_queues.get(camera.rtsp_url)
                if not frame_queue:
                    time.sleep(1)
                    continue
                
                # 프레임 가져오기
                frame_data = None
                try:
                    frame_data = frame_queue.get(timeout=1.0)
                except queue.Empty:
                    time.sleep(0.5)
                    continue
                
                # 프레임 데이터 추출
                if isinstance(frame_data, dict):
                    frame = frame_data.get('frame')
                    frame_timestamp = frame_data.get('timestamp_str', 'Unknown')
                    frame_age = time.time() - frame_data.get('timestamp', time.time())
                else:
                    # 구버전 호환성
                    frame = frame_data
                    frame_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    frame_age = 0
                
                if frame is None:
                    continue
                
                # 프레임 정보 출력
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                print(f"\n📹 프레임 획득: 카메라 '{camera.name}'")
                print(f"   - 프레임 캡처 시간: {frame_timestamp}")
                print(f"   - 현재 처리 시간: {current_time}")
                print(f"   - 프레임 지연: {frame_age:.2f}초")
                print(f"   - 프레임 크기: {frame.shape}")
                
                # 프레임이 너무 오래되었으면 스킵
                if frame_age > 5.0:
                    print(f"   ⚠️ 프레임이 너무 오래됨 ({frame_age:.1f}초), 스킵")
                    continue
                
                # 타겟 라벨 가져오기
                target_labels = list(camera.target_labels.all())
                if not target_labels:
                    print(f"⚠️ 카메라 '{camera.name}'에 타겟 라벨이 없음")
                    time.sleep(5)
                    continue
                
                print(f"🎯 타겟 라벨 {len(target_labels)}개로 탐지 시작")
                
                # 탐지 시작 시간 기록
                detection_start = time.time()
                
                # 객체 탐지 수행
                # detections = self._detect_objects(frame, target_labels)
                detections = self._detect_objects(frame, target_labels, camera)

                # 탐지 소요 시간
                detection_duration = time.time() - detection_start
                print(f"⏱️ 탐지 소요 시간: {detection_duration:.2f}초")
                
                # 탐지 결과 처리
                if detections:
                    print(f"✨ 탐지 완료! {len(detections)}개 타겟 발견 (시간: {current_time})")
                    for detection in detections:
                        self._process_detection(camera, frame, detection, target_labels)
                        # 매 탐지마다 별도 스크린샷 저장
                        self._save_all_detection_screenshot(camera, frame, detection)
                else:
                    print(f"💤 탐지된 객체 없음 (시간: {current_time})")
                
                # 탐지 간격 계산 및 표시
                time_since_last = time.time() - last_detection_time
                print(f"📊 탐지 주기: {time_since_last:.1f}초")
                last_detection_time = time.time()
                
                # 탐지 간격
                time.sleep(1.5)
                
            except Exception as e:
                print(f"❌ 탐지 워커 오류 (카메라: {camera.name}): {e}")
                import traceback
                traceback.print_exc()
                time.sleep(2)
        
        print(f"🛑 탐지 워커 종료: 카메라 '{camera.name}'")

    def _detect_objects(self, frame, target_labels, camera):
        """
        Softmax 방식으로 객체 탐지
        - YOLO는 후보 박스만 제공
        - CLIP이 모든 라벨 + "other object"를 동시에 비교
        - "other object"가 최고점이면 무시
        """
        detections = []
        
        # 임계치 설정
        YOLO_CANDIDATE_THRESHOLD = 0.6   # YOLO 후보 박스 임계치
        CLIP_CONFIDENCE_THRESHOLD = 0.6   # CLIP softmax 최소 신뢰도
        
        if self.yolo_model is None or self.clip_model is None:
            print("⚠️ YOLO 또는 CLIP 모델이 로드되지 않음")
            return detections
        
        try:
            # 1. YOLO로 후보 박스 추출
            results = self.yolo_model(frame, conf=YOLO_CANDIDATE_THRESHOLD, verbose=True, imgsz=960)
            
            if not results or len(results) == 0:
                return detections
            
            yolo_result = results[0]
            
            if not hasattr(yolo_result, 'boxes') or yolo_result.boxes is not None:
                boxes = yolo_result.boxes.xyxy.cpu().numpy()
                confidences = yolo_result.boxes.conf.cpu().numpy() if yolo_result.boxes.conf is not None else []
                classes = yolo_result.boxes.cls.cpu().numpy() if yolo_result.boxes.cls is not None else []
                
                if len(boxes) == 0:
                    return detections
                
                # print(f"📊 YOLO 후보 박스: {len(boxes)}개 탐지")
                
                # YOLO 클래스 이름 가져오기 (디버깅용)
                class_names = yolo_result.names if hasattr(yolo_result, 'names') else {}
                
                # 2. CLIP을 위한 텍스트 준비 (DB 라벨 + "other object")
                text_queries = []
                label_indices = []  # 각 쿼리가 어떤 라벨에 해당하는지 추적
                
                # DB에서 가져온 라벨들
                for i, target_label in enumerate(target_labels):
                    query = f"a photo of {target_label.label_name}"
                    text_queries.append(query)
                    label_indices.append(i)
                
                # "other object" 추가 (항상 마지막)
                text_queries.append("other object")
                other_object_idx = len(text_queries) - 1
                
                # print(f"등록된 객체 이름 : {[tl.display_name for tl in target_labels]}")
                # print(f"🎯 비교할 라벨: {[tl.label_name for tl in target_labels]} + 'other object'")
                
                # 텍스트 토큰화
                text_tokens = clip.tokenize(text_queries).to(self.device)
                
                with torch.no_grad():
                    text_features = self.clip_model.encode_text(text_tokens)
                    text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                
                # 3. 각 타겟 라벨별로 탐지된 박스들을 수집
                label_detections = {i: [] for i in range(len(target_labels))}
                
                # print(f"🔧 현재 CLIP_CONFIDENCE_THRESHOLD: {CLIP_CONFIDENCE_THRESHOLD}")

                # 4. 각 박스에 대해 CLIP으로 분류
                for box_idx, (box, yolo_conf, cls) in enumerate(zip(boxes, confidences, classes)):
                    x1, y1, x2, y2 = map(int, box)
                    
                    # 박스 크기를 20% 확장
                    box_scale_extend = 0.1

                    box_width = x2 - x1
                    box_height = y2 - y1
                    expand_w = int(box_width * box_scale_extend)  # 양쪽으로 10%씩 = 총 20%
                    expand_h = int(box_height * box_scale_extend)  # 위아래로 10%씩 = 총 20%
                    
                    # 프레임 경계 내에서 확장
                    frame_h, frame_w = frame.shape[:2]
                    x1_expanded = max(0, x1 - expand_w)
                    y1_expanded = max(0, y1 - expand_h)
                    x2_expanded = min(frame_w, x2 + expand_w)
                    y2_expanded = min(frame_h, y2 + expand_h)
                    
                    cropped_region = frame[y1_expanded:y2_expanded, x1_expanded:x2_expanded]
                    
                    if cropped_region.size == 0:
                        continue
                    
                    # YOLO 클래스 이름 (디버깅용)
                    yolo_class = class_names.get(int(cls), f'class_{int(cls)}')
                    
                    # CLIP으로 이미지 인코딩
                    pil_crop = Image.fromarray(cv2.cvtColor(cropped_region, cv2.COLOR_BGR2RGB))
                    crop_tensor = self.clip_preprocess(pil_crop).unsqueeze(0).to(self.device)
                    
                    with torch.no_grad():
                        crop_features = self.clip_model.encode_image(crop_tensor)
                        crop_features = crop_features / crop_features.norm(dim=-1, keepdim=True)
                        
                        # 모든 텍스트와의 유사도 계산
                        logits = (crop_features @ text_features.T) * 100.0  # CLIP의 temperature scaling
                        
                        # Softmax 적용
                        probs = logits.softmax(dim=-1).cpu().numpy()[0]
                    
                    # 가장 높은 확률의 라벨 찾기
                    best_idx = int(np.argmax(probs))
                    best_prob = float(probs[best_idx])
                    
                    # print(f"   Box{box_idx} [{yolo_class}]: ", end="")
                    # for i, (query, prob) in enumerate(zip(text_queries, probs)):
                    #     if i < len(target_labels):
                    #         print(f"{target_labels[i].display_name}={prob:.2f} ", end="")
                    #     else:
                    #         print(f"other={prob:.2f} ", end="")
                    
                    # "other object"가 최고점이면 무시
                    if best_idx == other_object_idx:
                        # print(f"      ❌ 'other object'로 분류됨 ({best_prob:.2f}) - 무시")
                        continue
                    
                    # 신뢰도가 임계치 미만이면 무시
                    if best_prob < CLIP_CONFIDENCE_THRESHOLD:
                        # print(f"      ❌ 신뢰도 부족 ({best_prob:.2f} < {CLIP_CONFIDENCE_THRESHOLD})")
                        continue
                    
                    # 해당 라벨로 분류
                    label_idx = label_indices[best_idx]
                    target_label = target_labels[label_idx]
                    
                    print(f"      ✅ '{target_label.display_name}'로 탐지! (신뢰도: {best_prob:.2f})")
                    
                    label_detections[label_idx].append({
                        'box': [x1, y1, x2, y2],
                        'confidence': best_prob,
                        'yolo_confidence': float(yolo_conf),
                        'clip_probability': best_prob,
                        'yolo_class': yolo_class
                    })
                
                # 5. 각 라벨별로 탐지 결과 생성
                for label_idx, detected_boxes in label_detections.items():
                    if detected_boxes:
                        target_label = target_labels[label_idx]
                        avg_confidence = sum(box['confidence'] for box in detected_boxes) / len(detected_boxes)
                        
                        detection = {
                            'label': target_label,
                            'confidence': float(avg_confidence),
                            'count': len(detected_boxes),
                            'has_alert': target_label.has_alert,
                            'boxes': detected_boxes
                        }
                        
                        detections.append(detection)
                        
                        # print(f"\n🎯 {target_label.display_name} 최종 탐지:")
                        # print(f"   - 박스 수: {len(detected_boxes)}개")
                        # print(f"   - 평균 신뢰도: {avg_confidence:.1%}")
                        # print(f"   - 경고 설정: {'활성' if target_label.has_alert else '비활성'}")
                
                if not detections:
                    print(f"💤 탐지된 유효 객체 없음 (모두 'other object'이거나 신뢰도 미달)")
            
        except Exception as e:
            print(f"❌ 객체 탐지 오류: {e}")
            import traceback
            traceback.print_exc()
        
        return detections


    # def _detect_objects(self, frame, target_labels):
    #     """프레임에서 객체 탐지 - 바운딩 박스 정보 포함"""
    #     detections = []
        
    #     if self.yolo_model is None or self.clip_model is None:
    #         print("⚠️ 디버그: YOLO 또는 CLIP 모델이 로드되지 않음")
    #         return detections
        
    #     try:
    #         # YOLO로 1차 객체 탐지 (바운딩 박스 획득)
    #         results = self.yolo_model(frame, verbose=False)
            
    #         if not results or len(results) == 0:
    #             return detections
            
    #         yolo_result = results[0]
            
    #         if hasattr(yolo_result, 'boxes') and yolo_result.boxes is not None:
    #             boxes = yolo_result.boxes.xyxy.cpu().numpy()
    #             confidences = yolo_result.boxes.conf.cpu().numpy() if yolo_result.boxes.conf is not None else []
                
    #             # 신뢰도 0.6 이상인 바운딩 박스만 사용
    #             high_conf_mask = confidences >= 0.2
    #             valid_boxes = boxes[high_conf_mask]
    #             valid_confidences = confidences[high_conf_mask]
                
    #             if len(valid_boxes) == 0:
    #                 return detections
                
    #             # 각 타겟 라벨에 대해 CLIP으로 분류
    #             for target_label in target_labels:
    #                 detected_boxes = []
                    
    #                 for idx, (box, yolo_conf) in enumerate(zip(valid_boxes, valid_confidences)):
    #                     x1, y1, x2, y2 = map(int, box)
    #                     cropped_region = frame[y1:y2, x1:x2]
                        
    #                     if cropped_region.size > 0:
    #                         # CLIP으로 해당 영역 분류
    #                         pil_crop = Image.fromarray(cv2.cvtColor(cropped_region, cv2.COLOR_BGR2RGB))
    #                         crop_tensor = self.clip_preprocess(pil_crop).unsqueeze(0).to(self.device)
                            
    #                         text_query = f"a photo of {target_label.label_name}"
    #                         text_token = clip.tokenize([text_query]).to(self.device)
                            
    #                         with torch.no_grad():
    #                             # 특징 추출
    #                             crop_features = self.clip_model.encode_image(crop_tensor)
    #                             text_features = self.clip_model.encode_text(text_token)
                                
    #                             # L2 정규화 (중요!)
    #                             crop_features = crop_features / crop_features.norm(dim=-1, keepdim=True)
    #                             text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                                
    #                             # 코사인 유사도 계산 (이제 -1에서 1 사이)
    #                             similarity = (crop_features @ text_features.T).cpu().numpy()[0][0]
                                
    #                             # 0-1 범위로 변환 (선택적)
    #                             similarity_normalized = (similarity + 1) / 2
                                
    #                             print(f"     CLIP 유사도: 원본={similarity:.3f}, 정규화={similarity_normalized:.3f}")
                            
    #                         # CLIP 임계값 (정규화된 값 기준으로 조정)
    #                         if similarity_normalized > 0.6:  # 신뢰도.
    #                             # YOLO 신뢰도와 CLIP 유사도의 평균 사용
    #                             combined_confidence = (float(yolo_conf) + float(similarity_normalized)) / 2
                                
    #                             detected_boxes.append({
    #                                 'box': [x1, y1, x2, y2],
    #                                 'confidence': combined_confidence,  # 결합된 신뢰도
    #                                 'yolo_confidence': float(yolo_conf),
    #                                 'clip_similarity': float(similarity_normalized)
    #                             })
    #                             print(f"     ✅ Box{idx}: 매칭! (YOLO={yolo_conf:.2f}, CLIP={similarity_normalized:.2f}, 결합={combined_confidence:.2f})")
                    
    #                 # 해당 라벨로 분류된 객체가 있다면 탐지 결과에 추가
    #                 if detected_boxes:
    #                     # 평균 신뢰도 계산
    #                     avg_confidence = sum(box['confidence'] for box in detected_boxes) / len(detected_boxes)
                        
    #                     detections.append({
    #                         'label': target_label,
    #                         'confidence': float(avg_confidence),  # 0-1 범위
    #                         'count': len(detected_boxes),
    #                         'has_alert': target_label.has_alert,
    #                         'boxes': detected_boxes
    #                     })
                        
    #                     print(f"     🎯 최종 탐지: {len(detected_boxes)}개 (평균 신뢰도: {avg_confidence:.1%})")
            
    #     except Exception as e:
    #         print(f"❌ 객체 탐지 오류: {e}")
    #         import traceback
    #         traceback.print_exc()
        
    #     return detections

    def _process_detection(self, camera, frame, detection, target_labels):
        """탐지 결과 처리 - 바운딩 박스 포함 스크린샷"""
        from .models import DetectionLog
        
        try:
            if detection['has_alert']:
                print(f"\n📝 탐지 결과 처리:")
                print(f"  - 카메라: {camera.name}")
                print(f"  - 객체: {detection['label'].display_name}")
                print(f"  - 개수: {detection['count']}")
                print(f"  - 신뢰도: {detection['confidence']:.3f}")
                print(f"  - 알림 여부: {'예' if detection['has_alert'] else '아니오'}")
            
            # 스크린샷 저장 (has_alert인 경우 + 바운딩 박스 그리기)
            screenshot_path = None
            if detection['has_alert']:
                # 프레임에 바운딩 박스 그리기
                annotated_frame = self._draw_detection_boxes(frame, detection)
                screenshot_path = self._save_screenshot_with_boxes(camera, annotated_frame, detection)
                
                if screenshot_path:
                    print(f"  - 📸 스크린샷 저장 (박스 포함): {screenshot_path}")
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
            
        except Exception as e:
            print(f"❌ 탐지 결과 처리 오류: {e}")
            import traceback
            traceback.print_exc()

    def _draw_detection_boxes(self, frame, detection):
        """프레임에 바운딩 박스와 라벨 그리기 (한글 지원)"""
        # 프레임 복사 (원본 보존)
        annotated_frame = frame.copy()
        
        # OpenCV BGR을 PIL RGB로 변환
        frame_rgb = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_image)
        
        # 폰트 설정 (한글 지원)
        try:
            if self.korean_font:
                font = ImageFont.truetype(self.korean_font, 24)
                small_font = ImageFont.truetype(self.korean_font, 18)
            else:
                # 기본 폰트 (영문만)
                font = ImageFont.load_default()
                small_font = font
        except:
            font = ImageFont.load_default()
            small_font = font
        
        # 색상 설정
        if detection['has_alert']:
            box_color = (255, 0, 0)  # 빨간색 (경고)
            text_bg_color = (255, 0, 0)
        else:
            box_color = (0, 255, 0)  # 초록색 (일반)
            text_bg_color = (0, 255, 0)
        text_color = (255, 255, 255)  # 흰색 텍스트
        
        # 각 바운딩 박스 그리기
        if 'boxes' in detection and detection['boxes']:
            for idx, box_info in enumerate(detection['boxes']):
                x1, y1, x2, y2 = box_info['box']
                confidence = box_info['confidence']
                
                # 바운딩 박스 그리기 (두께 3)
                draw.rectangle([x1, y1, x2, y2], outline=box_color, width=3)
                
                # 라벨 텍스트 준비
                label_text = f"{detection['label'].display_name} {confidence*100:.1f}%"
                
                # 텍스트 크기 계산
                try:
                    bbox = draw.textbbox((x1, y1), label_text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except:
                    # textbbox가 없는 경우 (구버전 Pillow)
                    text_width, text_height = draw.textsize(label_text, font=font)
                
                # 텍스트 배경 그리기
                text_bg_y1 = max(0, y1 - text_height - 10)
                text_bg_y2 = y1
                draw.rectangle(
                    [x1, text_bg_y1, x1 + text_width + 10, text_bg_y2],
                    fill=text_bg_color
                )
                
                # 텍스트 그리기
                draw.text(
                    (x1 + 5, text_bg_y1 + 2),
                    label_text,
                    font=font,
                    fill=text_color
                )
                
                # 박스 번호 (여러 개일 경우)
                if len(detection['boxes']) > 1:
                    box_num_text = f"#{idx+1}"
                    draw.text(
                        (x1 + 5, y1 + 5),
                        box_num_text,
                        font=small_font,
                        fill=box_color
                    )
        
        # 전체 정보 표시 (우측 상단)
        info_text = f"총 {detection['count']}개 탐지"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 정보 배경
        info_bg_x1 = pil_image.width - 250
        info_bg_y1 = 10
        info_bg_x2 = pil_image.width - 10
        info_bg_y2 = 70
        
        draw.rectangle(
            [info_bg_x1, info_bg_y1, info_bg_x2, info_bg_y2],
            fill=(0, 0, 0, 180)  # 반투명 검정
        )
        
        draw.text(
            (info_bg_x1 + 10, info_bg_y1 + 5),
            info_text,
            font=font,
            fill=(255, 255, 255)
        )
        
        draw.text(
            (info_bg_x1 + 10, info_bg_y1 + 30),
            timestamp,
            font=small_font,
            fill=(200, 200, 200)
        )
        
        # PIL 이미지를 OpenCV 형식으로 변환
        annotated_frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        
        return annotated_frame
    
    def _save_screenshot_with_boxes(self, camera, annotated_frame, detection):
        """바운딩 박스가 그려진 스크린샷 저장"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 파일명에 한글 포함 시 문제 방지
            safe_object_name = detection['label'].display_name.replace(' ', '_')
            # 한글을 영문으로 변환하거나 ID 사용
            if not safe_object_name.isascii():
                safe_object_name = f"object_{detection['label'].id}"
            
            filename = f"{camera.id}_{timestamp}_{safe_object_name}.jpg"
            filepath = os.path.join(self.screenshot_dir, filename)
            
            # 스크린샷 저장 (JPEG 품질 95)
            cv2.imwrite(filepath, annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            print(f"    💾 스크린샷 저장 완료: {filename}")
            return filepath
            
        except Exception as e:
            print(f"❌ 스크린샷 저장 오류: {e}")
            return None
    
    def _save_all_detection_screenshot(self, camera, frame, detection):
        """모든 탐지 결과에 대한 스크린샷 저장 (별도 폴더)"""
        try:
            # 날짜별 폴더 생성
            today = datetime.now().strftime("%Y%m%d")
            daily_dir = os.path.join(self.all_detection_dir, today)
            if not os.path.exists(daily_dir):
                os.makedirs(daily_dir, exist_ok=True)
            
            # 카메라별 폴더 생성
            camera_dir = os.path.join(daily_dir, f"camera_{camera.id}")
            if not os.path.exists(camera_dir):
                os.makedirs(camera_dir, exist_ok=True)
            
            # 탐지된 객체별 폴더 생성
            safe_object_name = detection['label'].display_name.replace(' ', '_')
            if not safe_object_name.isascii():
                safe_object_name = f"object_{detection['label'].id}"
            
            object_dir = os.path.join(camera_dir, safe_object_name)
            if not os.path.exists(object_dir):
                os.makedirs(object_dir, exist_ok=True)
            
            # 바운딩 박스가 그려진 프레임 생성
            annotated_frame = self._draw_detection_boxes(frame, detection)
            
            # 파일명 생성 (시간 + 신뢰도)
            timestamp = datetime.now().strftime("%H%M%S")
            confidence = detection['confidence']
            filename = f"{timestamp}_{confidence:.2f}.jpg"
            filepath = os.path.join(object_dir, filename)
            
            # 스크린샷 저장
            cv2.imwrite(filepath, annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            
            print(f"    📁 모든탐지 저장: {today}/{camera.id}/{safe_object_name}/{filename}")
            return filepath
            
        except Exception as e:
            print(f"❌ 모든탐지 스크린샷 저장 오류: {e}")
            return None
    
    def _save_screenshot(self, camera, frame, detection):
        """기존 스크린샷 저장 함수 (바운딩 박스 포함 버전으로 리다이렉트)"""
        # 바운딩 박스를 그린 프레임 생성
        annotated_frame = self._draw_detection_boxes(frame, detection)
        # 저장
        return self._save_screenshot_with_boxes(camera, annotated_frame, detection)
    
    def _send_realtime_alert(self, log):
        """실시간 알림 전송 - 개선된 버전"""
        try:
            alert_data = {
                'type': 'detection_alert',
                'id': log.id,
                'camera_name': log.camera_name,
                'camera_location': log.camera_location,
                'detected_object': log.detected_object,
                'object_count': log.object_count,
                'detected_at': log.detected_at.isoformat(),
                'has_screenshot': bool(log.screenshot_path),
                'confidence': log.confidence,
                'is_new': True  # 새 알림 플래그
            }
            
            # 전역 큐에 추가
            try:
                # 큐가 가득 찬 경우 오래된 항목 제거
                if self.alert_queue.full():
                    try:
                        self.alert_queue.get_nowait()
                    except queue.Empty:
                        pass
                
                self.alert_queue.put_nowait(alert_data)
                print(f"  ✅ 알림 큐에 추가 성공: {alert_data['detected_object']}")
                print(f"  📊 큐 크기: {self.alert_queue.qsize()}/{self.alert_queue.maxsize}")
                
                # 모든 SSE 리스너에게 즉시 알림 (선택적)
                for listener in ALERT_LISTENERS:
                    try:
                        listener(alert_data)
                    except:
                        pass
                        
            except queue.Full:
                print(f"  ⚠️ 알림 큐가 가득 참")
            except Exception as e:
                print(f"  ❌ 큐 추가 오류: {e}")
                
        except Exception as e:
            print(f"❌ 실시간 알림 전송 오류: {e}")
            import traceback
            traceback.print_exc()

    def get_alert_queue(self):
        """알림 큐 반환"""
        return self.alert_queue
    
    def start_all_detections(self):
        """모든 활성 카메라에 대한 탐지 시작 (자동 시작 모드)"""
        from .models import Camera
        
        cameras = Camera.objects.all()
        started_count = 0
        
        for camera in cameras:
            # 타겟 라벨이 있는 카메라이거나, 자동 시작 모드에서는 모든 카메라 시작
            if camera.target_labels.exists():
                self.start_detection_for_camera(camera)
                started_count += 1
            else:
                print(f"⚠️ 카메라 '{camera.name}'에 타겟 라벨이 없어 AI 탐지를 건너뜁니다")
        
        print(f"🤖 총 {started_count}개 카메라에서 AI 탐지 시작됨")
    
    def stop_all_detections(self):
        """모든 탐지 중지"""
        for camera_id in list(self.detection_active.keys()):
            self.stop_detection_for_camera(camera_id)

# 싱글톤 인스턴스
camera_streamer = CameraStreamer()
ai_detection_system = AIDetectionSystem()

# 알림 큐 접근을 위한 헬퍼 함수
def get_global_alert_queue():
    """전역 알림 큐 반환"""
    return GLOBAL_ALERT_QUEUE