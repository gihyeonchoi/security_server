from django.contrib import admin
from django.utils.html import format_html
from .models import Location, Floor, CameraPosition


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'floors_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'address']
    ordering = ['name']
    
    def floors_count(self, obj):
        return obj.floors.count()
    floors_count.short_description = '층 개수'


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'floor_number', 'map_image_preview', 'cameras_count', 'created_at']
    list_filter = ['location', 'created_at']
    search_fields = ['name', 'location__name']
    ordering = ['location', 'floor_number']
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('location', 'name', 'floor_number', 'map_image')
        }),
        ('GPS 좌표 범위', {
            'fields': (('top_left_lat', 'top_left_lon'), ('bottom_right_lat', 'bottom_right_lon')),
            'classes': ['collapse']
        })
    )
    
    def map_image_preview(self, obj):
        if obj.map_image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover;" />', obj.map_image.url)
        return '이미지 없음'
    map_image_preview.short_description = '지도 미리보기'
    
    def cameras_count(self, obj):
        return obj.camera_positions.filter(is_active=True).count()
    cameras_count.short_description = '카메라 개수'


@admin.register(CameraPosition)
class CameraPositionAdmin(admin.ModelAdmin):
    list_display = ['camera', 'floor', 'position_display', 'is_active', 'stream_link', 'updated_at']
    list_filter = ['floor__location', 'floor', 'is_active', 'updated_at']
    search_fields = ['camera__name', 'floor__name', 'floor__location__name']
    ordering = ['floor__location', 'floor__floor_number', 'camera__name']
    
    fieldsets = (
        ('기본 정보', {
            'fields': ('camera', 'floor', 'is_active')
        }),
        ('위치 좌표', {
            'fields': ('x_position', 'y_position'),
            'description': '지도상에서의 위치를 퍼센트로 입력하세요 (0-100)'
        })
    )
    
    def position_display(self, obj):
        return f"({obj.x_position:.1f}%, {obj.y_position:.1f}%)"
    position_display.short_description = '위치'
    
    def stream_link(self, obj):
        if obj.camera:
            return format_html('<a href="{}" target="_blank">스트림 보기</a>', obj.stream_url)
        return '-'
    stream_link.short_description = '스트림'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('camera', 'floor', 'floor__location')
