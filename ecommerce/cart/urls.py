from django.urls import path
from . import views

urlpatterns = [
    path('', views.cart_summary, name='cart_summary'), #cart page
    path('add_cart/', views.add_cart, name='add_cart'), #add to cart
    path('remove_cart/', views.remove_cart, name='remove_cart'), #remove from cart
    path('update_cart/', views.update_cart, name='update_cart'), #remove item
]