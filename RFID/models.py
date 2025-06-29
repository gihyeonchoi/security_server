# models.py
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

class ModuleInfo(models.Model):
    """
    아두이노 모듈 apName 저장
    """
    device_id = models.CharField(
        max_length = 10,
        verbose_name="모듈 고유 코드",
        help_text = "아두이노 내부 Preferences->ap_name"
    )

class Room(models.Model):
    """
    방/출입지점 정보 테이블
    - RFID 리더기가 설치된 각 방의 정보를 관리
    - 각 방의 출입 권한 레벨과 상태를 저장
    """
    name = models.CharField(
        max_length=100, 
        verbose_name="방 이름",
        help_text="예: 회의실A, 서버실, 사무실"
    )
    location = models.CharField(
        max_length=150, 
        verbose_name="방 위치",
        help_text="예: 3층 동쪽, GPS좌표, 상세 주소"
    )
    required_level = models.IntegerField(
        verbose_name="필요 보안 등급",
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        help_text="0=최고 권한, 5=최저 권한"
    )
    device_id = models.CharField(
        max_length=20, 
        unique=True,
        verbose_name="아두이노 기기 ID",
        help_text="각 아두이노 기기의 고유 식별자"
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name="방 사용 가능 여부",
        help_text="False시 모든 출입 차단"
    )
    door_status = models.BooleanField(
        default=False,
        verbose_name="현재 문 상태",
        help_text="True=열림, False=닫힘"
    )
    last_door_change = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name="마지막 문 상태 변경 시간"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="등록일시"
    )
    
    class Meta:
        db_table = 'room_info'
        verbose_name = "방 정보"
        verbose_name_plural = "ROOM : 방 정보 목록"
        indexes = [
            models.Index(fields=['device_id']),
            models.Index(fields=['required_level']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.location})"
    
    def can_access(self, card_level):
        """카드 레벨로 출입 가능 여부 확인"""
        return self.is_enabled and card_level <= self.required_level


class Card(models.Model):
    """
    RFID 카드 정보 테이블
    - 각 RFID 카드의 기본 정보와 권한 레벨을 관리
    - 카드의 활성화 상태와 유효 기간을 추적
    """
    card_key_value = models.CharField(
        max_length=20, 
        # unique=True,
        verbose_name="카드 고유키",
        help_text="RFID 카드의 UID (Hex 형태)"
    )
    card_alias = models.CharField(
        max_length=100,
        verbose_name="카드 별칭",
        help_text="예: 홍길동 카드, 임시카드1"
    )
    card_level = models.IntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        verbose_name="카드 보안 등급",
        help_text="0=최고 권한, 5=최저 권한"
    )
    regist_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="등록일시"
    )
    who_add = models.CharField(
        max_length=100,
        verbose_name="등록자",
        help_text="카드를 등록한 관리자 이름"
    )
    last_modify_date = models.DateTimeField(
        auto_now=True,
        verbose_name="마지막 수정일시"
    )
    last_modify_who = models.CharField(
        max_length=100, 
        blank=True,
        verbose_name="마지막 수정자"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="카드 활성 상태",
        help_text="False시 카드 사용 불가"
    )
    valid_from = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name="유효 시작일"
    )
    valid_until = models.DateTimeField(
        null=True, 
        blank=True,
        verbose_name="유효 종료일"
    )
    
    class Meta:
        db_table = 'card'
        verbose_name = "RFID 카드"
        verbose_name_plural = "Card : RFID 카드 목록"
        indexes = [
            models.Index(fields=['card_key_value']),
            models.Index(fields=['card_level']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.card_alias} ({self.card_key_value})"
    
    def is_valid(self):
        """카드 유효성 검사"""
        if not self.is_active:
            return False
        
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        
        return True
    
    def can_access_room(self, room):
        """특정 방 출입 가능 여부 확인"""
        return self.is_valid() and room.can_access(self.card_level)
    
    def save(self, *args, **kwargs):
        """새 카드 등록 시 나머지 중복 카드들 is_active 모두 비활성화"""
        if self.is_active:
            Card.objects.filter(card_key_value=self.card_key_value).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class CardModifyLog(models.Model):
    """
    카드 정보 수정 로그 테이블
    - 카드 정보 변경 시마다 이력을 기록
    - 보안 감사 및 변경 추적을 위한 테이블
    """
    card = models.ForeignKey(
        Card, 
        on_delete=models.CASCADE,
        verbose_name="수정된 카드",
        related_name='modify_logs'
    )
    card_alias_before = models.CharField(
        max_length=100, 
        blank=True,
        verbose_name="변경 전 카드 별칭"
    )
    card_alias_after = models.CharField(
        max_length=100, 
        blank=True,
        verbose_name="변경 후 카드 별칭"
    )
    card_level_before = models.IntegerField(
        verbose_name="변경 전 보안 등급"
    )
    card_level_after = models.IntegerField(
        verbose_name="변경 후 보안 등급"
    )
    is_active_before = models.BooleanField(
        verbose_name="변경 전 활성 상태"
    )
    is_active_after = models.BooleanField(
        verbose_name="변경 후 활성 상태"
    )
    modify_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="수정일시"
    )
    modify_who = models.CharField(
        max_length=100,
        verbose_name="수정자"
    )
    modify_reason = models.TextField(
        blank=True,
        verbose_name="수정 사유"
    )
    
    class Meta:
        db_table = 'card_modify_log'
        verbose_name = "카드 수정 로그"
        verbose_name_plural = "CardModifyLog : 카드 수정 로그 목록"
        indexes = [
            models.Index(fields=['card', 'modify_date']),
            models.Index(fields=['modify_date']),
        ]
        ordering = ['-modify_date']
    
    def __str__(self):
        return f"{self.card.card_alias} 수정 ({self.modify_date.strftime('%Y-%m-%d %H:%M')})"


class CardUseLog(models.Model):
    """
    카드 사용 로그 테이블
    - 모든 카드 태깅 시도를 기록
    - 출입 허용/거부 여부와 함께 저장
    """
    ACCESS_GRANTED = 'granted'
    ACCESS_DENIED = 'denied'
    ACCESS_ERROR = 'error'
    
    ACCESS_RESULT_CHOICES = [
        (ACCESS_GRANTED, '출입 허용'),
        (ACCESS_DENIED, '출입 거부'),
        (ACCESS_ERROR, '시스템 오류'),
    ]
    
    card = models.ForeignKey(
        Card, 
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="사용된 카드",
        related_name='use_logs',
        help_text="카드 삭제 시에도 로그는 유지"
    )
    room = models.ForeignKey(
        Room, 
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="출입 시도 방",
        related_name='access_logs'
    )
    card_key_backup = models.CharField(
        max_length=20,
        verbose_name="카드키 백업",
        help_text="카드 삭제 시 추적을 위한 백업"
    )
    room_name_backup = models.CharField(
        max_length=100,
        verbose_name="방 이름 백업",
        help_text="방 삭제 시 추적을 위한 백업"
    )
    access_result = models.CharField(
        max_length=10,
        choices=ACCESS_RESULT_CHOICES,
        default=ACCESS_DENIED,
        verbose_name="출입 결과"
    )
    denial_reason = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="거부 사유",
        help_text="출입 거부 시 상세 사유"
    )
    use_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="사용일시"
    )
    server_response_time = models.FloatField(
        null=True,
        blank=True,
        verbose_name="서버 응답 시간(ms)",
        help_text="성능 모니터링용"
    )
    
    class Meta:
        db_table = 'card_use_log'
        verbose_name = "카드 사용 로그"
        verbose_name_plural = "CardUseLog : 카드 사용 로그 목록"
        indexes = [
            models.Index(fields=['card', 'use_date']),
            models.Index(fields=['room', 'use_date']),
            models.Index(fields=['use_date']),
            models.Index(fields=['access_result']),
            models.Index(fields=['card_key_backup']),
        ]
        ordering = ['-use_date']
    
    def __str__(self):
        card_name = self.card.card_alias if self.card else self.card_key_backup
        room_name = self.room.name if self.room else self.room_name_backup
        return f"{card_name} → {room_name} ({self.get_access_result_display()})"
    
    def save(self, *args, **kwargs):
        """저장 시 백업 데이터 자동 설정"""
        if self.card:
            self.card_key_backup = self.card.card_key_value
        if self.room:
            self.room_name_backup = self.room.name
        super().save(*args, **kwargs)