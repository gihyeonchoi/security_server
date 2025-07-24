# CCTV/serializers.py
from rest_framework import serializers
from .models import CameraConfig

class CameraConfigSerializer(serializers.ModelSerializer):
    """카메라 설정 시리얼라이저"""
    
    class Meta:
        model = CameraConfig
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def validate_max_fps(self, value):
        """FPS 유효성 검사"""
        if value < 1 or value > 60:
            raise serializers.ValidationError("FPS는 1에서 60 사이여야 합니다.")
        return value
    
    def validate_rtsp_url(self, value):
        """RTSP URL 유효성 검사"""
        if not value.startswith('rtsp://'):
            raise serializers.ValidationError("RTSP URL은 'rtsp://'로 시작해야 합니다.")
        return value