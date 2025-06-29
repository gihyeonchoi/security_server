# views_card_edit.py
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from datetime import datetime
from django.apps import apps

Card = apps.get_model('RFID', 'Card')
CardModifyLog = apps.get_model('RFID', 'CardModifyLog')

@login_required
def card_edit(request, card_id):
    """카드 정보 수정"""
    if not request.user.is_superuser:
        messages.error(request, "접근 권한이 없습니다.")
        return redirect('card_list')
    
    card = get_object_or_404(Card, id=card_id)
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # 수정 전 값 저장
                old_alias = card.card_alias
                old_level = card.card_level
                old_active = card.is_active
                
                # 새 값 가져오기
                card.card_alias = request.POST.get('card_alias')
                card.card_level = int(request.POST.get('card_level'))
                new_is_active = request.POST.get('is_active') == 'on'
                
                # 날짜 처리
                valid_from = request.POST.get('valid_from')
                valid_until = request.POST.get('valid_until')
                card.valid_from = datetime.fromisoformat(valid_from) if valid_from else None
                card.valid_until = datetime.fromisoformat(valid_until) if valid_until else None
                
                # 수정자 정보
                modifier = request.user.get_full_name() or request.user.username
                card.last_modify_who = modifier
                
                # 활성화 시 동일 카드키 비활성화
                if new_is_active and not card.is_active:
                    Card.objects.filter(
                        card_key_value=card.card_key_value
                    ).exclude(id=card.id).update(is_active=False)
                
                card.is_active = new_is_active
                card.save()
                
                # 수정 로그 생성
                CardModifyLog.objects.create(
                    card=card,
                    card_alias_before=old_alias,
                    card_alias_after=card.card_alias,
                    card_level_before=old_level,
                    card_level_after=card.card_level,
                    is_active_before=old_active,
                    is_active_after=card.is_active,
                    modify_who=modifier,
                    modify_reason=request.POST.get('modify_reason', '')
                )
                
                messages.success(request, "카드 정보가 수정되었습니다.")
                return redirect('card_list')
                
        except Exception as e:
            messages.error(request, f"수정 중 오류 발생: {str(e)}")
    
    # 수정 이력 조회
    modify_logs = card.modify_logs.order_by('-modify_date')[:10]
    
    context = {
        'card': card,
        'modify_logs': modify_logs,
    }
    return render(request, 'card_edit.html', context)