# CCTV/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import json

class CameraConfig(models.Model):
    """CCTV 카메라 설정 모델"""
    name = models.CharField(max_length=100, unique=True, help_text="카메라 식별명")
    api_key = models.CharField(max_length=255, help_text="ROBOFLOW API 키")
    workspace_name = models.CharField(max_length=100, help_text="ROBOFLOW 워크스페이스명")
    workflow_id = models.CharField(max_length=100, help_text="워크플로우 ID")
    rtsp_url = models.CharField(max_length=500, help_text="RTSP 스트림 URL")
    max_fps = models.IntegerField(
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        help_text="최대 FPS (1-60)"
    )
    is_active = models.BooleanField(default=True, help_text="카메라 활성화 상태")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "카메라 설정"
        verbose_name_plural = "카메라 설정"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({'활성' if self.is_active else '비활성'})"
    
    def to_dict(self):
        """딕셔너리 형태로 변환 (API 응답용)"""
        return {
            'id': self.id,
            'name': self.name,
            'api_key': self.api_key,
            'workspace_name': self.workspace_name,
            'workflow_id': self.workflow_id,
            'rtsp_url': self.rtsp_url,
            'max_fps': self.max_fps,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }