from django.db import models
from django.urls import reverse


class Location(models.Model):
    """건물/위치 정보"""
    name = models.CharField(max_length=100, help_text="건물명 (예: 대학본부, 공학관)")
    address = models.CharField(max_length=200, blank=True, help_text="주소")
    description = models.TextField(blank=True, help_text="설명")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "위치"
        verbose_name_plural = "위치들"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Floor(models.Model):
    """층별 지도 정보"""
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='floors', verbose_name="위치")
    name = models.CharField(max_length=100, help_text="층 이름 (예: 1층, 2층, 지하1층)")
    floor_number = models.IntegerField(help_text="정렬용 층수 (-1, 1, 2, 3...)")
    map_image = models.ImageField(upload_to='maps/%Y/%m/', help_text="지도 이미지 파일")
    
    # GPS 좌표 범위 (기존 코드에서 사용중)
    top_left_lat = models.FloatField(null=True, blank=True, help_text="좌상단 위도")
    top_left_lon = models.FloatField(null=True, blank=True, help_text="좌상단 경도")
    bottom_right_lat = models.FloatField(null=True, blank=True, help_text="우하단 위도")
    bottom_right_lon = models.FloatField(null=True, blank=True, help_text="우하단 경도")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "층"
        verbose_name_plural = "층들"
        ordering = ['location', 'floor_number']
        unique_together = ['location', 'floor_number']
    
    def __str__(self):
        return f"{self.location.name} {self.name}"
    
    def get_absolute_url(self):
        return reverse('map:floor_detail', kwargs={'pk': self.pk})


class CameraPosition(models.Model):
    """카메라 위치 정보"""
    camera = models.OneToOneField('CCTV.Camera', on_delete=models.CASCADE, related_name='position', verbose_name="카메라")
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='camera_positions', verbose_name="층")
    
    # 지도상 위치 (퍼센트 단위, 0.0-100.0)
    x_position = models.FloatField(help_text="지도상 X 좌표 (퍼센트, 0-100)")
    y_position = models.FloatField(help_text="지도상 Y 좌표 (퍼센트, 0-100)")
    
    is_active = models.BooleanField(default=True, help_text="활성화 여부")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "카메라 위치"
        verbose_name_plural = "카메라 위치들"
        unique_together = ['camera', 'floor']
    
    def __str__(self):
        return f"{self.camera.name} @ {self.floor}"
    
    @property
    def stream_url(self):
        """CCTV 스트림 URL 반환"""
        return reverse('cctv:camera_stream', kwargs={'camera_id': self.camera.id})
    
    def get_absolute_url(self):
        return reverse('map:camera_position_detail', kwargs={'pk': self.pk})
