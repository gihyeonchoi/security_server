
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.views import login_required
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.contrib import messages
from .models import Camera, TargetLabel, DetectionLog
from .utils import camera_streamer, ai_detection_system
import json
import time
import queue

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

def detection_alerts_stream(request):
    """SSE를 위한 실시간 알림 스트림"""
    def event_stream():
        # SSE 헤더 설정
        yield "data: {\"type\": \"connected\", \"message\": \"알림 스트림 연결됨\"}\n\n"
        
        # 최근 10개 탐지 로그 전송
        recent_logs = DetectionLog.objects.filter(has_alert=True)[:10]
        for log in recent_logs:
            alert_data = {
                'type': 'detection_alert',
                'id': log.id,
                'camera_name': log.camera_name,
                'camera_location': log.camera_location,
                'detected_object': log.detected_object,
                'object_count': log.object_count,
                'detected_at': log.detected_at.isoformat(),
                'has_screenshot': bool(log.screenshot_path),
                'confidence': log.confidence
            }
            yield f"data: {json.dumps(alert_data)}\n\n"
        
        # 실시간 알림 대기
        while True:
            try:
                # AI 탐지 시스템의 알림 큐에서 새 알림 확인
                if hasattr(ai_detection_system, 'alert_queue'):
                    try:
                        alert = ai_detection_system.alert_queue.get_nowait()
                        yield f"data: {json.dumps(alert)}\n\n"
                    except queue.Empty:
                        pass
                
                # 하트비트 전송 (30초마다)
                yield "data: {\"type\": \"heartbeat\"}\n\n"
                time.sleep(30)
                
            except Exception as e:
                yield f"data: {{\"type\": \"error\", \"message\": \"스트림 오류: {str(e)}\"}}\n\n"
                break
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # nginx 버퍼링 비활성화
    return response

@login_required
def detection_logs_api(request):
    """탐지 로그 API (페이징 지원)"""
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    alert_only = request.GET.get('alert_only', 'false').lower() == 'true'
    
    logs = DetectionLog.objects.all()
    if alert_only:
        logs = logs.filter(has_alert=True)
    
    total_count = logs.count()
    start = (page - 1) * page_size
    end = start + page_size
    logs = logs[start:end]
    
    logs_data = []
    for log in logs:
        logs_data.append({
            'id': log.id,
            'camera_name': log.camera_name,
            'camera_location': log.camera_location,
            'detected_object': log.detected_object,
            'object_count': log.object_count,
            'confidence': log.confidence,
            'has_alert': log.has_alert,
            'has_screenshot': log.screenshot_exists,
            'detected_at': log.detected_at.isoformat()
        })
    
    return JsonResponse({
        'status': 'success',
        'logs': logs_data,
        'total_count': total_count,
        'page': page,
        'page_size': page_size,
        'has_next': end < total_count
    })

@login_required
def start_detection(request):
    """AI 탐지 시작"""
    if request.method == 'POST':
        try:
            camera_id = request.POST.get('camera_id')
            if camera_id:
                camera = get_object_or_404(Camera, id=camera_id)
                ai_detection_system.start_detection_for_camera(camera)
                messages.success(request, f'카메라 "{camera.name}"의 AI 탐지가 시작되었습니다.')
            else:
                ai_detection_system.start_all_detections()
                messages.success(request, '모든 카메라의 AI 탐지가 시작되었습니다.')
        except Exception as e:
            messages.error(request, f'AI 탐지 시작 실패: {str(e)}')
    
    return redirect('cctv:index')

@login_required
def stop_detection(request):
    """AI 탐지 중지"""
    if request.method == 'POST':
        try:
            camera_id = request.POST.get('camera_id')
            if camera_id:
                ai_detection_system.stop_detection_for_camera(int(camera_id))
                camera = get_object_or_404(Camera, id=camera_id)
                messages.success(request, f'카메라 "{camera.name}"의 AI 탐지가 중지되었습니다.')
            else:
                ai_detection_system.stop_all_detections()
                messages.success(request, '모든 카메라의 AI 탐지가 중지되었습니다.')
        except Exception as e:
            messages.error(request, f'AI 탐지 중지 실패: {str(e)}')
    
    return redirect('cctv:index')