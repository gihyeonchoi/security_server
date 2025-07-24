# CCTV/views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CameraConfig
from .serializers import CameraConfigSerializer
import json

# HTML 뷰
def camera_dashboard(request):
    """카메라 대시보드 페이지"""
    cameras = CameraConfig.objects.all()
    return render(request, 'dashboard.html', {'cameras': cameras})

def camera_detail(request, camera_id):
    """개별 카메라 상세 페이지"""
    camera = get_object_or_404(CameraConfig, id=camera_id)
    return render(request, 'camera_detail.html', {'camera': camera})

# REST API ViewSet
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

# 간단한 JSON API (REST framework 없이)
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