# urls.py
from django.urls import path
from . import views
from . import views2
from . import card_list
from . import card_modify
from . import card_log
from . import views_room
from . import door_status

urlpatterns = [
    path('', views2.main_page, name='main_page'),
    path('check_tag/', views.check_tag, name='check_tag'),
    # path('card_add/<str:page_id>/', views.card_add, name='card_add'),
    


    
    # RFID 태그 확인 페이지 (관리자 전용)
    path('view_tag/', views2.view_tag, name='view_tag'),
    path('test/', views2.card_tag, name='card_add_test'),   # 클라이언트 -> 서버 tag 데이터 전송 엔드포인트
    # RFID 레코드 JSON 데이터 (AJAX용)
    path('get_records_json/', views2.get_records_json, name='get_records_json'),
    # RFID 저장 페이지
    path('card_add/<str:page_id>/', views2.card_add, name='card_add'),


    # RFID 카드 정보 확인 페이지 (관리자 전용)
    path('card_list/', card_list.card_list, name='card_list'),
    path('api/cards/', card_list.card_list_api, name='card_list_api'),

    # RFID 실제 방에 사용 관련
    path('card_use/', views2.card_use, name='card_use'),


    # RFID 카드 수정 페이지 (관리자 전용)
    path('card_edit/<int:card_id>/', card_modify.card_edit, name='card_edit'),
    # 카드 사용 로그
    path('card_logs/<int:card_id>/', card_log.card_logs, name='card_logs'),
    path('card_logs_export/<int:card_id>/', card_log.card_logs_export, name='card_logs_export'),

    # Room 관리
    path('room_list/', views_room.room_list, name='room_list'),
    path('room_add/', views_room.room_add, name='room_add'),
    path('room_edit/<int:room_id>/', views_room.room_edit, name='room_edit'),
    path('room_delete/<int:room_id>/', views_room.room_delete, name='room_delete'),
    
    # Module 관리
    path('module_list/', views_room.module_list, name='module_list'),
    
    # Door Status 관리 (새로 추가)
    path('door_status_update/', door_status.door_status_update, name='door_status_update'),
    path('door_status_get/', door_status.door_status_get, name='door_status_get'),
    path('door_status_monitor/', door_status.door_status_monitor, name='door_status_monitor'),

    # Ajax
    path('check_device_availability/', views_room.check_device_availability, name='check_device_availability'),
]  