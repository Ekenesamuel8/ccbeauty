from django.urls import path
from . import views

urlpatterns = [
    path('payment_failed/<str:ref>/', views.payment_failed, name='payment_failed'),

    path('payment_success/<str:ref>/', views.payment_success, name='payment_success'),

    path('payment_pending/<str:ref>/', views.payment_pending, name='payment_pending'),

    path('checkout/', views.checkout, name='checkout'),

    path('makepayment/<str:ref>/', views.makepayment, name='makepayment'),

    path('verify_payment/<str:ref>/', views.verify_payment, name='verify_payment'),

    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),

    path('orders/', views.orders, name='orders'),

]
