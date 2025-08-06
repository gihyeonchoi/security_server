"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# from RFID import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('RFID/', include('RFID.urls')),
    path('cctv/', include('CCTV.urls')),
    path('CCTV/', include('CCTV.urls')),  # 대문자도 지원
    path('map/', include('map.urls')),
    path('', include('map.urls')),
]

# 개발 환경에서 정적 파일 서빙
if settings.DEBUG:
    # Django의 기본 정적 파일 처리 사용
    from django.contrib.staticfiles import views
    from django.urls import re_path
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', views.serve),
    ]
    # 미디어 파일도 서빙 (이미지 업로드용)
    if hasattr(settings, 'MEDIA_URL') and hasattr(settings, 'MEDIA_ROOT'):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
