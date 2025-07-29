from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/cctv/camera/(?P<camera_id>\w+)/$', consumers.CameraDetectionConsumer.as_asgi()),
    re_path(r'ws/cctv/live/$', consumers.LiveViewConsumer.as_asgi()),
]