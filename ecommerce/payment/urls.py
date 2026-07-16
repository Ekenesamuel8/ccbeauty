from django.urls import path
from . import views

urlpatterns = [
    path('payment_failed/', views.payment_failed, name='payment_failed'),

    path('payment_success/', views.payment_success, name='payment_success'),

    path('checkout/', views.checkout, name='checkout'),

    path('makepayment/<str:ref>/', views.makepayment, name='makepayment'),

    path('verify_payment/<str:ref>/', views.verify_payment, name='verify_payment'),

    path('orders/', views.orders, name='orders'),

]
