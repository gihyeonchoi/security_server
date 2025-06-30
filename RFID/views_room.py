# views_room.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.apps import apps

Room = apps.get_model('RFID', 'Room')
ModuleInfo = apps.get_model('RFID', 'ModuleInfo')
CardUseLog = apps.get_model('RFID', 'CardUseLog')

@login_required
def room_list(request):
    """Room 목록 조회"""
    if not request.user.is_superuser:
        return HttpResponse("접근 권한이 없습니다.", status=403)
    
    # 검색 필터
    search = request.GET.get('search', '')
    
    rooms = Room.objects.all()
    
    if search:
        rooms = rooms.filter(
            Q(name__icontains=search) |
            Q(location__icontains=search) |
            Q(device_id__icontains=search)
        )
    
    # 각 방의 사용 통계 추가
    rooms = rooms.annotate(
        access_count=Count('access_logs'),
        granted_count=Count('access_logs', filter=Q(access_logs__access_result='granted'))
    )
    
    # 페이지네이션
    paginator = Paginator(rooms.order_by('name'), 20)
    page = request.GET.get('page', 1)
    rooms_page = paginator.get_page(page)
    
    context = {
        'rooms': rooms_page,
        'search': search,
        'total_count': paginator.count,
        'active_count': Room.objects.filter(is_enabled=True).count(),
    }
    
    return render(request, 'room_list.html', context)

@login_required
def room_add(request):
    """Room 등록"""
    if not request.user.is_superuser:
        messages.error(request, "접근 권한이 없습니다.")
        return redirect('room_list')
    
    # 모든 모듈 목록과 사용 상태 확인
    all_modules = ModuleInfo.objects.all()
    used_device_ids = Room.objects.values_list('device_id', flat=True)
    
    # 각 모듈에 사용 상태 추가
    modules_with_status = []
    for module in all_modules:
        room = Room.objects.filter(device_id=module.device_id).first()
        modules_with_status.append({
            'device_id': module.device_id,
            'is_used': module.device_id in used_device_ids,
            'room': room
        })
    
    if request.method == 'POST':
        try:
            device_id = request.POST.get('device_id')
            
            # ModuleInfo에 등록된 기기인지 확인
            if not ModuleInfo.objects.filter(device_id=device_id).exists():
                messages.error(request, "등록되지 않은 아두이노 기기입니다. ModuleInfo에 먼저 등록하세요.")
                return redirect('room_add')
            
            # 이미 사용 중인지 확인
            if Room.objects.filter(device_id=device_id).exists():
                messages.error(request, "이미 다른 방에서 사용 중인 기기입니다.")
                return redirect('room_add')
            
            # Room 생성
            room = Room.objects.create(
                name=request.POST.get('name'),
                location=request.POST.get('location'),
                required_level=int(request.POST.get('required_level')),
                device_id=device_id,
                is_enabled=request.POST.get('is_enabled') == 'on'
            )
            
            messages.success(request, f"방 '{room.name}'이(가) 등록되었습니다.")
            return redirect('room_list')
            
        except Exception as e:
            messages.error(request, f"등록 중 오류 발생: {str(e)}")
    
    available_count = len([m for m in modules_with_status if not m['is_used']])
    
    context = {
        'modules_with_status': modules_with_status,
        'total_modules': len(modules_with_status),
        'used_modules': len(modules_with_status) - available_count,
        'available_count': available_count,
    }
    return render(request, 'room_add.html', context)

@login_required
def room_edit(request, room_id):
    """Room 정보 수정"""
    if not request.user.is_superuser:
        messages.error(request, "접근 권한이 없습니다.")
        return redirect('room_list')

    room = get_object_or_404(Room, id=room_id)

    if request.method == 'POST':
        try:
            room.name = request.POST.get('name')
            room.location = request.POST.get('location')
            room.required_level = int(request.POST.get('required_level'))
            room.is_enabled = request.POST.get('is_enabled') == 'on'
            # device_id는 변경 불가

            room.save()
            messages.success(request, "방 정보가 수정되었습니다.")
            return redirect('room_list')

        except Exception as e:
            messages.error(request, f"수정 중 오류 발생: {str(e)}")

    # ✅ 여기서 출입 허용 기록 수 계산
    granted_count = room.access_logs.filter(access_result='granted').count()

    context = {
        'room': room,
        'granted_count': granted_count,
    }
    return render(request, 'room_edit.html', context)

@login_required
def room_delete(request, room_id):
    """Room 삭제"""
    if not request.user.is_superuser:
        messages.error(request, "접근 권한이 없습니다.")
        return redirect('room_list')
    
    room = get_object_or_404(Room, id=room_id)
    
    if request.method == 'POST':
        try:
            # 삭제 전 정보 저장
            room_name = room.name
            device_id = room.device_id
            
            # 관련 로그 수 확인
            access_logs_count = room.access_logs.count()
            # door_logs_count = room.door_logs.count()
            
            # 삭제 확인
            if request.POST.get('confirm_delete') == 'yes':
                # Room 삭제 (CASCADE로 door_logs는 자동 삭제)
                # access_logs는 SET_NULL로 유지됨
                room.delete()
                
                messages.success(request, f"방 '{room_name}'이(가) 삭제되었습니다. (기기 ID: {device_id})")
                return redirect('room_list')
            else:
                messages.error(request, "삭제가 취소되었습니다.")
                return redirect('room_edit', room_id=room_id)
                
        except Exception as e:
            messages.error(request, f"삭제 중 오류 발생: {str(e)}")
            return redirect('room_edit', room_id=room_id)
    
    # GET 요청 시 확인 페이지 표시
    context = {
        'room': room,
        'access_logs_count': room.access_logs.count(),
        # 'door_logs_count': room.door_logs.count(),
        'recent_access': room.access_logs.order_by('-use_date').first(),
    }
    return render(request, 'room_delete_confirm.html', context)


@login_required
def module_list(request):
    """ModuleInfo 목록 및 관리"""
    if not request.user.is_superuser:
        return HttpResponse("접근 권한이 없습니다.", status=403)
    
    if request.method == 'POST':
        # 새 모듈 추가
        device_id = request.POST.get('device_id', '').strip().upper()
        
        # 서버 측 검증: 8자리 대문자 영어와 숫자
        import re
        if not re.match(r'^[A-Z0-9]{8}$', device_id):
            messages.error(request, "기기 ID는 8자리 대문자 영어와 숫자 조합이어야 합니다.")
            return redirect('module_list')
        
        if ModuleInfo.objects.filter(device_id=device_id).exists():
            messages.error(request, "이미 등록된 기기 ID입니다.")
        else:
            ModuleInfo.objects.create(device_id=device_id)
            messages.success(request, f"모듈 '{device_id}'이(가) 등록되었습니다.")
        return redirect('module_list')
    
    # 모듈 삭제
    if request.GET.get('delete'):
        module_id = request.GET.get('delete')
        module = get_object_or_404(ModuleInfo, id=module_id)
        
        # 사용 중인지 확인
        if Room.objects.filter(device_id=module.device_id).exists():
            messages.error(request, "이 모듈은 방에서 사용 중이므로 삭제할 수 없습니다.")
        else:
            module.delete()
            messages.success(request, "모듈이 삭제되었습니다.")
        
        return redirect('module_list')
    
    modules = ModuleInfo.objects.all()
    
    # 각 모듈의 사용 상태 확인
    for module in modules:
        module.room = Room.objects.filter(device_id=module.device_id).first()
    
    context = {
        'modules': modules,
    }
    return render(request, 'module_list.html', context)

@login_required
def check_device_availability(request):
    """Ajax: device_id 사용 가능 여부 확인"""
    if not request.user.is_superuser:
        return JsonResponse({'error': '권한 없음'}, status=403)
    
    device_id = request.GET.get('device_id', '')
    
    if not device_id:
        return JsonResponse({'available': False, 'message': '기기 ID를 입력하세요.'})
    
    # ModuleInfo에 등록되어 있는지 확인
    if not ModuleInfo.objects.filter(device_id=device_id).exists():
        return JsonResponse({
            'available': False, 
            'registered': False,
            'message': '등록되지 않은 기기입니다. ModuleInfo에 먼저 등록하세요.'
        })
    
    # 이미 Room에서 사용 중인지 확인
    room = Room.objects.filter(device_id=device_id).first()
    if room:
        return JsonResponse({
            'available': False,
            'registered': True,
            'used': True,
            'message': f"'{room.name}'에서 사용 중입니다."
        })
    
    return JsonResponse({
        'available': True,
        'registered': True,
        'used': False,
        'message': '사용 가능한 기기입니다.'
    })