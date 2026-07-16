import logging
from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone

from payment.models import Order, Payment
from payment.services.paystack import PaystackVerificationResult
from payment.services.inventory import deduct_stock_for_verified_order


logger = logging.getLogger(__name__)

DEFINITIVE_FAILURE_STATUSES = {"failed", "abandoned", "reversed"}
PAYABLE_ORDER_STATUSES = {
    Order.Status.PENDING_PAYMENT,
    Order.Status.PAYMENT_FAILED,
}
PAYABLE_PAYMENT_STATUSES = {
    Payment.Status.INITIALIZED,
    Payment.Status.PENDING,
}


class PaymentProcessingError(Exception):
    pass


class PaymentNotFoundError(PaymentProcessingError):
    pass


class LegacyPaymentError(PaymentProcessingError):
    pass


class PaymentOwnershipError(PaymentProcessingError):
    pass


class PaymentReferenceMismatch(PaymentProcessingError):
    pass


class PaymentAmountMismatch(PaymentProcessingError):
    pass


class PaymentCurrencyMismatch(PaymentProcessingError):
    pass


class PaymentCustomerMismatch(PaymentProcessingError):
    pass


class DuplicateProviderTransactionError(PaymentProcessingError):
    pass


class InvalidPaymentStateError(PaymentProcessingError):
    pass


@dataclass(frozen=True)
class PaymentProcessingResult:
    payment: Payment
    order: Order
    state: str
    newly_verified: bool
    confirmation_scheduled: bool

    @property
    def successful(self) -> bool:
        return self.state == Payment.Status.VERIFIED


def _expected_kobo(amount):
    return int(amount * 100)


def _validate_consistency(payment, order, reference, verification_data):
    if verification_data.reference != reference or payment.ref != reference:
        logger.warning("Payment reference mismatch reference=%s", reference)
        raise PaymentReferenceMismatch
    if payment.user_id and order.user_id and payment.user_id != order.user_id:
        logger.warning("Payment ownership mismatch payment_id=%s", payment.id)
        raise PaymentOwnershipError
    if payment.email.casefold() != order.email.casefold():
        logger.warning("Payment/order email mismatch payment_id=%s", payment.id)
        raise PaymentOwnershipError
    if (
        verification_data.customer_email
        and verification_data.customer_email.casefold() != payment.email.casefold()
    ):
        logger.warning("Paystack customer mismatch payment_id=%s", payment.id)
        raise PaymentCustomerMismatch

    expected_payment_kobo = _expected_kobo(payment.amount_paid)
    expected_order_kobo = _expected_kobo(order.amount_paid)
    if (
        expected_payment_kobo != expected_order_kobo
        or verification_data.amount_kobo != expected_payment_kobo
    ):
        logger.warning("Payment amount mismatch payment_id=%s", payment.id)
        raise PaymentAmountMismatch
    if verification_data.currency != payment.currency.upper():
        logger.warning("Payment currency mismatch payment_id=%s", payment.id)
        raise PaymentCurrencyMismatch


def _ensure_provider_transaction_available(payment, transaction_id):
    if payment.provider_transaction_id and payment.provider_transaction_id != transaction_id:
        raise DuplicateProviderTransactionError
    if (
        Payment.objects.exclude(pk=payment.pk)
        .filter(provider_transaction_id=transaction_id)
        .exists()
    ):
        logger.warning(
            "Provider transaction reuse rejected transaction_id=%s",
            transaction_id,
        )
        raise DuplicateProviderTransactionError


def _apply_provider_metadata(payment, verification_data):
    payment.provider = "paystack"
    payment.provider_transaction_id = verification_data.transaction_id
    payment.currency = verification_data.currency
    payment.provider_paid_at = verification_data.paid_at
    payment.provider_channel = verification_data.channel or ""


def _claim_confirmation(order):
    if order.confirmation_status not in {
        Order.ConfirmationStatus.PENDING,
        Order.ConfirmationStatus.FAILED,
    }:
        return False
    order.confirmation_status = Order.ConfirmationStatus.SENDING
    order.confirmation_sent_at = None
    order.save(
        update_fields=(
            "confirmation_status",
            "confirmation_sent_at",
            "updated_at",
        )
    )
    return True


def _confirmation_body(order, payment):
    item_lines = [
        f"- {item.product_title} x {item.quantity}: NGN {item.line_total}"
        for item in order.orderitem_set.order_by("id")
    ]
    return "\n".join(
        [
            f"Hello {order.fullname},",
            "",
            f"Payment for order #{order.id} has been verified.",
            f"Payment reference: {payment.ref}",
            f"Paid amount: NGN {order.amount_paid}",
            "",
            "Items:",
            *item_lines,
            "",
            "Shipping summary:",
            order.address1,
            "",
            "Thank you for shopping with CCbeauty.",
        ]
    )


def deliver_order_confirmation(*, order_id, payment_id):
    """Deliver a claimed confirmation without affecting paid-state correctness."""
    try:
        order = Order.objects.get(pk=order_id)
        payment = Payment.objects.get(pk=payment_id, order_id=order_id)
        if (
            order.status != Order.Status.PAID
            or payment.status != Payment.Status.VERIFIED
            or order.confirmation_status != Order.ConfirmationStatus.SENDING
        ):
            return False

        sent_count = send_mail(
            subject=f"CCbeauty payment confirmed - order #{order.id}",
            message=_confirmation_body(order, payment),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[order.email],
            fail_silently=False,
        )
        if sent_count != 1:
            raise RuntimeError("Confirmation email was not accepted by the backend")
    except Exception:
        logger.exception(
            "Order confirmation email failed order_id=%s payment_id=%s",
            order_id,
            payment_id,
        )
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().filter(pk=order_id).first()
            if (
                locked_order
                and locked_order.confirmation_status
                == Order.ConfirmationStatus.SENDING
            ):
                locked_order.confirmation_status = Order.ConfirmationStatus.FAILED
                locked_order.confirmation_sent_at = None
                locked_order.save(
                    update_fields=(
                        "confirmation_status",
                        "confirmation_sent_at",
                        "updated_at",
                    )
                )
        return False

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order_id)
        if locked_order.confirmation_status == Order.ConfirmationStatus.SENDING:
            locked_order.confirmation_status = Order.ConfirmationStatus.SENT
            locked_order.confirmation_sent_at = timezone.now()
            locked_order.save(
                update_fields=(
                    "confirmation_status",
                    "confirmation_sent_at",
                    "updated_at",
                )
            )
    logger.info("Order confirmation email sent order_id=%s", order_id)
    return True


def _schedule_confirmation(order, payment):
    transaction.on_commit(
        lambda: deliver_order_confirmation(
            order_id=order.id,
            payment_id=payment.id,
        )
    )


def reconcile_paid_order_cart(*, session, order: Order) -> bool:
    """Subtract paid quantities while preserving unrelated/newer cart contents."""
    cart = session.get("sess_key")
    if not isinstance(cart, dict) or order.status != Order.Status.PAID:
        return False

    purchased = defaultdict(int)
    for product_id, quantity in order.orderitem_set.exclude(
        product_id=None
    ).values_list("product_id", "quantity"):
        purchased[str(product_id)] += quantity

    changed = False
    for product_id, paid_quantity in purchased.items():
        item = cart.get(product_id)
        if not isinstance(item, dict):
            continue
        current_quantity = item.get("product_qty")
        if isinstance(current_quantity, bool):
            continue
        try:
            current_quantity = int(current_quantity)
        except (TypeError, ValueError):
            continue
        if current_quantity > paid_quantity:
            item["product_qty"] = current_quantity - paid_quantity
        else:
            del cart[product_id]
        changed = True

    if changed:
        session["sess_key"] = cart
        session.modified = True
    return changed


def process_verified_payment(
    *,
    reference: str,
    verification_data: PaystackVerificationResult,
) -> PaymentProcessingResult:
    """Apply a verified Paystack result to one exact payment and order."""
    try:
        with transaction.atomic():
            try:
                payment = Payment.objects.select_for_update().get(ref=reference)
            except Payment.DoesNotExist as exc:
                raise PaymentNotFoundError from exc
            if not payment.order_id:
                raise LegacyPaymentError

            order = Order.objects.select_for_update().get(pk=payment.order_id)
            _validate_consistency(payment, order, reference, verification_data)
            _ensure_provider_transaction_available(
                payment,
                verification_data.transaction_id,
            )

            if payment.status == Payment.Status.VERIFIED and order.status in {
                Order.Status.PAID,
                Order.Status.PAID_STOCK_ISSUE,
            }:
                confirmation_claimed = (
                    _claim_confirmation(order)
                    if order.status == Order.Status.PAID
                    else False
                )
                if confirmation_claimed:
                    _schedule_confirmation(order, payment)
                logger.info("Payment already processed payment_id=%s", payment.id)
                return PaymentProcessingResult(
                    payment=payment,
                    order=order,
                    state=Payment.Status.VERIFIED,
                    newly_verified=False,
                    confirmation_scheduled=confirmation_claimed,
                )

            if payment.status == Payment.Status.VERIFIED or order.status in {
                Order.Status.PAID, Order.Status.PAID_STOCK_ISSUE,
            }:
                raise InvalidPaymentStateError

            _apply_provider_metadata(payment, verification_data)
            if not verification_data.successful:
                if verification_data.status in DEFINITIVE_FAILURE_STATUSES:
                    payment.status = Payment.Status.FAILED
                    payment.failure_reason = (
                        f"Paystack transaction status: {verification_data.status}"
                    )
                    if order.status == Order.Status.PENDING_PAYMENT:
                        order.status = Order.Status.PAYMENT_FAILED
                        order.save(update_fields=("status", "updated_at"))
                    state = Payment.Status.FAILED
                    logger.info("Payment verification failed payment_id=%s", payment.id)
                else:
                    payment.status = Payment.Status.PENDING
                    payment.failure_reason = ""
                    if order.status == Order.Status.PAYMENT_FAILED:
                        order.status = Order.Status.PENDING_PAYMENT
                        order.save(update_fields=("status", "updated_at"))
                    state = Payment.Status.PENDING
                payment.save(
                    update_fields=(
                        "provider",
                        "provider_transaction_id",
                        "currency",
                        "provider_paid_at",
                        "provider_channel",
                        "status",
                        "failure_reason",
                        "updated_at",
                    )
                )
                return PaymentProcessingResult(
                    payment=payment,
                    order=order,
                    state=state,
                    newly_verified=False,
                    confirmation_scheduled=False,
                )

            if payment.status not in PAYABLE_PAYMENT_STATUSES:
                raise InvalidPaymentStateError
            if order.status not in PAYABLE_ORDER_STATUSES:
                raise InvalidPaymentStateError

            payment.status = Payment.Status.VERIFIED
            payment.verified_at = timezone.now()
            payment.failure_reason = ""
            payment.save(
                update_fields=(
                    "provider",
                    "provider_transaction_id",
                    "currency",
                    "provider_paid_at",
                    "provider_channel",
                    "status",
                    "verified_at",
                    "failure_reason",
                    "updated_at",
                )
            )
            stock_ok = deduct_stock_for_verified_order(order)
            confirmation_claimed = _claim_confirmation(order) if stock_ok else False
            if confirmation_claimed:
                _schedule_confirmation(order, payment)
            logger.info(
                "Payment verified payment_id=%s order_id=%s transaction_id=%s",
                payment.id,
                order.id,
                payment.provider_transaction_id,
            )
            return PaymentProcessingResult(
                payment=payment,
                order=order,
                state=Payment.Status.VERIFIED,
                newly_verified=True,
                confirmation_scheduled=confirmation_claimed,
            )
    except IntegrityError as exc:
        if Payment.objects.filter(
            provider_transaction_id=verification_data.transaction_id
        ).exists():
            raise DuplicateProviderTransactionError from exc
        raise PaymentProcessingError("Payment state update failed") from exc
