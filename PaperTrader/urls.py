from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.search_stock, name='search_stock'),
    path('orders/', views.orders, name='orders'),
    path('sell/', views.sell_stock, name='sell_stock'),
    path('reset/', views.reset_portfolio, name='reset_portfolio'),


]
