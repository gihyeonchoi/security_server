
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.views import login_required
from django.http import StreamingHttpResponse, JsonResponse
from django.contrib import messages
from .models import Camera, TargetLabel
from .utils import camera_streamer

@login_required
def camera_stream(request, camera_id):
    """개별 카메라 스트림 엔드포인트"""
    camera = get_object_or_404(Camera, id=camera_id)
    
    response = StreamingHttpResponse(
        camera_streamer.generate_frames(camera.rtsp_url),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response

@login_required
def camera_status_api(request):
    """카메라 상태 API 엔드포인트"""
    cameras = Camera.objects.all()
    camera_status = {}
    
    for camera in cameras:
        status = camera_streamer.get_camera_status(camera.rtsp_url)
        camera_status[str(camera.id)] = status
    
    return JsonResponse({
        'status': 'success',
        'cameras': camera_status
    })

@login_required
def multi_camera_view(request):
    """다중 카메라 모니터링 뷰"""
    cameras = Camera.objects.all()
    return render(request, 'cctv/multi_camera.html', {'cameras': cameras})

@login_required
def index(request):
    """CCTV 메인 페이지 - 카메라 목록 및 관리"""
    cameras = Camera.objects.all().prefetch_related('target_labels')
    return render(request, 'cctv/index.html', {'cameras': cameras})

@login_required
def camera_create(request):
    """카메라 생성"""
    if request.method == 'POST':
        name = request.POST.get('name')
        location = request.POST.get('location')
        rtsp_url = request.POST.get('rtsp_url')
        
        if name and location and rtsp_url:
            camera = Camera.objects.create(
                name=name,
                location=location,
                rtsp_url=rtsp_url
            )
            messages.success(request, f'카메라 "{camera.name}"이 성공적으로 추가되었습니다.')
            return redirect('cctv:index')
        else:
            messages.error(request, '모든 필드를 입력해주세요.')
    
    return render(request, 'cctv/camera_form.html', {'action': 'create'})

@login_required
def camera_edit(request, camera_id):
    """카메라 수정"""
    camera = get_object_or_404(Camera, id=camera_id)
    
    if request.method == 'POST':
        camera.name = request.POST.get('name', camera.name)
        camera.location = request.POST.get('location', camera.location)
        camera.rtsp_url = request.POST.get('rtsp_url', camera.rtsp_url)
        camera.save()
        
        messages.success(request, f'카메라 "{camera.name}"이 성공적으로 수정되었습니다.')
        return redirect('cctv:index')
    
    return render(request, 'cctv/camera_form.html', {
        'camera': camera,
        'action': 'edit'
    })

@login_required
def camera_delete(request, camera_id):
    """카메라 삭제"""
    camera = get_object_or_404(Camera, id=camera_id)
    
    if request.method == 'POST':
        camera_name = camera.name
        camera.delete()
        messages.success(request, f'카메라 "{camera_name}"이 성공적으로 삭제되었습니다.')
        return redirect('cctv:index')
    
    return render(request, 'cctv/camera_confirm_delete.html', {'camera': camera})

@login_required
def target_label_create(request, camera_id):
    """타겟 라벨 생성"""
    camera = get_object_or_404(Camera, id=camera_id)
    
    if request.method == 'POST':
        display_name = request.POST.get('display_name')
        label_name = request.POST.get('label_name')
        has_alert = request.POST.get('has_alert') == 'on'
        
        if display_name and label_name:
            target_label = TargetLabel.objects.create(
                camera=camera,
                display_name=display_name,
                label_name=label_name,
                has_alert=has_alert
            )
            messages.success(request, f'타겟 라벨 "{target_label.display_name}"이 성공적으로 추가되었습니다.')
            return redirect('cctv:index')
        else:
            messages.error(request, '표시 이름과 라벨 이름을 입력해주세요.')
    
    return render(request, 'cctv/target_label_form.html', {
        'camera': camera,
        'action': 'create'
    })

@login_required
def target_label_edit(request, label_id):
    """타겟 라벨 수정"""
    target_label = get_object_or_404(TargetLabel, id=label_id)
    
    if request.method == 'POST':
        target_label.display_name = request.POST.get('display_name', target_label.display_name)
        target_label.label_name = request.POST.get('label_name', target_label.label_name)
        target_label.has_alert = request.POST.get('has_alert') == 'on'
        target_label.save()
        
        messages.success(request, f'타겟 라벨 "{target_label.display_name}"이 성공적으로 수정되었습니다.')
        return redirect('cctv:index')
    
    return render(request, 'cctv/target_label_form.html', {
        'target_label': target_label,
        'camera': target_label.camera,
        'action': 'edit'
    })

@login_required
def target_label_delete(request, label_id):
    """타겟 라벨 삭제"""
    target_label = get_object_or_404(TargetLabel, id=label_id)
    
    if request.method == 'POST':
        display_name = target_label.display_name
        target_label.delete()
        messages.success(request, f'타겟 라벨 "{display_name}"이 성공적으로 삭제되었습니다.')
        return redirect('cctv:index')
    
    return render(request, 'cctv/target_label_confirm_delete.html', {'target_label': target_label})