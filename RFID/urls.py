# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.tag_test, name='tag_test'),
    path('check_tag/', views.check_tag, name='check_tag'),
    path('card_add/<str:page_id>/', views.card_add, name='card_add'),
    path('card_edit/<int:card_id>/', views.card_edit, name='card_edit'),
]