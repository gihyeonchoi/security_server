# map/urls.py
from django.urls import path
from . import views

app_name = 'map'

urlpatterns = [
    # 지도 보기
    path('', views.map_view, name='map_view'),
    path('location/', views.location_api, name='location_api'),

    # 위치 관리
    path('locations/', views.LocationListView.as_view(), name='location_list'),
    path('locations/create/', views.LocationCreateView.as_view(), name='location_create'),
    path('locations/<int:pk>/edit/', views.LocationUpdateView.as_view(), name='location_edit'),
    path('locations/<int:pk>/delete/', views.LocationDeleteView.as_view(), name='location_delete'),
    
    # 층 관리
    path('floors/', views.FloorListView.as_view(), name='floor_list'),
    path('floors/create/', views.FloorCreateView.as_view(), name='floor_create'),
    path('floors/<int:pk>/edit/', views.FloorUpdateView.as_view(), name='floor_edit'),
    path('floors/<int:pk>/delete/', views.FloorDeleteView.as_view(), name='floor_delete'),
    
    # 카메라 위치 관리
    path('camera-positions/', views.CameraPositionListView.as_view(), name='camera_position_list'),
    path('camera-positions/create/', views.CameraPositionCreateView.as_view(), name='camera_position_create'),
    path('camera-positions/<int:pk>/edit/', views.CameraPositionUpdateView.as_view(), name='camera_position_edit'),
    path('camera-positions/<int:pk>/delete/', views.CameraPositionDeleteView.as_view(), name='camera_position_delete'),
    
    # 드래그 앤 드롭 관리
    path('floors/<int:floor_id>/camera-manager/', views.camera_position_manager, name='camera_position_manager'),
    path('camera-positions/<int:position_id>/update-position/', views.update_camera_position, name='update_camera_position'),

]