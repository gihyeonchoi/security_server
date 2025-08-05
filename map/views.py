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

# Flask의 전역 변수처럼, 서버가 실행되는 동안 위치를 메모리에 저장합니다.
# (주의: 서버가 재시작되면 정보는 초기화됩니다.)
latest_location = {
    "latitude": None,
    "longitude": None,
    "altitude": None
}

def map_view(request):
    return render(request, 'map/map.html')

# 외부 장치에서 CSRF 토큰 없이 POST 요청을 보내므로, 이 View에 대해서만 CSRF 보호를 비활성화합니다.
@csrf_exempt
def location_api(request):
    global latest_location

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            altitude = data.get('altitude')

            if latitude is not None and longitude is not None and altitude is not None:
                latest_location = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude": altitude
                }
                print(f"📡 POST 수신: {latest_location}")
                return JsonResponse({"status": "ok", "message": "Location received"})
            else:
                return JsonResponse({"status": "error", "message": "Missing location data"}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
    
    elif request.method == 'GET':
        # print(f"🛰️ GET 요청: 저장된 위치 전송 - {latest_location}")
        return JsonResponse(latest_location)
    
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