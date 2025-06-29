from django.contrib import admin
from .models import Room, Card, CardModifyLog, CardUseLog, ModuleInfo

# Register your models here.
admin.site.register(Room)
admin.site.register(Card)
admin.site.register(CardModifyLog)
admin.site.register(CardUseLog)
admin.site.register(ModuleInfo)