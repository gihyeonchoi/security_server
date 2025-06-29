# views_card_logs.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.apps import apps
from datetime import datetime, timedelta

Card = apps.get_model('RFID', 'Card')
CardUseLog = apps.get_model('RFID', 'CardUseLog')
Room = apps.get_model('RFID', 'Room')

@login_required
def card_logs(request, card_id):
    """특정 카드의 사용 로그 조회"""
    if not request.user.is_superuser:
        return HttpResponse("접근 권한이 없습니다.", status=403)
    
    card = get_object_or_404(Card, id=card_id)
    
    # 필터 파라미터
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    result_filter = request.GET.get('result', '')
    room_filter = request.GET.get('room', '')
    
    # 기본 쿼리셋
    logs = CardUseLog.objects.filter(card=card)
    
    # 날짜 필터
    if date_from:
        logs = logs.filter(use_date__gte=datetime.fromisoformat(date_from))
    if date_to:
        logs = logs.filter(use_date__lte=datetime.fromisoformat(date_to))
    
    # 결과 필터
    if result_filter:
        logs = logs.filter(access_result=result_filter)
    
    # 방 필터
    if room_filter:
        logs = logs.filter(room_id=room_filter)
    
    # 통계 계산
    total_logs = logs.count()
    granted_count = logs.filter(access_result=CardUseLog.ACCESS_GRANTED).count()
    denied_count = logs.filter(access_result=CardUseLog.ACCESS_DENIED).count()
    
    # 방별 사용 통계
    room_stats = logs.values('room__name').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    # 페이지네이션
    paginator = Paginator(logs.order_by('-use_date'), 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)
    
    # 사용 가능한 방 목록
    rooms = Room.objects.filter(is_enabled=True).order_by('name')
    
    context = {
        'card': card,
        'logs': logs_page,
        'total_logs': total_logs,
        'granted_count': granted_count,
        'denied_count': denied_count,
        'room_stats': room_stats,
        'rooms': rooms,
        'date_from': date_from,
        'date_to': date_to,
        'result_filter': result_filter,
        'room_filter': room_filter,
    }
    
    return render(request, 'card_logs.html', context)

@login_required
def card_logs_export(request, card_id):
    """카드 사용 로그 CSV 내보내기"""
    if not request.user.is_superuser:
        return HttpResponse("접근 권한이 없습니다.", status=403)
    
    card = get_object_or_404(Card, id=card_id)
    logs = CardUseLog.objects.filter(card=card).order_by('-use_date')
    
    # CSV 생성
    import csv
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="card_logs_{card.card_key_value}_{datetime.now().strftime("%Y%m%d")}.csv"'
    
    # BOM 추가 (Excel 한글 호환)
    response.write('\ufeff')
    
    writer = csv.writer(response)
    writer.writerow(['사용일시', '방 이름', '출입 결과', '거부 사유', '응답시간(ms)'])
    
    for log in logs[:1000]:  # 최대 1000건
        writer.writerow([
            log.use_date.strftime('%Y-%m-%d %H:%M:%S'),
            log.room.name if log.room else log.room_name_backup,
            log.get_access_result_display(),
            log.denial_reason or '-',
            f"{log.server_response_time:.2f}" if log.server_response_time else '-'
        ])
    
    return response