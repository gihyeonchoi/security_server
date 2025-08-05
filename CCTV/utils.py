# CCTV/utils.py
import cv2
import threading
import time
import queue
from django.http import StreamingHttpResponse
import json
import numpy as np
from collections import deque

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

# 싱글톤 인스턴스
camera_streamer = CameraStreamer()