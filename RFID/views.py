# 카드 중복 처리 기능이 추가된 views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from .models import Card, CardModifyLog
import json
from datetime import timedelta
from collections import deque
import uuid

# RFID 데이터를 저장할 구조
rfid_records = deque(maxlen=100)
temporary_pages = {}

def tag_test(request):
    """RFID 태그 테스트 페이지"""
    # 최근 1분 이내의 태그만 표시
    one_minute_ago = timezone.now() - timedelta(minutes=1)
    recent_tags = []
    
    for record in rfid_records:
        if record['time'] > one_minute_ago:
            recent_tags.append({
                'code': record['code'], 
                'time': record['time'], 
                'page_id': record['page_id']
            })
    
    return render(request, 'tag_test.html', {'recent_tags': recent_tags})

@csrf_exempt
def check_tag(request):
    """RFID 태그 데이터 처리"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            rfid_code = data.get('rfid_code')
            
            if rfid_code:
                page_id = str(uuid.uuid4())
                current_time = timezone.now()
                
                record = {
                    'code': rfid_code,
                    'time': current_time,
                    'page_id': page_id
                }
                
                rfid_records.appendleft(record)
                temporary_pages[page_id] = {
                    'rfid_code': rfid_code,
                    'created_at': current_time
                }
                
                return JsonResponse({
                    'status': 'success',
                    'rfid_code': rfid_code,
                    'page_id': page_id
                })
                
        except json.JSONDecodeError as e:
            return JsonResponse({'status': 'error', 'message': '잘못된 데이터 형식'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    # GET 요청 처리
    one_minute_ago = timezone.now() - timedelta(minutes=1)
    recent_tags = []
    
    for record in rfid_records:
        if record['time'] > one_minute_ago:
            recent_tags.append({
                'code': record['code'], 
                'time': record['time'].strftime('%Y-%m-%d %H:%M:%S'), 
                'page_id': record['page_id']
            })
    
    return JsonResponse({'tags': recent_tags})

@login_required
def card_add(request, page_id):
    """카드 등록 페이지 (중복 처리 포함)"""
    page_data = temporary_pages.get(page_id)
    
    if not page_data:
        messages.error(request, '링크가 만료되었거나 존재하지 않습니다.')
        return redirect('tag_test')
    
    # 이미 등록된 태그인지 확인
    if page_data.get('card_registered'):
        messages.info(request, '이미 등록 완료된 RFID 태그입니다.')
        return redirect('tag_test')
    
    rfid_code = page_data['rfid_code']
    
    # 기존 카드 확인
    existing_card = Card.objects.filter(card_key_value=rfid_code).first()
    action = request.GET.get('action')
    
    # 중복 카드가 있고 action이 지정되지 않은 경우 선택 페이지로
    if existing_card and not action:
        return render(request, 'card_choice.html', {
            'rfid_code': rfid_code,
            'created_at': page_data['created_at'],
            'existing_card': existing_card,
            'page_id': page_id
        })
    
    if request.method == 'POST':
        try:
            who_add = request.user.get_full_name() or request.user.username
            
            card_data = {
                'card_key_value': rfid_code,
                'card_alias': request.POST.get('card_alias'),
                'card_level': int(request.POST.get('card_level')),
                'who_add': who_add,
                'is_active': request.POST.get('is_active') == 'true',
            }
        
            # 선택적 필드 처리
            valid_from = request.POST.get('valid_from')
            valid_until = request.POST.get('valid_until')
            
            if valid_from:
                card_data['valid_from'] = parse_datetime(valid_from)
            if valid_until:
                card_data['valid_until'] = parse_datetime(valid_until)
            
            # action이 'add_new'가 아닌 경우 중복 확인
            if action != 'add_new':
                current_existing_card = Card.objects.filter(card_key_value=rfid_code).first()
                if current_existing_card:
                    messages.error(request, f'이미 등록된 RFID 코드입니다: {rfid_code} (카드명: {current_existing_card.card_alias})')
                    context = {
                        'rfid_code': rfid_code,
                        'created_at': page_data['created_at'],
                        'user': request.user,
                        'action': action,
                        'existing_card': None
                    }
                    return render(request, 'card_add.html', context)
            
            # 새 카드 추가 시 기존 카드 비활성화 (action이 'add_new'인 경우에만)
            if action == 'add_new' and existing_card:
                # 기존 카드 수정 로그 기록
                CardModifyLog.objects.create(
                    card=existing_card,
                    card_alias_before=existing_card.card_alias,
                    card_alias_after=existing_card.card_alias,
                    card_level_before=existing_card.card_level,
                    card_level_after=existing_card.card_level,
                    is_active_before=existing_card.is_active,
                    is_active_after=False,
                    modify_who=who_add,
                    modify_reason=f"새 카드 등록으로 인한 자동 비활성화 (새 카드: {card_data['card_alias']})"
                )
                
                # 기존 카드 비활성화
                existing_card.is_active = False
                existing_card.last_modify_who = who_add
                existing_card.save()
                
                messages.info(request, f'기존 카드 "{existing_card.card_alias}"가 비활성화되었습니다.')
            
            # 새 카드 생성
            card = Card.objects.create(**card_data)
            
            # 등록 완료 표시 (임시 페이지는 유지하되 등록 완료 표시)
            temporary_pages[page_id]['card_registered'] = True
            temporary_pages[page_id]['registered_card_id'] = card.id
            
            # rfid_records에서도 해당 태그 제거 (UI에서 사라지도록)
            global rfid_records
            rfid_records = deque([
                record for record in rfid_records 
                if record['page_id'] != page_id
            ], maxlen=100)
            
            if action == 'add_new':
                messages.success(request, f'새 카드 "{card.card_alias}"가 성공적으로 등록되었습니다. (기존 카드 대체)')
            else:
                messages.success(request, f'카드 "{card.card_alias}"가 성공적으로 등록되었습니다.')
            
            return redirect('tag_test')
            
        except Exception as e:
            messages.error(request, f'카드 등록 중 오류: {str(e)}')
    
    # GET 요청 처리
    context = {
        'rfid_code': rfid_code,
        'created_at': page_data['created_at'],
        'user': request.user,
        'action': action,
        'existing_card': existing_card if action == 'add_new' else None
    }
    
    return render(request, 'card_add.html', context)

@login_required 
def card_edit(request, card_id):
    """카드 수정 페이지 (임시 - 테스트 페이지로 리다이렉트)"""
    # 현재는 구현하지 않으므로 테스트 페이지로 리다이렉트
    messages.info(request, '카드 수정 기능은 아직 구현되지 않았습니다.')
    return redirect('tag_test')