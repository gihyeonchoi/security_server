# CCTV/models.py
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import json

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