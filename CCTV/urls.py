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
    
    # REST API
    path('api/', include(router.urls)),
    
    # 간단한 JSON API
    path('json/cameras/', views.camera_config_json, name='camera_json_list'),
    path('json/cameras/<int:camera_id>/', views.camera_config_json, name='camera_json_detail'),
]