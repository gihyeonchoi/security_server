
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.views import login_required
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import Camera, TargetLabel, DetectionLog
from .utils import camera_streamer, ai_detection_system
import json
import time
import queue
from datetime import timedelta

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
            
            # 카메라 추가 후 스트리밍 및 탐지 시스템 업데이트
            try:
                camera_streamer.refresh_cameras()
                ai_detection_system.refresh_cameras()
                print(f"✅ 카메라 '{camera.name}' 추가 후 시스템 업데이트 완료")
            except Exception as e:
                print(f"⚠️ 카메라 추가 후 시스템 업데이트 오류: {e}")
            
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
        
        # 카메라 수정 후 스트리밍 및 탐지 시스템 업데이트
        try:
            camera_streamer.refresh_cameras()
            ai_detection_system.refresh_cameras()
            print(f"✅ 카메라 '{camera.name}' 수정 후 시스템 업데이트 완료")
        except Exception as e:
            print(f"⚠️ 카메라 수정 후 시스템 업데이트 오류: {e}")
        
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
        
        # 카메라 삭제 후 스트리밍 및 탐지 시스템 업데이트
        try:
            camera_streamer.refresh_cameras()
            ai_detection_system.refresh_cameras()
            print(f"✅ 카메라 '{camera_name}' 삭제 후 시스템 업데이트 완료")
        except Exception as e:
            print(f"⚠️ 카메라 삭제 후 시스템 업데이트 오류: {e}")
        
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
            
            # 타겟 라벨 추가 후 AI 탐지 시스템 업데이트
            try:
                ai_detection_system.refresh_cameras()
                print(f"✅ 타겟 라벨 '{target_label.display_name}' 추가 후 AI 탐지 업데이트 완료")
            except Exception as e:
                print(f"⚠️ 타겟 라벨 추가 후 AI 탐지 업데이트 오류: {e}")
            
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
        
        # 타겟 라벨 수정 후 AI 탐지 시스템 업데이트
        try:
            ai_detection_system.refresh_cameras()
            print(f"✅ 타겟 라벨 '{target_label.display_name}' 수정 후 AI 탐지 업데이트 완료")
        except Exception as e:
            print(f"⚠️ 타겟 라벨 수정 후 AI 탐지 업데이트 오류: {e}")
        
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
        
        # 타겟 라벨 삭제 후 AI 탐지 시스템 업데이트
        try:
            ai_detection_system.refresh_cameras()
            print(f"✅ 타겟 라벨 '{display_name}' 삭제 후 AI 탐지 업데이트 완료")
        except Exception as e:
            print(f"⚠️ 타겟 라벨 삭제 후 AI 탐지 업데이트 오류: {e}")
        
        return redirect('cctv:index')
    
    return render(request, 'cctv/target_label_confirm_delete.html', {'target_label': target_label})

def detection_alerts_stream(request):
    """SSE를 위한 실시간 알림 스트림 - 수정된 버전"""
    def event_stream():
        # SSE 연결 시작
        yield "data: {\"type\": \"connected\", \"message\": \"알림 스트림 연결됨\"}\n\n"
        
        # 처음 연결 시 최근 1분 이내의 알림만 전송
        recent_time = timezone.now() - timedelta(minutes=1)
        recent_logs = DetectionLog.objects.filter(
            has_alert=True,
            detected_at__gte=recent_time
        ).order_by('-detected_at')[:3]  # 최대 3개만
        
        print(f"📨 SSE 초기 알림: {recent_logs.count()}개")
        
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
                'confidence': log.confidence,
                'is_recent': True
            }
            yield f"data: {json.dumps(alert_data, ensure_ascii=False)}\n\n"
        
        # 실시간 알림 대기
        last_heartbeat = time.time()
        empty_count = 0
        
        while True:
            try:
                current_time = time.time()
                
                # 전역 알림 큐에서 새 알림 확인
                alert_queue = ai_detection_system.get_alert_queue()
                
                if alert_queue:
                    try:
                        # 0.5초 타임아웃으로 큐에서 가져오기
                        alert = alert_queue.get(timeout=0.5)
                        
                        print(f"🔔 SSE 새 알림 전송: {alert.get('detected_object', 'Unknown')}")
                        
                        # 새로운 알림 전송
                        alert['is_new'] = True
                        yield f"data: {json.dumps(alert, ensure_ascii=False)}\n\n"
                        
                        empty_count = 0
                        
                    except queue.Empty:
                        empty_count += 1
                        
                        # 디버그: 큐가 비어있는 경우
                        if empty_count % 20 == 0:  # 10초마다 한 번
                            print(f"💤 SSE 큐 비어있음 (체크 횟수: {empty_count})")
                else:
                    print("⚠️ SSE: 알림 큐가 None입니다")
                    time.sleep(1)
                    continue
                
                # 30초마다 하트비트 전송
                if current_time - last_heartbeat > 30:
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
                    last_heartbeat = current_time
                    print(f"💓 SSE 하트비트 전송")
                
                # CPU 사용량 감소를 위한 짧은 대기
                time.sleep(0.1)
                
            except GeneratorExit:
                print("🛑 SSE 연결 종료 (클라이언트 연결 끊김)")
                break
            except Exception as e:
                print(f"❌ SSE 스트림 오류: {e}")
                yield f"data: {{\"type\": \"error\", \"message\": \"스트림 오류: {str(e)}\"}}\n\n"
                time.sleep(1)
    
    response = StreamingHttpResponse(
        event_stream(), 
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['X-Accel-Buffering'] = 'no'  # nginx 버퍼링 비활성화
    # response['Connection'] = 'keep-alive' # (WSGI에서 hop-by-hop 헤더는 허용되지 않음)
    
    return response

# 알림 초기화 API 추가
@login_required
@require_http_methods(["POST"])
def clear_alert_history(request):
    """알림 히스토리 초기화"""
    request.session['last_alert_time'] = timezone.now().isoformat()
    request.session.save()
    return JsonResponse({'status': 'success', 'message': '알림 히스토리가 초기화되었습니다.'})

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

@require_http_methods(["GET"])
def background_streaming_status(request):
    """백그라운드 스트리밍 상태 확인"""
    try:
        from .models import Camera
        cameras = Camera.objects.all()  # 실시간 DB 조회
        
        status_data = []
        for camera in cameras:
            is_background = camera_streamer.is_background_streaming(camera.rtsp_url)
            camera_status = camera_streamer.get_camera_status(camera.rtsp_url)
            
            status_data.append({
                'id': camera.id,
                'name': camera.name,
                'location': camera.location,
                'rtsp_url': camera.rtsp_url,
                'background_streaming': is_background,
                'is_connected': camera_status.get('is_connected', False),
                'avg_fps': camera_status.get('avg_fps', 0),
                'stream_count': camera_status.get('stream_count', 0)
            })
        
        return JsonResponse({
            'success': True,
            'cameras': status_data,
            'total_cameras': len(cameras),
            'background_active': sum(1 for data in status_data if data['background_streaming'])
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)