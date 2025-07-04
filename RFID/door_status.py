# door_status.py
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.utils import timezone
from django.apps import apps
import json
import logging

# 로깅 설정
logger = logging.getLogger(__name__)

Room = apps.get_model('RFID', 'Room')

@csrf_exempt
def door_status_update(request):
    """
    아두이노에서 문 상태 업데이트
    POST 요청으로 device_code와 door_status를 받아 Room 테이블 업데이트
    """
    if request.method != 'POST':
        return JsonResponse({
            'status': 'error',
            'message': 'POST 메서드만 허용됩니다.'
        }, status=405)
    
    try:
        data = json.loads(request.body)
        device_code = data.get('device_code')
        door_status = data.get('door_status')  # True=열림, False=닫힘
        
        # 필수 데이터 확인
        if device_code is None or door_status is None:
            return JsonResponse({
                'status': 'error',
                'message': '필수 데이터 누락',
                'detail': 'device_code와 door_status가 필요합니다.'
            }, status=400)
        
        # door_status가 boolean 타입인지 확인
        if not isinstance(door_status, bool):
            return JsonResponse({
                'status': 'error',
                'message': '잘못된 데이터 타입',
                'detail': 'door_status는 boolean 타입이어야 합니다.'
            }, status=400)
        
        # Room 조회
        try:
            room = Room.objects.get(device_id=device_code)
        except Room.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': '방을 찾을 수 없음',
                'detail': f'device_code {device_code}에 해당하는 방이 없습니다.'
            }, status=404)
        
        # 상태 변경 확인
        status_changed = room.door_status != door_status
        
        # Room 상태 업데이트
        room.door_status = door_status
        room.last_door_change = timezone.now()
        room.save()
        
        logger.info(f"Door status updated - Room: {room.name}, Status: {'열림' if door_status else '닫힘'}")
        
        return JsonResponse({
            'status': 'success',
            'message': '문 상태 업데이트 완료',
            'data': {
                'room_name': room.name,
                'device_code': device_code,
                'door_status': door_status,
                'door_status_text': '열림' if door_status else '닫힘',
                'last_door_change': room.last_door_change.isoformat(),
                'status_changed': status_changed
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'status': 'error',
            'message': '잘못된 JSON 형식',
            'detail': '올바른 JSON 형식으로 요청해주세요.'
        }, status=400)
    except Exception as e:
        logger.error(f"Door status update error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': '서버 오류',
            'detail': str(e)
        }, status=500)

@csrf_exempt
def door_status_get(request):
    """
    모든 방의 현재 문 상태 조회 API
    실시간 모니터링용
    """
    if request.method != 'GET':
        return JsonResponse({
            'status': 'error',
            'message': 'GET 메서드만 허용됩니다.'
        }, status=405)
    
    try:
        # 활성화된 방들만 조회
        rooms = Room.objects.filter(is_enabled=True).order_by('name')
        
        room_data = []
        for room in rooms:
            room_data.append({
                'id': room.id,
                'name': room.name,
                'location': room.location,
                'device_id': room.device_id,
                'door_status': room.door_status,
                'door_status_text': '열림' if room.door_status else '닫힘',
                'last_door_change': room.last_door_change.isoformat() if room.last_door_change else None,
                'required_level': room.required_level,
                'is_enabled': room.is_enabled
            })
        
        return JsonResponse({
            'status': 'success',
            'message': '방 상태 조회 완료',
            'data': {
                'rooms': room_data,
                'total_rooms': len(room_data),
                'open_rooms': len([r for r in room_data if r['door_status']]),
                'closed_rooms': len([r for r in room_data if not r['door_status']]),
                'server_time': timezone.now().isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Door status get error: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': '서버 오류',
            'detail': str(e)
        }, status=500)

def door_status_monitor(request):
    """
    문 상태 모니터링 페이지
    실시간으로 모든 방의 상태를 확인할 수 있는 간단한 웹 페이지
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': '로그인이 필요합니다.'}, status=401)
    
    rooms = Room.objects.filter(is_enabled=True).order_by('name')
    
    context = {
        'rooms': rooms,
        'total_rooms': rooms.count(),
        'open_rooms': rooms.filter(door_status=True).count(),
        'closed_rooms': rooms.filter(door_status=False).count(),
    }
    
    from django.shortcuts import render
    return render(request, 'door_status_monitor.html', context)