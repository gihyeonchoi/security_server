# CCTV/views.py - InferencePipeline + WebSocket 연동 버전

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CameraConfig, Camera, TargetLabel
from .serializers import CameraConfigSerializer
from .roboflow_service import pipeline_manager, start_camera_detection, stop_camera_detection, start_all_detection, stop_all_detection, get_detection_status
from .RTSP_Camera import MultiCameraObjectDetector
import json
import asyncio
import logging
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

detection_tasks = {}

# 전역 detector 인스턴스
detector_instance = None

def get_or_create_detector():
    """Detector 인스턴스 가져오기 또는 생성"""
    global detector_instance
    if detector_instance is None:
        try:
            cameras = Camera.objects.all()
            logger.info(f"Creating detector with {cameras.count()} cameras from DB")
            
            if cameras.exists():
                detector_instance = MultiCameraObjectDetector.from_django_config(cameras)
                logger.info(f"Detector created with {len(detector_instance.camera_configs)} camera configs")
                logger.info(f"Connected cameras: {len(detector_instance.cameras)}")
            else:
                logger.warning("No cameras found in database")
                detector_instance = None
        except Exception as e:
            logger.error(f"Error creating detector: {e}")
            import traceback
            logger.error(traceback.format_exc())
            detector_instance = None
    else:
        logger.info("Using existing detector instance")
    
    return detector_instance

def launch_detection_task(camera_id):
    camera = CameraConfig.objects.get(id=camera_id)
    config = {
        "api_key": camera.api_key,
        "workspace_name": camera.workspace_name,
        "workflow_id": camera.workflow_id,
        "rtsp_url": camera.rtsp_url,
        "max_fps": camera.max_fps,
    }

    # asyncio task 시작
    task = asyncio.create_task(start_camera_detection(camera_id, config))
    detection_tasks[camera_id] = task


# Pipeline 기반 감지 관리 - 전역 변수 제거 (WebSocket으로 대체)

# HTML 뷰
def camera_dashboard(request):
    """카메라 대시보드 페이지"""
    try:
        cameras = CameraConfig.objects.all()
        return render(request, 'dashboard.html', {'cameras': cameras})
    except Exception as e:
        from django.http import HttpResponse
        return HttpResponse(f"Dashboard Error: {str(e)}")

def simple_test(request):
    """간단한 테스트 페이지"""
    from django.http import HttpResponse
    return HttpResponse("Server is working! Django is running correctly.")

def camera_detail(request, camera_id):
    """개별 카메라 상세 페이지"""
    camera = get_object_or_404(CameraConfig, id=camera_id)
    return render(request, 'camera_detail.html', {'camera': camera})

def live_view(request):
    """라이브 모니터링 페이지"""
    cameras = CameraConfig.objects.filter(is_active=True)
    return render(request, 'live_view.html', {'cameras': cameras})

def multi_camera_view(request):
    """모든 카메라를 한 화면에서 보는 페이지"""
    cameras = Camera.objects.all()
    
    # detector 초기화
    global detector_instance
    if detector_instance is None:
        logger.info("Detector is None, creating new instance...")
        get_or_create_detector()
    
    return render(request, 'cctv/multi_camera.html', {'cameras': cameras})

def reset_detector(request):
    """Detector 강제 재시작 (디버깅용)"""
    global detector_instance
    if detector_instance:
        try:
            detector_instance.cleanup()
        except:
            pass
    detector_instance = None
    
    # 새로 생성
    get_or_create_detector()
    
    return JsonResponse({'status': 'success', 'message': 'Detector reset completed'})

def single_camera_stream(request, camera_id):
    """개별 카메라 MJPEG 스트림"""
    try:
        detector = get_or_create_detector()
        if detector is None:
            logger.error("No detector available for streaming")
            return JsonResponse({'error': 'No detector available'}, status=500)
        
        camera_id = str(camera_id)
        
        # 카메라가 실제로 연결되어 있는지 확인
        if camera_id not in detector.cameras:
            logger.error(f"Camera {camera_id} not found in detector")
            return JsonResponse({'error': f'Camera {camera_id} not connected'}, status=404)
        
        # 웹 모드가 시작되지 않았다면 시작
        if not detector.running:
            logger.info(f"Starting detector for camera {camera_id}")
            import threading
            def start_detector():
                try:
                    detector.run(web_mode=True)
                except Exception as e:
                    logger.error(f"Error running detector: {e}")
            
            thread = threading.Thread(target=start_detector)
            thread.daemon = True
            thread.start()
            
            # 잠시 대기
            import time
            time.sleep(2)
        
        response = StreamingHttpResponse(
            detector.generate_mjpeg_stream(camera_id),
            content_type='multipart/x-mixed-replace; boundary=frame'
        )
        response['Cache-Control'] = 'no-cache'
        return response
        
    except Exception as e:
        logger.error(f"Error in single_camera_stream: {e}")
        return JsonResponse({'error': str(e)}, status=500)

def camera_status_api(request):
    """카메라 상태 API"""
    try:
        detector = get_or_create_detector()
        if detector is None:
            logger.error("Detector is None")
            return JsonResponse({'error': 'No detector available'}, status=500)
        
        logger.info(f"Detector camera_configs: {[(c.camera_id, c.name) for c in detector.camera_configs]}")
        logger.info(f"Detector cameras keys: {list(detector.cameras.keys())}")
        
        status = detector.get_camera_status()
        logger.info(f"Camera status result: {status}")
        
        return JsonResponse({
            'status': 'success',
            'cameras': status
        })
    except Exception as e:
        logger.error(f"Error in camera_status_api: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# Pipeline 기반으로 변경 - 기존 스트림 코드 제거
# WebSocket을 통해 실시간 감지 결과 전송

def video_feed(request, camera_id):
    """개별 카메라의 비디오 스트림 - Pipeline 방식으로 변경"""
    # 단순한 상태 메시지 반환 (실제 스트림은 WebSocket으로 처리)
    return JsonResponse({
        'message': 'Pipeline 기반 스트림 사용 중',
        'camera_id': camera_id,
        'websocket_url': f'/ws/cctv/camera/{camera_id}/'
    })

@csrf_exempt
def detection_results(request, camera_id):
    """현재 감지 상태 조회 (Pipeline 기반)"""
    if request.method == 'GET':
        camera_id = int(camera_id)
        status_dict = get_detection_status()
        
        return JsonResponse({
            'status': 'success',
            'camera_id': camera_id,
            'pipeline_running': camera_id in status_dict,
            'pipeline_status': status_dict.get(camera_id, 'stopped'),
            'websocket_url': f'/ws/cctv/camera/{camera_id}/'
        })
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# 새로운 Pipeline 제어 엔드포인트들
@csrf_exempt
def start_detection(request, camera_id):
    """특정 카메라 감지 시작"""
    if request.method == 'POST':
        try:
            camera_id = int(camera_id)
            # 비동기 함수를 백그라운드에서 실행
            import threading
            def run_async():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(start_camera_detection(camera_id))
                loop.close()
            
            thread = threading.Thread(target=run_async)
            thread.daemon = True
            thread.start()
            
            return JsonResponse({
                'status': 'success',
                'message': f'카메라 {camera_id} 감지 시작',
                'camera_id': camera_id
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def stop_detection(request, camera_id):
    """특정 카메라 감지 중지"""
    if request.method == 'POST':
        try:
            camera_id = int(camera_id)
            # 비동기 함수를 백그라운드에서 실행
            import threading
            def run_async():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(stop_camera_detection(camera_id))
                loop.close()
            
            thread = threading.Thread(target=run_async)
            thread.daemon = True
            thread.start()
            
            return JsonResponse({
                'status': 'success',
                'message': f'카메라 {camera_id} 감지 중지',
                'camera_id': camera_id
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def start_all_detection_view(request):
    """모든 활성 카메라 감지 시작"""
    if request.method == 'POST':
        try:
            # 비동기 함수를 백그라운드에서 실행
            import threading
            def run_async():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(start_all_detection())
                loop.close()
            
            thread = threading.Thread(target=run_async)
            thread.daemon = True
            thread.start()
            return JsonResponse({
                'status': 'success',
                'message': '모든 카메라 감지 시작'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def stop_all_detection_view(request):
    """모든 카메라 감지 중지"""
    if request.method == 'POST':
        try:
            # 비동기 함수를 백그라운드에서 실행
            import threading
            def run_async():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(stop_all_detection())
                loop.close()
            
            thread = threading.Thread(target=run_async)
            thread.daemon = True
            thread.start()
            return JsonResponse({
                'status': 'success',
                'message': '모든 카메라 감지 중지'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
def detection_status_view(request):
    """전체 감지 상태 조회"""
    if request.method == 'GET':
        try:
            status_dict = get_detection_status()
            return JsonResponse({
                'status': 'success',
                'pipelines': status_dict,
                'active_count': len(status_dict)
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# REST API ViewSet (기존 코드 유지)
class CameraConfigViewSet(viewsets.ModelViewSet):
    """카메라 설정 API ViewSet"""
    queryset = CameraConfig.objects.all()
    serializer_class = CameraConfigSerializer
    
    @action(detail=True, methods=['post'])
    def toggle_active(self, request, pk=None):
        """카메라 활성화/비활성화 토글"""
        camera = self.get_object()
        camera.is_active = not camera.is_active
        camera.save()
        serializer = self.get_serializer(camera)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def active_cameras(self, request):
        """활성화된 카메라만 조회"""
        active_cameras = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(active_cameras, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def config_dict(self, request, pk=None):
        """Python dict 형태로 설정 반환 (ROBOFLOW 연동용)"""
        camera = self.get_object()
        config = {
            "api_key": camera.api_key,
            "workspace_name": camera.workspace_name,
            "workflow_id": camera.workflow_id,
            "rtsp_url": camera.rtsp_url,
            "max_fps": camera.max_fps,
        }
        return Response(config)

# 간단한 JSON API (기존 코드 유지)
@csrf_exempt
def camera_config_json(request, camera_id=None):
    """간단한 JSON API 엔드포인트"""
    if request.method == 'GET':
        if camera_id:
            camera = get_object_or_404(CameraConfig, id=camera_id)
            return JsonResponse(camera.to_dict())
        else:
            cameras = CameraConfig.objects.all()
            return JsonResponse({
                'cameras': [camera.to_dict() for camera in cameras]
            })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            camera = CameraConfig.objects.create(**data)
            return JsonResponse(camera.to_dict(), status=201)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    elif request.method == 'PUT' and camera_id:
        try:
            camera = get_object_or_404(CameraConfig, id=camera_id)
            data = json.loads(request.body)
            for key, value in data.items():
                setattr(camera, key, value)
            camera.save()
            return JsonResponse(camera.to_dict())
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    elif request.method == 'DELETE' and camera_id:
        camera = get_object_or_404(CameraConfig, id=camera_id)
        camera.delete()
        return JsonResponse({'message': '삭제되었습니다.'}, status=204)