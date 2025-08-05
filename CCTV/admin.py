from django.contrib import admin
from .models import Camera, TargetLabel

class TargetLabelInline(admin.StackedInline):
    model = TargetLabel
    readonly_fields = ('id',)
    extra = 1

@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    """카메라 테이블 하나에서 LABEL 정보도 함께 등록"""
    inlines = [TargetLabelInline]