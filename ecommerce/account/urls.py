from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .form import PrivatePasswordResetForm


urlpatterns = [
    path("register/", views.register, name="register"),
    path(
        "email_verification/<str:uidb64>/<str:token>/",
        views.email_verification,
        name="email_verification",
    ),
    path("resend_verification/", views.resend_verification, name="resend_verification"),
    path("email_verification_success/", views.email_verification_success, name="email_verification_success"),
    path("email_verification_sent/", views.email_verification_sent, name="email_verification_sent"),
    path("email_verification_failed/", views.email_verification_failed, name="email_verification_failed"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile_account/", views.profile_account, name="profile_account"),
    path("delete_profile/", views.delete_profile, name="delete_profile"),
    path(
        "password_reset/",
        auth_views.PasswordResetView.as_view(
            template_name="account/password/password_reset.html",
            form_class=PrivatePasswordResetForm,
            success_url=reverse_lazy("password_reset_done"),
            email_template_name="account/password/password_reset_email.txt",
        ),
        name="password_reset",
    ),
    path(
        "password_reset_sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="account/password/password_reset_sent.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="account/password/password_reset_form.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password_reset_complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="account/password/password_reset_done.html"
        ),
        name="password_reset_complete",
    ),
    path("manage_shipping_address/", views.manage_shipping_address, name="manage_shipping_address"),
    path("addresses/new/", views.address_create, name="address_create"),
    path("addresses/<int:address_id>/edit/", views.address_edit, name="address_edit"),
    path("addresses/<int:address_id>/delete/", views.address_delete, name="address_delete"),
    path("addresses/<int:address_id>/default/", views.address_set_default, name="address_set_default"),
    path("order_history/", views.order_history, name="order_history"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
]

handler403 = "account.views.rate_limit_exceeded"
