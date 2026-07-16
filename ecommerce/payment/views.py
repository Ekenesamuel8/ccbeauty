import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from cart.cart import Cart
from payment.models import Order, Payment, RegisterAddress
from payment.services.checkout import (
    AddressOwnershipError,
    CheckoutError,
    CheckoutStateError,
    EmptyCartError,
    InvalidCartItemError,
    InvalidCheckoutTokenError,
    InvalidQuantityError,
    MissingAddressError,
    ProductUnavailableError,
    build_cart_preview,
    checkout_token_is_valid,
    create_checkout_order,
)


logger = logging.getLogger(__name__)
CHECKOUT_TOKEN_SESSION_KEY = "checkout_token"
CHECKOUT_PAYMENT_SESSION_KEY = "checkout_payment_ref"


def _new_checkout_token():
    return secrets.token_urlsafe(32)


@login_required(login_url="login")
@require_GET
def payment_failed(request):
    return render(request, "payment/payment_failed.html")


@login_required(login_url="login")
@require_GET
def payment_success(request):
    return render(request, "payment/payment_success.html")


@login_required(login_url="login")
@require_GET
def checkout(request):
    address_query = RegisterAddress.objects.filter(user=request.user).order_by("id")
    selected_address_id = request.GET.get("address_id")
    if selected_address_id:
        try:
            shipping_address = address_query.filter(pk=selected_address_id).first()
        except (TypeError, ValueError):
            shipping_address = None
    else:
        shipping_address = address_query.first()

    if shipping_address is None:
        messages.error(request, MissingAddressError.user_message)
        return redirect("manage_shipping_address")

    cart = Cart(request)
    try:
        preview = build_cart_preview(cart)
    except CheckoutError as exc:
        messages.error(request, exc.user_message)
        return redirect("cart_summary")

    checkout_token = request.session.get(CHECKOUT_TOKEN_SESSION_KEY)
    if not checkout_token_is_valid(checkout_token):
        checkout_token = _new_checkout_token()
        request.session[CHECKOUT_TOKEN_SESSION_KEY] = checkout_token

    context = {
        "shipping_address": shipping_address,
        "total_cost": preview.total,
        "total_items": preview.total_quantity,
        "checkout_token": checkout_token,
    }
    return render(request, "payment/checkout.html", context=context)


@login_required(login_url="login")
@require_POST
def orders(request):
    checkout_token = request.POST.get("checkout_token", "")
    session_token = request.session.get(CHECKOUT_TOKEN_SESSION_KEY)
    owned_checkout_exists = bool(checkout_token) and Order.objects.filter(
        user=request.user,
        idempotency_key=checkout_token,
    ).exists()

    if checkout_token != session_token and not owned_checkout_exists:
        logger.warning("Invalid checkout token rejected for user_id=%s", request.user.id)
        messages.error(request, InvalidCheckoutTokenError.user_message)
        return redirect("checkout")

    shipping_address = None
    if not owned_checkout_exists:
        address_id = request.POST.get("address_id")
        try:
            shipping_address = RegisterAddress.objects.filter(
                pk=address_id,
                user=request.user,
            ).first()
        except (TypeError, ValueError):
            shipping_address = None

        if shipping_address is None:
            logger.warning("Checkout address rejected for user_id=%s", request.user.id)
            messages.error(request, AddressOwnershipError.user_message)
            return redirect("manage_shipping_address")

    try:
        result = create_checkout_order(
            user=request.user,
            cart=Cart(request),
            shipping_address=shipping_address,
            idempotency_key=checkout_token,
        )
    except (EmptyCartError, InvalidCartItemError, InvalidQuantityError) as exc:
        messages.error(request, exc.user_message)
        return redirect("cart_summary")
    except ProductUnavailableError as exc:
        messages.error(request, exc.user_message)
        return redirect("cart_summary")
    except (MissingAddressError, AddressOwnershipError) as exc:
        messages.error(request, exc.user_message)
        return redirect("manage_shipping_address")
    except (InvalidCheckoutTokenError, CheckoutStateError) as exc:
        messages.error(request, exc.user_message)
        return redirect("checkout")
    except Exception:
        logger.exception("Unexpected checkout failure for user_id=%s", request.user.id)
        messages.error(request, CheckoutError.user_message)
        return redirect("cart_summary")

    if not result.created:
        messages.info(request, "This checkout was already created; payment resumed.")

    request.session[CHECKOUT_PAYMENT_SESSION_KEY] = result.payment.ref
    request.session[CHECKOUT_TOKEN_SESSION_KEY] = _new_checkout_token()
    return redirect("makepayment", ref=result.payment.ref)


@login_required(login_url="login")
@require_GET
def makepayment(request, ref):
    payment = (
        Payment.objects.select_related("order")
        .filter(ref=ref, user=request.user)
        .first()
    )
    if payment is None:
        logger.warning("Payment-page ownership/not-found rejection user_id=%s", request.user.id)
        messages.error(request, "Payment record not found or access was denied.")
        return redirect("checkout")

    order = payment.order
    if order is None or order.user_id != request.user.id:
        logger.warning("Payment-order ownership mismatch user_id=%s", request.user.id)
        messages.error(request, "Payment record not found or access was denied.")
        return redirect("checkout")
    if payment.amount_paid != order.amount_paid:
        logger.error("Payment amount mismatch for payment_id=%s", payment.id)
        messages.error(request, "This payment cannot be initialized safely.")
        return redirect("checkout")
    if order.status != Order.Status.PENDING_PAYMENT:
        messages.error(request, "This order is no longer payable.")
        return redirect("checkout")
    if payment.status not in {
        Payment.Status.INITIALIZED,
        Payment.Status.PENDING,
    }:
        messages.error(request, "This payment attempt is no longer payable.")
        return redirect("checkout")

    context = {
        "total_cost": payment.amount_paid,
        "amount_kobo": payment.amount_value(),
        "email": payment.email,
        "payment": payment,
        "PAYSTACK_PK": settings.PAYSTACK_PUBLIC_KEY,
    }
    return render(request, "payment/makepayment.html", context=context)


@login_required(login_url="login")
@require_GET
def verify_payment(request, ref):
    try:
        payment = Payment.objects.select_related("order").get(
            ref=ref,
            user=request.user,
        )
    except Payment.DoesNotExist:
        logger.warning("Payment verification ownership/not-found rejection")
        messages.warning(request, "Payment record not found or access was denied.")
        return JsonResponse({"error message": "Payment not found"}, status=404)

    if not payment.order_id or payment.order.user_id != request.user.id:
        # Phase 3 will replace this browser-return flow with full verification
        # hardening and webhook processing. Never guess an order association.
        messages.warning(request, "Payment has no valid owned order.")
        return JsonResponse(
            {"error message": "Payment has no valid order"},
            status=409,
        )

    verified = payment.verify_payment()
    if not verified:
        messages.warning(request, "Payment verification failed.")
        return redirect("dashboard")

    # Existing post-verification compatibility behavior is retained for Phase 3.
    # The cart is not touched during checkout creation or payment-page rendering.
    request.session.pop("sess_key", None)
    order_info = {
        "id": payment.order.id,
        "total_cost": payment.order.amount_paid,
    }
    context = {
        "placed_order": order_info,
        "payment": payment,
    }
    return render(request, "payment/payment_success.html", context=context)
