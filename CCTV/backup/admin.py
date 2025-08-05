from django.contrib import admin
from .models import CameraConfig, Camera, TargetLabel

class TargetLabelInline(admin.TabularInline):
    """카메라 등록 정보 관리"""
    model = TargetLabel
    extra = 1

@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    """카메라 테이블 하나에서 LABEL 정보도 함께 등록"""
    inlines = [TargetLabelInline]

@admin.register(CameraConfig)
class CameraConfigAdmin(admin.ModelAdmin):
    """CCTV 카메라 설정 관리"""
    
    # 목록 페이지에서 보여줄 필드
    list_display = [
        'name', 
        'rtsp_url', 
        'max_fps', 
        'is_active', 
        'created_at',
        'updated_at'
    ]
    
    # 필터링 가능한 필드
    list_filter = [
        'is_active',
        'max_fps',
        'created_at',
        'updated_at'
    ]
    
    # 검색 가능한 필드
    search_fields = [
        'name',
        'rtsp_url',
        'workspace_name',
        'workflow_id'
    ]
    
    # 편집 가능한 필드 (목록에서 바로 편집)
    list_editable = [
        'is_active',
        'max_fps'
    ]
    
    # 상세 페이지 필드 그룹화
    fieldsets = [
        ('기본 정보', {
            'fields': ['name', 'is_active']
        }),
        ('RTSP 설정', {
            'fields': ['rtsp_url', 'max_fps']
        }),
        ('ROBOFLOW 설정', {
            'fields': ['api_key', 'workspace_name', 'workflow_id'],
            'classes': ['collapse']  # 접을 수 있는 섹션
        }),
        ('시간 정보', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
            'description': '시스템에서 자동으로 관리되는 시간 정보입니다.'
        })
    ]
    
    # 읽기 전용 필드
    readonly_fields = ['created_at', 'updated_at']
    
    # 기본 정렬
    ordering = ['name']
    
    # 페이지당 표시할 항목 수
    list_per_page = 25
    
    # 액션 설정
    actions = ['activate_cameras', 'deactivate_cameras']
    
    def activate_cameras(self, request, queryset):
        """선택된 카메라들을 활성화"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated}개의 카메라가 활성화되었습니다.')
    activate_cameras.short_description = "선택된 카메라 활성화"
    
    def deactivate_cameras(self, request, queryset):
        """선택된 카메라들을 비활성화"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated}개의 카메라가 비활성화되었습니다.')
    deactivate_cameras.short_description = "선택된 카메라 비활성화"
    
    # 새 객체 추가 시 기본값 설정
    def get_changeform_initial_data(self, request):
        return {
            'max_fps': 15,
            'is_active': True,
        }