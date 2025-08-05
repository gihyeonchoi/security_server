# CCTV/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import json
import os

class Camera(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    rtsp_url = models.CharField(max_length=500)

    def __str__(self):
        return f"{self.name} @ {self.location}"

class TargetLabel(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='target_labels')
    display_name = models.CharField(max_length=100, help_text="화면에 표시할 이름")
    label_name = models.CharField(max_length=200,  help_text="객체 탐지 자연어 토큰")   # CLIP용 입력 텍스트
    has_alert = models.BooleanField(default=False, verbose_name="경고 여부")            # 경고할건지 안할건지
    

    def __str__(self):
        return f"[{self.camera.name}] {self.display_name or self.label_name}"

class DetectionLog(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='detection_logs')
    camera_name = models.CharField(max_length=100, help_text="카메라 이름 (로그용)")
    camera_location = models.CharField(max_length=200, help_text="카메라 위치 (로그용)")
    detected_object = models.CharField(max_length=100, help_text="탐지된 객체")
    object_count = models.PositiveIntegerField(help_text="탐지된 객체 개수")
    confidence = models.FloatField(help_text="탐지 신뢰도 (0.0-1.0)")
    has_alert = models.BooleanField(default=False, help_text="경고 객체 여부")
    screenshot_path = models.CharField(max_length=500, blank=True, null=True, help_text="스크린샷 파일 경로")
    detected_at = models.DateTimeField(default=timezone.now, help_text="탐지 시각")
    
    class Meta:
        ordering = ['-detected_at']
        verbose_name = "탐지 로그"
        verbose_name_plural = "탐지 로그들"
    
    def __str__(self):
        return f"[{self.detected_at.strftime('%Y-%m-%d %H:%M:%S')}] {self.camera_name}: {self.detected_object} ({self.object_count}개)"
    
    @property
    def screenshot_exists(self):
        """스크린샷 파일이 존재하는지 확인"""
        if self.screenshot_path and os.path.exists(self.screenshot_path):
            return True
        return False