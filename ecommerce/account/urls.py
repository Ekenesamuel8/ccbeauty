from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [

    path('register/', views.register, name='register'), #register page

    path('email_verification/<str:uidb64>/<str:token>', views.email_verification, name='email_verification'), #email verification page

    path('email_verification_success/', views.email_verification_success, name='email_verification_success'), #email verification success page

    path('email_verification_sent/', views.email_verification_sent, name='email_verification_sent'), #email verification sent page

    path('email_verification_failed/', views.email_verification_failed, name='email_verification_failed'), #email verification failed page

    path('login/', views.login, name='login'),

    path('logout/', views.logout, name='logout'),

    path('dashboard/', views.dashboard, name='dashboard'),

    path('profile_account/', views.profile_account, name='profile_account'),

    path('delete_profile/', views.delete_profile, name='delete_profile'),


    #password reset urls
    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='account/password/password_reset.html'), name='password_reset'),

    #password reset done urls   
    path('password_reset_complete/', auth_views.PasswordResetCompleteView.as_view(template_name='account/password/password_reset_done.html'), name='password_reset_complete'),

    #password reset form urls
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='account/password/password_reset_form.html'), name='password_reset_confirm'),

    #password reset sent urls
    path('password_reset_sent/', auth_views.PasswordResetDoneView.as_view(template_name='account/password/password_reset_sent.html'), name='password_reset_done'),
   
    path('manage_shipping_address/', views.manage_shipping_address, name='manage_shipping_address'),

    path('order_history/', views.order_history, name='order_history'),

]