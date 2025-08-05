# map/urls.py (새로 만들기)
from django.urls import path
from . import views

urlpatterns = [
    path('', views.map_view, name='map_page'), # /map/ 경로
    path('location/', views.location_api, name='location_api'), # /map/location/ 경로
]