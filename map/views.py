# map/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods

from CCTV.models import Camera
from .models import Location, Floor, CameraPosition
from .forms import LocationForm, FloorForm, CameraPositionForm, CameraPositionUpdateForm
import json
from datetime import datetime, timedelta
from django.utils import timezone

# 다중 사용자 위치 정보를 메모리에 저장
# {device_id: {"latitude": float, "longitude": float, "altitude": float, "last_update": datetime, "calculated_floor": int}}
user_locations = {}

# 5초 타임아웃으로 비활성 사용자 정리
def cleanup_inactive_users():
    global user_locations
    current_time = timezone.now()
    timeout_threshold = current_time - timedelta(seconds=5)
    
    # 5초 이상 신호가 없는 사용자들 제거
    inactive_users = [
        device_id for device_id, data in user_locations.items()
        if data['last_update'] < timeout_threshold
    ]
    
    for device_id in inactive_users:
        del user_locations[device_id]
        print(f"⏰ 타임아웃: {device_id} 사용자 제거")

@csrf_exempt
def location_api(request):
    global user_locations
    
    # 비활성 사용자 정리
    cleanup_inactive_users()

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            device_id = data.get('device_id')
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            altitude = data.get('altitude')
            location_id = data.get('location_id')  # 어떤 위치인지 지정

            if not device_id:
                return JsonResponse({"status": "error", "message": "device_id is required"}, status=400)

            if latitude is not None and longitude is not None and altitude is not None:
                # 층수 계산을 위해 Location 정보 가져오기
                calculated_floor = None
                if location_id:
                    try:
                        location = Location.objects.get(id=location_id)
                        calculated_floor = location.calculate_floor_from_altitude(altitude)
                    except Location.DoesNotExist:
                        pass

                user_locations[device_id] = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude": altitude,
                    "calculated_floor": calculated_floor,
                    "location_id": location_id,
                    "last_update": timezone.now()
                }
                
                print(f"📡 POST 수신 [{device_id}]: 위도={latitude}, 경도={longitude}, 고도={altitude}, 층={calculated_floor}")
                return JsonResponse({
                    "status": "ok", 
                    "message": "Location received",
                    "calculated_floor": calculated_floor,
                    "active_users": len(user_locations)
                })
            else:
                return JsonResponse({"status": "error", "message": "Missing location data (latitude, longitude, altitude required)"}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
    
    elif request.method == 'GET':
        # 모든 활성 사용자 위치 정보 반환
        location_id = request.GET.get('location_id')
        
        # 특정 location에 대한 사용자들만 필터링
        filtered_locations = {}
        if location_id:
            filtered_locations = {
                device_id: data for device_id, data in user_locations.items()
                if data.get('location_id') == int(location_id)
            }
        else:
            filtered_locations = user_locations
            
        print(f"🛰️ GET 요청: {len(filtered_locations)}명의 활성 사용자 정보 전송")
        return JsonResponse({
                "user_locations": filtered_locations,
                "total_users": len(filtered_locations)
        })
    
@login_required    
def map_view(request):
    """동적 지도 보기 - 데이터베이스에서 위치, 층, 카메라 정보를 가져옴"""
    # 기본 위치 선택 (첫 번째 위치 또는 요청 파라미터로 지정)
    location_id = request.GET.get('location')
    if location_id:
        location = get_object_or_404(Location, id=location_id)
    else:
        location = Location.objects.first()
    
    if not location:
        # 위치가 없으면 빈 지도 표시
        context = {
            'location': None,
            'floors': [],
            'locations': Location.objects.all(),
            'error': '등록된 위치가 없습니다. 관리자에서 위치를 추가해주세요.'
        }
        return render(request, 'map/map.html', context)
    
    # 해당 위치의 층들과 카메라 위치 정보 가져오기
    floors = Floor.objects.filter(location=location).prefetch_related(
        'camera_positions__camera'
    ).order_by('floor_number')
    
    # 전체 위치 목록 (드롭다운용)
    locations = Location.objects.all()
    
    context = {
        'location': location,
        'floors': floors,
        'locations': locations,
    }
    
    return render(request, 'map/map.html', context)


# ==================== CRUD Views ====================

@method_decorator(login_required, name='dispatch')
class LocationListView(ListView):
    model = Location
    template_name = 'map/location_list.html'
    context_object_name = 'locations'
    paginate_by = 10


@method_decorator(login_required, name='dispatch')
class LocationCreateView(CreateView):
    model = Location
    form_class = LocationForm
    template_name = 'map/location_form.html'
    success_url = reverse_lazy('map:location_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"위치 '{form.instance.name}'이 생성되었습니다.")
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class LocationUpdateView(UpdateView):
    model = Location
    form_class = LocationForm
    template_name = 'map/location_form.html'
    success_url = reverse_lazy('map:location_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"위치 '{form.instance.name}'이 수정되었습니다.")
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class LocationDeleteView(DeleteView):
    model = Location
    template_name = 'map/location_confirm_delete.html'
    success_url = reverse_lazy('map:location_list')
    
    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f"위치 '{obj.name}'이 삭제되었습니다.")
        return super().delete(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class FloorListView(ListView):
    model = Floor
    template_name = 'map/floor_list.html'
    context_object_name = 'floors'
    paginate_by = 10
    
    def get_queryset(self):
        return Floor.objects.select_related('location').order_by('location', 'floor_number')


@method_decorator(login_required, name='dispatch')
class FloorCreateView(CreateView):
    model = Floor
    form_class = FloorForm
    template_name = 'map/floor_form.html'
    success_url = reverse_lazy('map:floor_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"층 '{form.instance}'이 생성되었습니다.")
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class FloorUpdateView(UpdateView):
    model = Floor
    form_class = FloorForm
    template_name = 'map/floor_form.html'
    success_url = reverse_lazy('map:floor_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"층 '{form.instance}'이 수정되었습니다.")
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class FloorDeleteView(DeleteView):
    model = Floor
    template_name = 'map/floor_confirm_delete.html'
    success_url = reverse_lazy('map:floor_list')
    
    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f"층 '{obj}'이 삭제되었습니다.")
        return super().delete(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class CameraPositionListView(ListView):
    model = CameraPosition
    template_name = 'map/camera_position_list.html'
    context_object_name = 'positions'
    paginate_by = 20
    
    def get_queryset(self):
        return CameraPosition.objects.select_related(
            'camera', 'floor', 'floor__location'
        ).order_by('floor__location', 'floor__floor_number', 'camera__name')


@method_decorator(login_required, name='dispatch')
class CameraPositionCreateView(CreateView):
    model = CameraPosition
    form_class = CameraPositionForm
    template_name = 'map/camera_position_form.html'
    success_url = reverse_lazy('map:camera_position_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"카메라 위치 '{form.instance}'가 생성되었습니다.")
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class CameraPositionUpdateView(UpdateView):
    model = CameraPosition
    form_class = CameraPositionForm
    template_name = 'map/camera_position_form.html'
    success_url = reverse_lazy('map:camera_position_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"카메라 위치 '{form.instance}'가 수정되었습니다.")
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class CameraPositionDeleteView(DeleteView):
    model = CameraPosition
    template_name = 'map/camera_position_confirm_delete.html'
    success_url = reverse_lazy('map:camera_position_list')
    
    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f"카메라 위치 '{obj}'가 삭제되었습니다.")
        return super().delete(request, *args, **kwargs)


# ==================== Management Views ====================

@login_required
def camera_position_manager(request, floor_id):
    """드래그 앤 드롭으로 카메라 위치 관리"""
    floor = get_object_or_404(Floor, id=floor_id)
    positions = CameraPosition.objects.filter(floor=floor, is_active=True).select_related('camera')
    available_cameras = Camera.objects.exclude(
        id__in=CameraPosition.objects.values_list('camera_id', flat=True)
    )
    
    context = {
        'floor': floor,
        'positions': positions,
        'available_cameras': available_cameras,
    }
    
    return render(request, 'map/camera_position_manager.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def update_camera_position(request, position_id):
    """드래그 앤 드롭으로 카메라 위치 업데이트 (AJAX)"""
    position = get_object_or_404(CameraPosition, id=position_id)
    
    try:
        data = json.loads(request.body)
        form = CameraPositionUpdateForm(data)
        
        if form.is_valid():
            position.x_position = form.cleaned_data['x_position']
            position.y_position = form.cleaned_data['y_position']
            position.save()
            
            return JsonResponse({
                'status': 'success',
                'message': f"{position.camera.name} 위치가 업데이트되었습니다.",
                'position': {
                    'x': position.x_position,
                    'y': position.y_position
                }
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': f"입력 데이터가 올바르지 않습니다: {form.errors}"
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': 'JSON 데이터 파싱 오류'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'오류가 발생했습니다: {str(e)}'
        }, status=500)