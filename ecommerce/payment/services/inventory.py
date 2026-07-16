import logging
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from ccstore.models import Product
from payment.models import Order

logger = logging.getLogger(__name__)


class InventoryError(Exception):
    pass


class InvalidOrderTransition(InventoryError):
    pass


VALID_TRANSITIONS = {
    Order.Status.PENDING_PAYMENT: {Order.Status.PAYMENT_FAILED, Order.Status.CANCELLED},
    Order.Status.PAYMENT_FAILED: {Order.Status.PENDING_PAYMENT, Order.Status.CANCELLED},
    Order.Status.PAID: {Order.Status.PROCESSING, Order.Status.CANCELLED, Order.Status.REFUNDED},
    Order.Status.PROCESSING: {Order.Status.SHIPPED, Order.Status.CANCELLED, Order.Status.REFUNDED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED},
    Order.Status.PAID_STOCK_ISSUE: {Order.Status.CANCELLED, Order.Status.REFUNDED},
    Order.Status.CANCELLED: {Order.Status.REFUNDED},
}


@transaction.atomic
def deduct_stock_for_verified_order(order):
    """Deduct all order quantities atomically; caller must hold the order lock."""
    if not order.payments.filter(status='verified').exists():
        raise InventoryError('Stock cannot be deducted before payment is verified.')
    if order.stock_deducted_at:
        logger.info("Duplicate stock deduction ignored order_id=%s", order.id)
        return True

    quantities = defaultdict(int)
    items = list(order.orderitem_set.order_by("product_id", "id"))
    for item in items:
        if not item.product_id:
            logger.error("Paid order has missing product order_id=%s item_id=%s", order.id, item.id)
            order.status = Order.Status.PAID_STOCK_ISSUE
            order.save(update_fields=("status", "updated_at"))
            return False
        quantities[item.product_id] += item.quantity

    products = {
        product.id: product
        for product in Product.objects.select_for_update().filter(pk__in=quantities)
    }
    for product_id, quantity in quantities.items():
        product = products.get(product_id)
        if product is None or not product.is_active or product.stock_quantity < quantity:
            logger.error(
                "Insufficient stock after verified payment order_id=%s product_id=%s sku=%s requested=%s available=%s",
                order.id,
                product_id,
                getattr(product, "sku", "missing"),
                quantity,
                getattr(product, "stock_quantity", 0),
            )
            order.status = Order.Status.PAID_STOCK_ISSUE
            order.save(update_fields=("status", "updated_at"))
            return False

    for product_id, quantity in quantities.items():
        product = products[product_id]
        product.stock_quantity -= quantity
        product.save(update_fields=("stock_quantity", "updated_at"))
        logger.info(
            "Stock deducted order_id=%s product_id=%s sku=%s quantity=%s",
            order.id, product.id, product.sku, quantity,
        )
    order.stock_deducted_at = timezone.now()
    order.stock_restored_at = None
    order.status = Order.Status.PAID
    order.save(update_fields=("stock_deducted_at", "stock_restored_at", "status", "updated_at"))
    return True


@transaction.atomic
def resolve_paid_stock_issue(order_id):
    """Retry allocation after staff restock; never substitutes or refunds automatically."""
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PAID_STOCK_ISSUE:
        raise InvalidOrderTransition('Only paid stock-issue orders can retry allocation.')
    if not deduct_stock_for_verified_order(order):
        raise InventoryError('Stock is still insufficient for this order.')
    return order


@transaction.atomic
def restore_order_stock(order_id):
    """Explicitly restore previously deducted stock once; no payment refund occurs."""
    order = Order.objects.select_for_update().get(pk=order_id)
    if not order.stock_deducted_at or order.stock_restored_at:
        return False
    if order.status not in {Order.Status.CANCELLED, Order.Status.REFUNDED}:
        raise InvalidOrderTransition("Stock can only be restored for cancelled or refunded orders.")

    quantities = defaultdict(int)
    for product_id, quantity in order.orderitem_set.values_list("product_id", "quantity"):
        if product_id:
            quantities[product_id] += quantity
    products = {
        product.id: product
        for product in Product.objects.select_for_update().filter(pk__in=quantities)
    }
    if set(products) != set(quantities):
        raise InventoryError("One or more historical products are unavailable for restoration.")
    for product_id, quantity in quantities.items():
        product = products[product_id]
        product.stock_quantity += quantity
        product.save(update_fields=("stock_quantity", "updated_at"))
    order.stock_restored_at = timezone.now()
    order.save(update_fields=("stock_restored_at", "updated_at"))
    logger.info("Stock restored order_id=%s", order.id)
    return True


@transaction.atomic
def transition_order(order_id, target_status):
    order = Order.objects.select_for_update().get(pk=order_id)
    allowed = VALID_TRANSITIONS.get(order.status, set())
    if target_status not in allowed:
        logger.warning(
            "Invalid order transition order_id=%s from=%s to=%s",
            order.id, order.status, target_status,
        )
        raise InvalidOrderTransition(f"Order cannot move from {order.status} to {target_status}.")
    order.status = target_status
    order.save(update_fields=("status", "updated_at"))
    return order
