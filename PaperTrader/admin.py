from django.contrib import admin
from .models import Stock, Holding, Portfolio

admin.site.register(Stock)
admin.site.register(Holding)
admin.site.register(Portfolio)
