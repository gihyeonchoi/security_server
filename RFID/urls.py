# urls.py
from django.urls import path
from . import views
from . import views2

urlpatterns = [
    path('', views.tag_test, name='tag_test'),
    path('check_tag/', views.check_tag, name='check_tag'),
    
    path('card_edit/<int:card_id>/', views.card_edit, name='card_edit'),
    # path('card_add/<str:page_id>/', views.card_add, name='card_add'),
    path('test/', views2.card_tag, name='card_add_test'),

    # RFID 레코드 HTML 페이지
    path('rfid_records/', views2.view_records, name='view_records'),
    # RFID 레코드 JSON 데이터 (AJAX용)
    path('get_records_json/', views2.get_records_json, name='get_records_json'),
    path('card_check/<str:page_id>/', views2.card_check, name='card_check'),
]  