# CCTV/views_rtsp.py - RTSP_Camera 기반 MJPEG 스트리밍 뷰

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from .models import CameraConfig
from .RTSP_Camera import MultiCameraObjectDetector, CameraConfig as RTSPCameraConfig
import json
import threading
import time
import cv2
import numpy as np

# RTSP_Camera 기반 전역 detector 인스턴스
global_detector = None
detector_lock = threading.Lock()
detector_thread = None

def init_multi_camera_detector():
    """MultiCameraObjectDetector 초기화"""
    global global_detector, detector_thread
    
    with detector_lock:
        if global_detector is not None:
            return global_detector
        
        # Django 모델에서 카메라 설정 로드
        django_cameras = CameraConfig.objects.filter(is_active=True)
        if not django_cameras.exists():
            return None
        
        # RTSP 카메라 설정으로 변환
        detector = MultiCameraObjectDetector.from_django_config(django_cameras)
        
        # 백그라운드에서 실행
        def run_detector():
            detector.run(web_mode=True)
        
        detector_thread = threading.Thread(target=run_detector)
        detector_thread.daemon = True
        detector_thread.start()
        
        global_detector = detector
        return detector

def get_detector():
    """전역 detector 인스턴스 가져오기"""
    global global_detector
    if global_detector is None:
        return init_multi_camera_detector()
    return global_detector

# =============================================================================
# HTML 뷰
# =============================================================================

def camera_grid_view(request):
    """Grid 형태로 여러 카메라 보기"""
    cameras = CameraConfig.objects.filter(is_active=True)
    detector = get_detector()
    
    return render(request, 'cctv/camera_grid.html', {
        'cameras': cameras,
        'detector_running': detector is not None
    })

def camera_settings_view(request):
    """카메라 설정 페이지"""
    cameras = CameraConfig.objects.filter(is_active=True)
    detector = get_detector()
    
    # 사용 가능한 객체 목록
    available_objects = {}
    if detector:
        available_objects = detector.get_available_detection_objects()
    else:
        available_objects = {
            "서 있는 사람": "a standing person",
            "쓰러진 사람": "a fallen person lying on the ground",
            "앉아 있는 사람": "a sitting person",
            "걷는 사람": "a walking person",
            "뛰는 사람": "a running person"
        }
    
    return render(request, 'cctv/camera_settings.html', {
        'cameras': cameras,
        'available_objects': available_objects,
        'detector_running': detector is not None
    })

# =============================================================================
# MJPEG 스트리밍
# =============================================================================

def mjpeg_stream(request, camera_id):
    """개별 카메라 MJPEG 스트림"""
    detector = get_detector()
    
    if detector is None:
        # 기본 에러 이미지 반환
        def generate_error():
            error_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(error_frame, 'Camera Not Available', (150, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(error_frame, f'Camera ID: {camera_id}', (200, 280), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            _, buffer = cv2.imencode('.jpg', error_frame)
            
            while True:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                time.sleep(0.1)
        
        return StreamingHttpResponse(generate_error(), 
                                   content_type='multipart/x-mixed-replace; boundary=frame')
    
    # 실제 스트림 반환
    return StreamingHttpResponse(detector.generate_mjpeg_stream(camera_id),
                               content_type='multipart/x-mixed-replace; boundary=frame')

# =============================================================================
# API 엔드포인트
# =============================================================================

@csrf_exempt
@api_view(['POST'])
def update_detection_objects(request, camera_id):
    """특정 카메라의 감지 객체 업데이트"""
    try:
        data = json.loads(request.body)
        detection_objects = data.get('detection_objects', {})
        
        detector = get_detector()
        if detector:
            success = detector.update_detection_objects(camera_id, detection_objects)
            if success:
                return JsonResponse({
                    'status': 'success',
                    'message': f'카메라 {camera_id} 감지 객체 업데이트 완료',
                    'detection_objects': detection_objects
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': '카메라를 찾을 수 없습니다'
                }, status=404)
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Detector가 초기화되지 않았습니다'
            }, status=500)
            
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

@csrf_exempt
@api_view(['GET'])
def get_available_objects(request):
    """사용 가능한 감지 객체 목록 조회"""
    detector = get_detector()
    if detector:
        available_objects = detector.get_available_detection_objects()
        return JsonResponse({
            'status': 'success',
            'available_objects': available_objects
        })
    else:
        # 기본 객체 목록 반환
        default_objects = {
            "서 있는 사람": "a standing person",
            "쓰러진 사람": "a fallen person lying on the ground",
            "앉아 있는 사람": "a sitting person",
            "걷는 사람": "a walking person",
            "뛰는 사람": "a running person",
            "누워 있는 사람": "a lying person",
            "올라가는 사람": "a person climbing up",
            "내려가는 사람": "a person going down",
            "손을 든 사람": "a person with raised hands",
            "가방을 든 사람": "a person carrying a bag"
        }
        return JsonResponse({
            'status': 'success',
            'available_objects': default_objects
        })

@csrf_exempt
@api_view(['GET'])
def camera_status(request):
    """모든 카메라 상태 조회"""
    detector = get_detector()
    if detector:
        status = detector.get_camera_status()
        return JsonResponse({
            'status': 'success',
            'cameras': status,
            'detector_running': True
        })
    else:
        # Django 모델에서 기본 상태 반환
        cameras = CameraConfig.objects.filter(is_active=True)
        basic_status = {}
        for camera in cameras:
            basic_status[str(camera.id)] = {
                'name': camera.name,
                'is_active': camera.is_active,
                'is_connected': False,
                'tracker_count': 0,
                'avg_fps': 0
            }
        
        return JsonResponse({
            'status': 'success',
            'cameras': basic_status,
            'detector_running': False
        })

@csrf_exempt
@api_view(['POST'])
def restart_detector(request):
    """Detector 재시작"""
    global global_detector, detector_thread
    
    with detector_lock:
        try:
            # 기존 detector 중지
            if global_detector:
                global_detector.stop()
                global_detector = None
            
            # 새로 초기화
            detector = init_multi_camera_detector()
            
            return JsonResponse({
                'status': 'success',
                'message': 'Detector 재시작 완료',
                'detector_running': detector is not None
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

@csrf_exempt
@api_view(['GET'])
def get_camera_config(request, camera_id):
    """특정 카메라의 현재 감지 객체 설정 조회"""
    try:
        camera = get_object_or_404(CameraConfig, id=camera_id)
        detector = get_detector()
        
        # 현재 설정된 감지 객체 (detector에서 가져오기)
        current_objects = {}
        if detector:
            for config in detector.camera_configs:
                if config.camera_id == camera_id:
                    current_objects = config.detection_objects
                    break
        
        # 기본값이 없으면 Django 모델 기본값 사용
        if not current_objects:
            current_objects = {
                "서 있는 사람": "a standing person",
                "쓰러진 사람": "a fallen person lying on the ground"
            }
        
        return JsonResponse({
            'status': 'success',
            'camera': {
                'id': camera.id,
                'name': camera.name,
                'rtsp_url': camera.rtsp_url,
                'is_active': camera.is_active,
                'max_fps': camera.max_fps
            },
            'current_detection_objects': current_objects
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=400)

# =============================================================================
# 유틸리티 함수
# =============================================================================

def health_check(request):
    """서비스 상태 확인"""
    detector = get_detector()
    
    return JsonResponse({
        'status': 'healthy',
        'detector_running': detector is not None,
        'active_cameras': CameraConfig.objects.filter(is_active=True).count(),
        'total_cameras': CameraConfig.objects.count()
    })