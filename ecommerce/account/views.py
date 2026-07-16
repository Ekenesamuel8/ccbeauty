import logging
from smtplib import SMTPException

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django_ratelimit.decorators import ratelimit
from axes.decorators import axes_dispatch

from payment.form import AddressForm
from payment.models import Order, RegisterAddress

from .form import (
    DeleteAccountForm,
    LoginForm,
    RegisterForm,
    ResendVerificationForm,
    UpdateUserForm,
    UserProfileForm,
)
from .signals import repair_missing_profile
from .token import user_tokenizer_generate


logger = logging.getLogger(__name__)
User = get_user_model()


def _send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = user_tokenizer_generate.make_token(user)
    verification_url = request.build_absolute_uri(
        reverse("email_verification", kwargs={"uidb64": uid, "token": token})
    )
    message = render_to_string(
        "account/registration/email_verification.html",
        {"user": user, "verification_url": verification_url},
    )
    user.email_user(subject="Verify your CCbeauty account", message=message)


@require_http_methods(["GET", "POST"])
def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.is_active = False
                user.save()
        except IntegrityError:
            logger.warning("Registration rejected by a uniqueness constraint")
            form.add_error("email", "An account with these details already exists.")
        else:
            try:
                _send_verification_email(request, user)
            except (SMTPException, OSError):
                logger.exception("Registration verification email failed user_id=%s", user.id)
                messages.warning(
                    request,
                    "Your inactive account was created, but email delivery failed. "
                    "Use resend verification to try again.",
                )
            return redirect("email_verification_sent")
    return render(request, "account/registration/register.html", {"form": form})


@require_GET
def email_verification(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
        logger.warning("Invalid verification user identifier")
        return redirect("email_verification_failed")

    if user.is_active:
        messages.info(request, "This account is already verified. You can log in.")
        return redirect("login")
    if not user_tokenizer_generate.check_token(user, token):
        logger.warning("Invalid or expired verification token user_id=%s", user.id)
        return redirect("email_verification_failed")

    user.is_active = True
    user.save(update_fields=("is_active",))
    repair_missing_profile(user)
    login(request, user, backend="account.auth_backend.EmailOrUsernameModelBackend")
    messages.success(request, "Your email has been verified.")
    return redirect("manage_shipping_address")


@ratelimit(key="post:email", rate="3/h", method="POST", block=True)
@require_http_methods(["GET", "POST"])
def resend_verification(request):
    form = ResendVerificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email__iexact=form.cleaned_data["email"]).first()
        if user and not user.is_active:
            try:
                _send_verification_email(request, user)
            except (SMTPException, OSError):
                logger.exception("Resend verification email failed user_id=%s", user.id)
        logger.info("Verification resend request processed")
        return redirect("email_verification_sent")
    return render(request, "account/registration/resend_verification.html", {"form": form})


@require_GET
def email_verification_success(request):
    return render(request, "account/registration/email_verification_success.html")


@require_GET
def email_verification_sent(request):
    return render(request, "account/registration/email_verification_sent.html")


@require_GET
def email_verification_failed(request):
    return render(request, "account/registration/email_verification_failed.html")


@ratelimit(key="post:username", rate="6/m", method="POST", block=True, group="login")
@axes_dispatch
@require_http_methods(["GET", "POST"])
def login_view(request):
    form = LoginForm(request=request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "You are now logged in.")
        return redirect("store")
    if request.method == "POST":
        messages.error(request, "Invalid username/email or password.")
    return render(request, "account/login.html", {"form": form})


def rate_limit_exceeded(request, exception):
    messages.error(request, "Too many attempts. Please try again later.")
    return render(request, "account/rate_limit_exceeded.html", status=403)


@login_required(login_url="login")
@require_POST
def logout(request):
    cart = request.session.get("sess_key")
    auth_logout(request)
    if isinstance(cart, dict):
        request.session["sess_key"] = cart
    messages.success(request, "You are now logged out.")
    return redirect("store")


@login_required(login_url="login")
@require_GET
def dashboard(request):
    profile = repair_missing_profile(request.user)
    default_address = request.user.shipping_addresses.filter(is_default=True).first()
    return render(
        request,
        "account/dashboard.html",
        {
            "user_details": default_address,
            "address": default_address.address1 if default_address else None,
            "profile_picture": profile,
        },
    )


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def profile_account(request):
    profile = repair_missing_profile(request.user)
    user_form = UpdateUserForm(instance=request.user)
    user_picture = UserProfileForm(instance=profile)
    if request.method == "POST" and "update_user" in request.POST:
        user_form = UpdateUserForm(request.POST, instance=request.user)
        if user_form.is_valid():
            try:
                user_form.save()
            except IntegrityError:
                logger.warning("Profile update rejected by uniqueness constraint")
                user_form.add_error("email", "This email is already in use.")
            else:
                messages.success(request, "Profile details updated.")
                return redirect("dashboard")
    elif request.method == "POST" and "update_profile" in request.POST:
        user_picture = UserProfileForm(request.POST, request.FILES, instance=profile)
        if user_picture.is_valid():
            user_picture.save()
            messages.success(request, "Profile picture updated.")
            return redirect("profile_account")
        logger.warning("Profile image validation failed user_id=%s", request.user.id)
    return render(
        request,
        "account/profile_account.html",
        {"user_form": user_form, "user_picture": user_picture},
    )


@login_required(login_url="login")
@require_POST
def delete_profile(request):
    form = DeleteAccountForm(request.POST, user=request.user)
    if form.is_valid():
        user = request.user
        user_id = user.id
        auth_logout(request)
        user.delete()
        logger.info("Password-confirmed account deletion completed user_id=%s", user_id)
        messages.success(request, "Your account was deleted.")
        return redirect("store")
    logger.warning("Password-confirmed account deletion rejected user_id=%s", request.user.id)
    return render(request, "account/delete_profile.html", {"form": form})


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def manage_shipping_address(request):
    address = request.user.shipping_addresses.filter(is_default=True).first()
    if address is None:
        address = request.user.shipping_addresses.first()
    if request.method == "POST":
        return _save_address(request, address)
    return render(
        request,
        "account/manage_shipping_address.html",
        {"form": AddressForm(instance=address), "addresses": request.user.shipping_addresses.all()},
    )


def _save_address(request, address=None):
    form = AddressForm(request.POST, instance=address)
    if form.is_valid():
        saved = form.save(commit=False)
        saved.user = request.user
        saved.save()
        messages.success(request, "Shipping address saved.")
        return redirect("manage_shipping_address")
    return render(
        request,
        "account/manage_shipping_address.html",
        {"form": form, "address": address, "addresses": request.user.shipping_addresses.all()},
    )


def _owned_address_or_404(request, address_id):
    address = RegisterAddress.objects.filter(pk=address_id, user=request.user).first()
    if address is None:
        logger.warning(
            "Unauthorized or missing address access user_id=%s address_id=%s",
            request.user.id,
            address_id,
        )
        raise Http404
    return address


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def address_create(request):
    if request.method == "POST":
        return _save_address(request)
    return render(request, "account/manage_shipping_address.html", {"form": AddressForm(), "addresses": request.user.shipping_addresses.all()})


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def address_edit(request, address_id):
    address = _owned_address_or_404(request, address_id)
    if request.method == "POST":
        return _save_address(request, address)
    return render(request, "account/manage_shipping_address.html", {"form": AddressForm(instance=address), "address": address, "addresses": request.user.shipping_addresses.all()})


@login_required(login_url="login")
@require_POST
def address_delete(request, address_id):
    address = _owned_address_or_404(request, address_id)
    was_default = address.is_default
    address.delete()
    if was_default:
        replacement = request.user.shipping_addresses.order_by("id").first()
        if replacement:
            replacement.is_default = True
            replacement.save()
    messages.success(request, "Shipping address deleted.")
    return redirect("manage_shipping_address")


@login_required(login_url="login")
@require_POST
def address_set_default(request, address_id):
    address = _owned_address_or_404(request, address_id)
    address.is_default = True
    address.save()
    messages.success(request, "Default shipping address updated.")
    return redirect("manage_shipping_address")


@login_required(login_url="login")
@require_GET
def order_history(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("orderitem_set")
    return render(request, "account/order_history.html", {"orders": orders})


@login_required(login_url="login")
@require_GET
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("orderitem_set", "payments"),
        pk=order_id,
        user=request.user,
    )
    payment = order.payments.order_by("-date_paid").first()
    return render(request, "account/order_detail.html", {"order": order, "payment": payment})
