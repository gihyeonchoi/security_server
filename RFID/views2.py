from django.contrib.auth.views import login_required
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.http import HttpResponseRedirect
from django.contrib import messages
import json
import uuid
from datetime import datetime
from django.utils import timezone
from datetime import timedelta
from django.db import transaction

# from RFID.models import Card
from django.apps import apps
Card = apps.get_model('RFID', 'Card')

rfid_records = []   # RFID 카드 데이터 저장용

def use_card(request):
    """ 카드로 문 열때 인증 관리 """
    return

@csrf_exempt
def card_tag(request):
    """ RFID 태그 데이터 처리 """
    if request.method == 'POST':    # 클라이언트가 카드 데이터 보낼시 응답확인용
        try:
            data = json.loads(request.body)
            rfid_code = data.get('rfid_code')
            if rfid_code:
                page_id = str(uuid.uuid4())     # 새 페이지 이름으로 랜덤값 생성
                current_time = timezone.now()   # 보내진 시간 측정

                record = {
                    'code': rfid_code,
                    'time': current_time,
                    'page_id': page_id,
                    'display_until': current_time + timedelta(minutes=1)  # 1분 후 표시 종료 시간
                }
                rfid_records.append(record)    # 태그 데이터 저장, 추후 한개씩 삭제
                # print(rfid_records)
                # 30분이 지난 레코드 삭제 (실제 데이터 삭제)
                clean_old_records_30min()
                
                return JsonResponse({
                        'status': 'success',
                        'rfid_code': rfid_code,
                        'page_id': page_id
                    })

        except json.JSONDecodeError as e:
            return JsonResponse({'status': 'error', 'message': '잘못된 데이터 형식'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error', 'message': '잘못된 요청 메소드'})

def clean_old_records_30min():
    """30분이 지난 레코드를 실제로 삭제하는 함수"""
    global rfid_records
    current_time = timezone.now()
    thirty_minutes_ago = current_time - timedelta(minutes=30)
    
    # 30분이 지나지 않은 레코드만 유지 (실제 데이터 삭제)
    rfid_records = [record for record in rfid_records if record['time'] > thirty_minutes_ago]

def get_visible_records():
    """1분 이내의 레코드만 반환하는 함수 (화면에 표시할 용도)"""
    current_time = timezone.now()
    
    # 현재 시간이 display_until 보다 작은 레코드만 반환 (표시 시간이 지나지 않은 것들)
    return [record for record in rfid_records if current_time < record.get('display_until', record['time'] + timedelta(minutes=1))]

def view_tag(request):
    """HTML에서 RFID 레코드를 볼 수 있는 페이지"""
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponse("접근 권한이 없습니다.".encode('utf-8'))
    
    # 30분이 지난 레코드 실제 삭제
    clean_old_records_30min()
    
    # 1분 이내의 레코드만 가져오기 (화면에 표시할 용도)
    visible_records = get_visible_records()
    
    # 시간 형식을 보기 좋게 변환
    formatted_records = []
    current_time = timezone.now()
    
    for record in visible_records:
        # 남은 표시 시간 계산 (초 단위)
        display_until = record.get('display_until', record['time'] + timedelta(minutes=1))
        remaining_seconds = max(0, int((display_until - current_time).total_seconds()))
        
        formatted_record = {
            'code': record['code'],
            'time': record['time'].strftime('%Y-%m-%d %H:%M:%S'),
            'page_id': record['page_id'],
            'remaining_seconds': remaining_seconds  # 남은 시간 추가
        }
        formatted_records.append(formatted_record)
    
    # 남은 시간이 많은 순서대로 정렬 (내림차순)
    formatted_records.sort(key=lambda x: x['remaining_seconds'], reverse=True)
    
    context = {
        'records': formatted_records
    }
    return render(request, 'view_tag.html', context)

def get_records_json(request):
    """AJAX 요청을 위한 JSON 형식의 레코드 데이터 제공"""
    # 30분이 지난 레코드 실제 삭제
    clean_old_records_30min()
    
    # 표시 기간이 지나지 않은 레코드만 가져오기
    visible_records = get_visible_records()
    
    # 마지막 체크 시간을 확인 (새 레코드가 있는지 확인용)
    last_check_time_str = request.GET.get('last_check', None)
    has_new_records = False
    newest_time = None
    
    # 시간 형식을 보기 좋게 변환
    formatted_records = []
    current_time = timezone.now()
    
    for record in visible_records:
        # 남은 표시 시간 계산 (초 단위)
        display_until = record.get('display_until', record['time'] + timedelta(minutes=1))
        remaining_seconds = max(0, int((display_until - current_time).total_seconds()))
        
        # 이 레코드가 마지막 체크 이후에 생성되었는지 확인
        if last_check_time_str and record['time'].isoformat() > last_check_time_str:
            has_new_records = True
        
        # 가장 최근 레코드 시간 업데이트
        if newest_time is None or record['time'] > newest_time:
            newest_time = record['time']
        
        formatted_record = {
            'code': record['code'],
            'time': record['time'].strftime('%Y-%m-%d %H:%M:%S'),
            'page_id': record['page_id'],
            'remaining_seconds': remaining_seconds,  # 남은 표시 시간 (초)
            'id': record['page_id'],  # 레코드 식별용 ID
            'created_at': record['time'].isoformat()  # ISO 형식의 생성 시간
        }
        formatted_records.append(formatted_record)
    
    # 남은 시간이 많은 순서대로 정렬 (내림차순)
    formatted_records.sort(key=lambda x: x['remaining_seconds'], reverse=True)
    
    return JsonResponse({
        'records': formatted_records,
        'newest_time': newest_time.isoformat() if newest_time else None,
        'has_new_records': has_new_records,
        'server_time': timezone.now().isoformat()
    })

@login_required
def card_add(request, page_id):
    """ 카드 등록 페이지 """
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponse("접근 권한이 없습니다.".encode('utf-8'))
    global rfid_records
    # print(f"페이지 아이디 : {page_id}")
    # print(f"현재 태그 개수 : {len(rfid_records)} 개")
    # print(f"현재 태그 : {rfid_records}")
    matching_record = None
    who_add = request.user.get_full_name() or request.user.username
    for record in rfid_records:     # 카드 정보 유효한지 검사
        if record.get('page_id') == page_id:
            matching_record = record
            break
    # print(f"카드체크 매칭 레코드 : {matching_record}")
    if not matching_record:
        messages.error(request, '링크가 만료되었거나 존재하지 않습니다.')
        return redirect('view_tag')

    if request.method == 'POST':
        try:
            # 폼 데이터 가져오기
            card_key_value = request.POST.get('card_key_value')
            card_alias = request.POST.get('card_alias')
            card_level = int(request.POST.get('card_level'))
            is_active = request.POST.get('is_active') == 'on'
            
            # 날짜 처리
            valid_from = request.POST.get('valid_from')
            valid_until = request.POST.get('valid_until')
            
            # 문자열을 datetime 객체로 변환
            valid_from = datetime.fromisoformat(valid_from) if valid_from else None
            valid_until = datetime.fromisoformat(valid_until) if valid_until else None

            # 중복 카드 확인
            existing_cards = Card.objects.filter(card_key_value=card_key_value)
            active_cards = existing_cards.filter(is_active=True)
            
            # 이미 활성화된 카드가 있는지 확인
            has_active_card = active_cards.exists()
            
            # 확인 단계를 거쳤는지 확인
            confirm_duplicate = request.POST.get('confirm_duplicate') == 'yes'
            
            if has_active_card and is_active and not confirm_duplicate:
                # 사용자에게 알림 및 선택지 제공
                active_card = active_cards.first()
                context = {
                    'rfid_code': matching_record['code'],
                    'who_add': who_add,
                    'duplicate_card': True,
                    'existing_card': active_card,
                    'form_data': {
                        'card_alias': card_alias,
                        'card_level': card_level,
                        'is_active': is_active,
                        'valid_from': valid_from.isoformat() if valid_from else '',
                        'valid_until': valid_until.isoformat() if valid_until else '',
                    }
                }
                return render(request, 'card_add.html', context)
            
            # 트랜잭션으로 처리하여 데이터 일관성 유지
            with transaction.atomic():
                # 새 카드가 활성화되는 경우 같은 카드키를 가진 다른 카드를 모두 비활성화
                if is_active:
                    existing_cards.update(is_active=False, last_modify_who=who_add)
                
                # 새 카드 생성
                new_card = Card.objects.create(
                    card_key_value=card_key_value,
                    card_alias=card_alias,
                    card_level=card_level,
                    who_add=who_add,
                    is_active=is_active,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    last_modify_who=who_add
                )
            
            # 등록된 카드 정보 지우기
            rfid_records = [record for record in rfid_records if record.get('page_id') != page_id]
            # 기존 카드가 있었는지에 따라 메시지 다르게 표시
            if has_active_card and is_active:
                messages.success(request, f'기존 활성화된 카드를 비활성화하고 새 카드({card_alias})를 등록했습니다.')
            else:
                messages.success(request, f'카드가 성공적으로 등록되었습니다. (카드별칭: {card_alias})')
            
            return HttpResponseRedirect('/RFID/view_tag/')

        except Exception as e:
            messages.error(request, f'카드 등록 중 오류가 발생했습니다: {str(e)}')
            return render(request, 'card_add.html', {
                'rfid_code': matching_record['code'],
                'who_add': who_add
            })

    # card_add form 데이터 처리
    return render(request, 'card_add.html', {
        'rfid_code': matching_record['code'],
        'who_add': who_add})