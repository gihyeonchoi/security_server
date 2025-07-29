# CCTV/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# REST API 라우터
router = DefaultRouter()
router.register(r'cameras', views.CameraConfigViewSet)

app_name = 'cctv'

urlpatterns = [
    # HTML 페이지
    path('', views.camera_dashboard, name='dashboard'),
    path('camera/<int:camera_id>/', views.camera_detail, name='camera_detail'),
    path('live/', views.live_view, name='live_view'),
    
    # Pipeline 기반 비디오 스트림 (WebSocket 정보 반환)
    path('stream/<int:camera_id>/', views.video_feed, name='video_feed'),
    
    # Pipeline 제어 엔드포인트
    path('detection/<int:camera_id>/', views.detection_results, name='detection_results'),
    path('detection/<int:camera_id>/start/', views.start_detection, name='start_detection'),
    path('detection/<int:camera_id>/stop/', views.stop_detection, name='stop_detection'),
    path('detection/start-all/', views.start_all_detection_view, name='start_all_detection'),
    path('detection/stop-all/', views.stop_all_detection_view, name='stop_all_detection'),
    path('detection/status/', views.detection_status_view, name='detection_status'),
    
    # REST API
    path('api/', include(router.urls)),
    
    # 간단한 JSON API
    path('json/cameras/', views.camera_config_json, name='camera_json_list'),
    path('json/cameras/<int:camera_id>/', views.camera_config_json, name='camera_json_detail'),
]