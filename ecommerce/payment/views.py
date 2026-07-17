import logging
import secrets
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

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
    InsufficientStockError,
    MissingAddressError,
    ProductUnavailableError,
    build_cart_preview,
    checkout_token_is_valid,
    create_checkout_order,
)
from payment.services.paystack import (
    PaystackError,
    verify_transaction,
    webhook_signature_is_valid,
)
from payment.services.payment_processing import (
    PaymentProcessingError,
    PaymentNotFoundError,
    process_verified_payment,
    reconcile_paid_order_cart,
)


logger = logging.getLogger(__name__)
CHECKOUT_TOKEN_SESSION_KEY = "checkout_token"
CHECKOUT_PAYMENT_SESSION_KEY = "checkout_payment_ref"


def _new_checkout_token():
    return secrets.token_urlsafe(32)


def _owned_payment(request, ref):
    return (
        Payment.objects.select_related("order")
        .filter(ref=ref, user=request.user, order__user=request.user)
        .first()
    )


@login_required(login_url="login")
@require_GET
def payment_success(request, ref):
    payment = _owned_payment(request, ref)
    if payment is None:
        messages.error(request, "Payment record not found or access was denied.")
        return redirect("checkout")
    if (
        payment.status != Payment.Status.VERIFIED
        or payment.order.status not in {Order.Status.PAID, Order.Status.PAID_STOCK_ISSUE}
    ):
        return redirect("payment_pending", ref=payment.ref)
    return render(
        request,
        "payment/payment_success.html",
        {"payment": payment, "order": payment.order},
    )


@login_required(login_url="login")
@require_GET
def payment_pending(request, ref):
    payment = _owned_payment(request, ref)
    if payment is None:
        messages.error(request, "Payment record not found or access was denied.")
        return redirect("checkout")
    if (
        payment.status == Payment.Status.VERIFIED
        and payment.order.status in {Order.Status.PAID, Order.Status.PAID_STOCK_ISSUE}
    ):
        return redirect("payment_success", ref=payment.ref)
    return render(
        request,
        "payment/payment_pending.html",
        {"payment": payment, "order": payment.order},
    )


@login_required(login_url="login")
@require_GET
def payment_failed(request, ref):
    payment = _owned_payment(request, ref)
    if payment is None:
        messages.error(request, "Payment record not found or access was denied.")
        return redirect("checkout")
    if (
        payment.status == Payment.Status.VERIFIED
        and payment.order.status in {Order.Status.PAID, Order.Status.PAID_STOCK_ISSUE}
    ):
        return redirect("payment_success", ref=payment.ref)
    return render(
        request,
        "payment/payment_failed.html",
        {"payment": payment, "order": payment.order},
    )


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
        "cart_lines": preview.lines,
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
    except (EmptyCartError, InvalidCartItemError, InvalidQuantityError, InsufficientStockError) as exc:
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
@require_POST
def verify_payment(request, ref):
    payment = _owned_payment(request, ref)
    if payment is None:
        logger.warning("Browser return ownership/not-found rejection")
        messages.error(request, "Payment record not found or access was denied.")
        return redirect("checkout")

    try:
        verification_data = verify_transaction(payment.ref)
    except PaystackError:
        logger.warning("Browser verification temporarily unavailable reference=%s", ref)
        messages.info(
            request,
            "Payment confirmation is still pending. You can retry shortly.",
        )
        return redirect("payment_pending", ref=payment.ref)

    try:
        result = process_verified_payment(
            reference=payment.ref,
            verification_data=verification_data,
        )
    except (PaymentProcessingError, PaymentNotFoundError):
        logger.warning("Browser payment processing rejected reference=%s", ref)
        messages.error(request, "This payment could not be confirmed safely.")
        return redirect("payment_failed", ref=payment.ref)

    if result.successful:
        reconcile_paid_order_cart(session=request.session, order=result.order)
        return redirect("payment_success", ref=result.payment.ref)
    if result.state == Payment.Status.FAILED:
        messages.error(request, "The payment was not successful.")
        return redirect("payment_failed", ref=result.payment.ref)
    messages.info(request, "Payment confirmation is still pending.")
    return redirect("payment_pending", ref=result.payment.ref)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    signature = request.headers.get("X-Paystack-Signature")
    if not webhook_signature_is_valid(request.body, signature):
        logger.warning("Invalid Paystack webhook signature")
        return JsonResponse({"status": "invalid signature"}, status=401)

    try:
        event = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Malformed Paystack webhook JSON")
        return JsonResponse({"status": "invalid payload"}, status=400)

    if not isinstance(event, dict):
        return JsonResponse({"status": "invalid payload"}, status=400)
    event_name = event.get("event")
    if event_name != "charge.success":
        logger.info("Unsupported Paystack webhook event=%s", event_name)
        return JsonResponse({"status": "ignored"})

    data = event.get("data")
    reference = data.get("reference") if isinstance(data, dict) else None
    if not isinstance(reference, str) or not reference:
        return JsonResponse({"status": "invalid payload"}, status=400)

    try:
        verification_data = verify_transaction(reference)
    except PaystackError:
        logger.warning("Webhook verification unavailable reference=%s", reference)
        return JsonResponse({"status": "verification unavailable"}, status=503)

    try:
        result = process_verified_payment(
            reference=reference,
            verification_data=verification_data,
        )
    except PaymentNotFoundError:
        logger.warning("Webhook ignored unknown reference=%s", reference)
        return JsonResponse({"status": "ignored"})
    except PaymentProcessingError:
        logger.warning("Webhook payment processing rejected reference=%s", reference)
        return JsonResponse({"status": "rejected"}, status=400)

    return JsonResponse(
        {
            "status": "processed",
            "payment_state": result.state,
        }
    )
