from django import forms
from django.core.exceptions import ValidationError
from .models import Location, Floor, CameraPosition
from CCTV.models import Camera


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ['name', 'address', 'description', 'base_floor_altitude', 'floor_height_interval']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '위치명을 입력하세요'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '주소를 입력하세요 (선택사항)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '설명을 입력하세요 (선택사항)'}),
            'base_floor_altitude': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.1', 
                'placeholder': '예: 100.0 (미터)'
            }),
            'floor_height_interval': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.1', 
                'placeholder': '예: 1.5 (미터)'
            })
        }
    
    def clean(self):
        cleaned_data = super().clean()
        base_altitude = cleaned_data.get('base_floor_altitude')
        floor_interval = cleaned_data.get('floor_height_interval')
        
        # 둘 다 입력되거나 둘 다 비어있어야 함
        if (base_altitude is not None) != (floor_interval is not None):
            raise ValidationError("1층 기준 고도와 층간 간격은 함께 입력하거나 함께 비워두어야 합니다.")
        
        if floor_interval is not None and floor_interval <= 0:
            raise ValidationError({'floor_height_interval': '층간 간격은 0보다 큰 값이어야 합니다.'})
        
        return cleaned_data


class FloorForm(forms.ModelForm):
    class Meta:
        model = Floor
        fields = ['location', 'name', 'floor_number', 'map_image', 
                  'top_left_lat', 'top_left_lon', 'bottom_right_lat', 'bottom_right_lon']
        widgets = {
            'location': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: 1층, 2층, 지하1층'}),
            'floor_number': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '예: 1, 2, -1'}),
            'map_image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'top_left_lat': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': '좌상단 위도'}),
            'top_left_lon': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': '좌상단 경도'}),
            'bottom_right_lat': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': '우하단 위도'}),
            'bottom_right_lon': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any', 'placeholder': '우하단 경도'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        location = cleaned_data.get('location')
        floor_number = cleaned_data.get('floor_number')
        
        if location and floor_number is not None:
            # 같은 위치에 같은 층수가 이미 있는지 확인
            if Floor.objects.filter(location=location, floor_number=floor_number).exclude(pk=self.instance.pk).exists():
                raise ValidationError(f"{location.name}에 {floor_number}층이 이미 존재합니다.")
        
        return cleaned_data


class CameraPositionForm(forms.ModelForm):
    class Meta:
        model = CameraPosition
        fields = ['camera', 'floor', 'x_position', 'y_position', 'is_active']
        widgets = {
            'camera': forms.Select(attrs={'class': 'form-control'}),
            'floor': forms.Select(attrs={'class': 'form-control'}),
            'x_position': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.1', 
                'min': '0', 
                'max': '100',
                'placeholder': '0-100 (퍼센트)'
            }),
            'y_position': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.1', 
                'min': '0', 
                'max': '100',
                'placeholder': '0-100 (퍼센트)'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 이미 위치가 설정된 카메라는 제외 (현재 편집중인 것은 제외)
        exclude_cameras = CameraPosition.objects.exclude(pk=self.instance.pk).values_list('camera', flat=True)
        self.fields['camera'].queryset = Camera.objects.exclude(id__in=exclude_cameras)
    
    def clean(self):
        cleaned_data = super().clean()
        x_pos = cleaned_data.get('x_position')
        y_pos = cleaned_data.get('y_position')
        
        if x_pos is not None and (x_pos < 0 or x_pos > 100):
            raise ValidationError({'x_position': 'X 좌표는 0-100 사이의 값이어야 합니다.'})
        
        if y_pos is not None and (y_pos < 0 or y_pos > 100):
            raise ValidationError({'y_position': 'Y 좌표는 0-100 사이의 값이어야 합니다.'})
        
        return cleaned_data


class CameraPositionUpdateForm(forms.Form):
    """드래그 앤 드롭용 간단한 위치 업데이트 폼"""
    x_position = forms.FloatField(min_value=0, max_value=100)
    y_position = forms.FloatField(min_value=0, max_value=100)