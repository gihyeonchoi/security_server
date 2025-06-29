# 전체 카드 정보 확인 페이지

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.apps import apps

Card = apps.get_model('RFID', 'Card')
CardUseLog = apps.get_model('RFID', 'CardUseLog')

@login_required
def card_list(request):
    """RFID 카드 전체 목록 조회"""
    if not request.user.is_superuser:
        return HttpResponse("접근 권한이 없습니다.", status=403)
    
    # 검색 및 필터링
    search = request.GET.get('search', '')
    filter_active = request.GET.get('active', '')
    filter_level = request.GET.get('level', '')
    sort_by = request.GET.get('sort', '-regist_date')
    
    # 기본 쿼리셋
    cards = Card.objects.all()
    
    # 검색 필터
    if search:
        cards = cards.filter(
            Q(card_key_value__icontains=search) |
            Q(card_alias__icontains=search) |
            Q(who_add__icontains=search)
        )
    
    # 활성 상태 필터
    if filter_active:
        cards = cards.filter(is_active=(filter_active == 'true'))
    
    # 보안 등급 필터
    if filter_level:
        cards = cards.filter(card_level=int(filter_level))
    
    # 정렬
    cards = cards.order_by(sort_by)
    
    # 각 카드의 최근 사용 정보 추가
    cards = cards.annotate(
        use_count=Count('use_logs'),
    ).prefetch_related('use_logs')
    
    # 페이지네이션
    paginator = Paginator(cards, 20)
    page = request.GET.get('page', 1)
    cards_page = paginator.get_page(page)
    
    # 각 카드의 추가 정보 계산
    for card in cards_page:
        # 최근 사용 로그
        last_use = card.use_logs.order_by('-use_date').first()
        card.last_use_date = last_use.use_date if last_use else None
        card.last_use_result = last_use.get_access_result_display() if last_use else None
        
        # 유효성 상태
        card.validity_status = '유효' if card.is_valid() else '만료/비활성'
    
    context = {
        'cards': cards_page,
        'search': search,
        'filter_active': filter_active,
        'filter_level': filter_level,
        'sort_by': sort_by,
        'total_count': paginator.count,
        'active_count': Card.objects.filter(is_active=True).count(),
    }
    
    return render(request, 'card_list.html', context)

@login_required
def card_list_api(request):
    """RFID 카드 목록 API (JSON)"""
    if not request.user.is_superuser:
        return JsonResponse({'error': '권한 없음'}, status=403)
    
    # 필터 파라미터
    active_only = request.GET.get('active_only', 'false') == 'true'
    level = request.GET.get('level')
    limit = int(request.GET.get('limit', 100))
    offset = int(request.GET.get('offset', 0))
    
    # 쿼리 생성
    cards = Card.objects.all()
    
    if active_only:
        cards = cards.filter(is_active=True)
    
    if level:
        cards = cards.filter(card_level=int(level))
    
    # 전체 개수
    total = cards.count()
    
    # 페이지네이션 적용
    cards = cards[offset:offset+limit]
    
    # 직렬화
    data = []
    for card in cards:
        data.append({
            'id': card.id,
            'card_key': card.card_key_value,
            'alias': card.card_alias,
            'level': card.card_level,
            'is_active': card.is_active,
            'is_valid': card.is_valid(),
            'registered_at': card.regist_date.isoformat(),
            'registered_by': card.who_add,
            'last_modified': card.last_modify_date.isoformat() if card.last_modify_date else None,
            'valid_from': card.valid_from.isoformat() if card.valid_from else None,
            'valid_until': card.valid_until.isoformat() if card.valid_until else None,
        })
    
    return JsonResponse({
        'total': total,
        'offset': offset,
        'limit': limit,
        'data': data
    })