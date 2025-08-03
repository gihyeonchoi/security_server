# CCTV/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import views_rtsp

# REST API 라우터
router = DefaultRouter()
router.register(r'cameras', views.CameraConfigViewSet)

app_name = 'cctv'

urlpatterns = [
    # HTML 페이지
    path('', views.camera_dashboard, name='dashboard'),
    path('test/', views.simple_test, name='simple_test'),
    path('camera/<int:camera_id>/', views.camera_detail, name='camera_detail'),
    path('live/', views.live_view, name='live_view'),
    path('multi-camera/', views.multi_camera_view, name='multi_camera'),
    
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
    
    # 새로운 카메라 스트리밍 API
    path('camera/<int:camera_id>/stream/', views.single_camera_stream, name='single_camera_stream'),
    path('api/camera-status/', views.camera_status_api, name='camera_status_api'),
    path('api/reset-detector/', views.reset_detector, name='reset_detector'),
    
    # =============================================================================
    # 새로운 RTSP_Camera 기반 MJPEG 스트리밍 엔드포인트
    # =============================================================================
    
    # HTML 페이지
    path('grid/', views_rtsp.camera_grid_view, name='camera_grid'),
    path('settings/', views_rtsp.camera_settings_view, name='camera_settings'),
    
    # MJPEG 스트리밍
    path('mjpeg/<str:camera_id>/', views_rtsp.mjpeg_stream, name='mjpeg_stream'),
    
    # API 엔드포인트
    path('rtsp/status/', views_rtsp.camera_status, name='rtsp_camera_status'),
    path('rtsp/objects/', views_rtsp.get_available_objects, name='rtsp_available_objects'),
    path('rtsp/camera/<str:camera_id>/config/', views_rtsp.get_camera_config, name='rtsp_camera_config'),
    path('rtsp/camera/<str:camera_id>/objects/', views_rtsp.update_detection_objects, name='rtsp_update_objects'),
    path('rtsp/restart/', views_rtsp.restart_detector, name='rtsp_restart'),
    path('rtsp/health/', views_rtsp.health_check, name='rtsp_health'),
]