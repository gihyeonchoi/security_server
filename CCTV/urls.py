# CCTV/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'cctv'

urlpatterns = [
    # 메인 페이지
    path('', views.index, name='index'),
    
    # 카메라 CRUD
    path('camera/create/', views.camera_create, name='camera_create'),
    path('camera/<int:camera_id>/edit/', views.camera_edit, name='camera_edit'),
    path('camera/<int:camera_id>/delete/', views.camera_delete, name='camera_delete'),
    
    # 타겟 라벨 CRUD
    path('camera/<int:camera_id>/target-label/create/', views.target_label_create, name='target_label_create'),
    path('target-label/<int:label_id>/edit/', views.target_label_edit, name='target_label_edit'),
    path('target-label/<int:label_id>/delete/', views.target_label_delete, name='target_label_delete'),
    
    # 스트리밍 및 API
    path('camera/<int:camera_id>/stream/', views.camera_stream, name='camera_stream'),
    path('api/camera-status/', views.camera_status_api, name='camera_status_api'),
    path('multi-camera/', views.multi_camera_view, name='multi_camera_view'),
    
    # AI 탐지 관련
    path('api/detection-logs/', views.detection_logs_api, name='detection_logs_api'),
    path('detection/start/', views.start_detection, name='start_detection'),
    path('detection/stop/', views.stop_detection, name='stop_detection'),
    
    # 백그라운드 스트리밍 상태
    path('api/background-streaming-status/', views.background_streaming_status, name='background_streaming_status'),
    
    # 실시간 알림 (SSE)
    path('alerts/stream/', views.detection_alerts_stream, name='detection_alerts_stream'),
    path('clear-alert-history/', views.clear_alert_history, name='clear_alert_history'),

    # 탐지 스크린샷 대시보드
    path('detection/dashboard/', views.detection_dashboard, name='detection_dashboard'),
    path('camera/<int:camera_id>/detections/', views.camera_detection_gallery, name='camera_detection_gallery'),
]