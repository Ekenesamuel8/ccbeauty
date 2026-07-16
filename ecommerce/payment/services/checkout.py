import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from django.db import IntegrityError, transaction

from ccstore.models import Product
from payment.models import Order, OrderItem, Payment, RegisterAddress


logger = logging.getLogger(__name__)

MAX_QUANTITY_PER_LINE = 99
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class CheckoutError(Exception):
    user_message = "We could not create your checkout. Please try again."


class EmptyCartError(CheckoutError):
    user_message = "Your cart is empty. Add an item before checking out."


class InvalidCartItemError(CheckoutError):
    user_message = "Your cart contains an invalid item. Please update your cart."


class ProductUnavailableError(CheckoutError):
    user_message = "A product in your cart is no longer available."


class InsufficientStockError(CheckoutError):
    user_message = "A product in your cart does not have enough stock. Please adjust your cart."


class InvalidQuantityError(CheckoutError):
    user_message = "A cart quantity is invalid. Choose between 1 and 99."


class MissingAddressError(CheckoutError):
    user_message = "Add a saved shipping address before checking out."


class AddressOwnershipError(CheckoutError):
    user_message = "The selected shipping address is not available."


class InvalidCheckoutTokenError(CheckoutError):
    user_message = "This checkout session is invalid or has expired."


class CheckoutStateError(CheckoutError):
    user_message = "The existing checkout cannot be resumed. Please contact support."


@dataclass(frozen=True)
class CartLine:
    product: Product
    quantity: int
    unit_price: Decimal

    @property
    def line_total(self):
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class CartPreview:
    lines: tuple[CartLine, ...]
    total: Decimal
    total_quantity: int


@dataclass(frozen=True)
class CheckoutResult:
    order: Order
    payment: Payment
    created: bool


def _cart_mapping(cart):
    data = getattr(cart, "cart", cart)
    if not isinstance(data, Mapping) or not data:
        raise EmptyCartError
    return data


def _parse_positive_integer(value, *, quantity=False):
    if isinstance(value, bool):
        error = InvalidQuantityError if quantity else InvalidCartItemError
        raise error
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        parsed = int(value.strip())
    else:
        error = InvalidQuantityError if quantity else InvalidCartItemError
        raise error

    if parsed <= 0:
        error = InvalidQuantityError if quantity else InvalidCartItemError
        raise error
    if quantity and parsed > MAX_QUANTITY_PER_LINE:
        raise InvalidQuantityError
    return parsed


def _parse_cart(cart):
    parsed = {}
    for raw_product_id, item in _cart_mapping(cart).items():
        product_id = _parse_positive_integer(raw_product_id)
        if product_id in parsed or not isinstance(item, Mapping):
            raise InvalidCartItemError
        if "product_qty" not in item:
            raise InvalidQuantityError
        quantity = _parse_positive_integer(item["product_qty"], quantity=True)
        parsed[product_id] = quantity
    return parsed


def _load_current_lines(parsed_cart, *, lock=False):
    products = Product.objects
    if lock:
        products = products.select_for_update()
    products_by_id = products.filter(pk__in=parsed_cart).in_bulk()

    if set(products_by_id) != set(parsed_cart):
        missing_count = len(set(parsed_cart) - set(products_by_id))
        logger.warning("Checkout rejected because %s product(s) are unavailable", missing_count)
        raise ProductUnavailableError

    lines = []
    for product_id, quantity in parsed_cart.items():
        product = products_by_id[product_id]
        if not product.is_active:
            logger.warning("Checkout rejected inactive product_id=%s sku=%s", product.id, product.sku)
            raise ProductUnavailableError
        if quantity > product.stock_quantity:
            logger.warning(
                "Checkout rejected insufficient stock product_id=%s sku=%s requested=%s available=%s",
                product.id, product.sku, quantity, product.stock_quantity,
            )
            raise InsufficientStockError
        unit_price = Decimal(product.price)
        if unit_price < 0:
            logger.warning("Checkout rejected because a current product price is invalid")
            raise InvalidCartItemError
        lines.append(
            CartLine(
                product=product,
                quantity=quantity,
                unit_price=unit_price,
            )
        )
    return tuple(lines)


def _preview_from_lines(lines):
    return CartPreview(
        lines=lines,
        total=sum((line.line_total for line in lines), Decimal("0.00")),
        total_quantity=sum(line.quantity for line in lines),
    )


def build_cart_preview(cart) -> CartPreview:
    """Validate and price a cart from current database product records."""
    try:
        return _preview_from_lines(_load_current_lines(_parse_cart(cart)))
    except CheckoutError as exc:
        logger.warning("Cart preview rejected: %s", type(exc).__name__)
        raise


def checkout_token_is_valid(value) -> bool:
    return isinstance(value, str) and TOKEN_PATTERN.fullmatch(value) is not None


def _validate_token(idempotency_key):
    if not checkout_token_is_valid(idempotency_key):
        raise InvalidCheckoutTokenError


def _existing_checkout(*, user, idempotency_key, lock=False):
    orders = Order.objects
    if lock:
        orders = orders.select_for_update()
    order = orders.filter(idempotency_key=idempotency_key).first()
    if order is None:
        return None
    if order.user_id != user.id:
        logger.warning("Checkout token ownership rejected for user_id=%s", user.id)
        raise InvalidCheckoutTokenError

    payment = order.payments.order_by("date_paid", "id").first()
    if payment is None:
        logger.error("Idempotent order_id=%s has no payment attempt", order.id)
        raise CheckoutStateError

    logger.info("Duplicate checkout token reused for order_id=%s", order.id)
    return CheckoutResult(order=order, payment=payment, created=False)


def _address_snapshot(address: RegisterAddress) -> str:
    parts = (
        address.address1,
        address.address2,
        address.city,
        address.state,
        address.zipcode,
        address.country,
    )
    return "\n".join(str(part).strip() for part in parts if part and str(part).strip())


def create_checkout_order(
    *,
    user,
    cart,
    shipping_address: RegisterAddress | None,
    idempotency_key: str,
) -> CheckoutResult:
    """Atomically create one order, its snapshots, and its exact payment."""
    if not user or not user.is_authenticated:
        raise AddressOwnershipError
    _validate_token(idempotency_key)

    existing = _existing_checkout(
        user=user,
        idempotency_key=idempotency_key,
    )
    if existing:
        return existing

    if shipping_address is None or shipping_address.pk is None:
        raise MissingAddressError
    if shipping_address.user_id != user.id:
        logger.warning("Shipping-address ownership rejected for user_id=%s", user.id)
        raise AddressOwnershipError

    try:
        parsed_cart = _parse_cart(cart)
    except CheckoutError as exc:
        logger.warning("Checkout cart rejected: %s", type(exc).__name__)
        raise

    try:
        with transaction.atomic():
            existing = _existing_checkout(
                user=user,
                idempotency_key=idempotency_key,
                lock=True,
            )
            if existing:
                return existing

            address = (
                RegisterAddress.objects.select_for_update()
                .filter(pk=shipping_address.pk, user=user)
                .first()
            )
            if address is None:
                raise MissingAddressError

            preview = _preview_from_lines(
                _load_current_lines(parsed_cart, lock=True)
            )
            order = Order.objects.create(
                user=user,
                fullname=address.fullname,
                email=address.email,
                address1=_address_snapshot(address),
                amount_paid=preview.total,
                status=Order.Status.PENDING_PAYMENT,
                idempotency_key=idempotency_key,
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        product=line.product,
                        product_title=line.product.title,
                        product_sku=line.product.sku,
                        user=user,
                        quantity=line.quantity,
                        price=line.unit_price,
                    )
                    for line in preview.lines
                ]
            )
            payment = Payment.objects.create(
                order=order,
                user=user,
                amount_paid=preview.total,
                email=order.email,
                status=Payment.Status.INITIALIZED,
            )
    except IntegrityError as exc:
        # A concurrent request may win the unique idempotency-key race.
        existing = _existing_checkout(
            user=user,
            idempotency_key=idempotency_key,
        )
        if existing:
            return existing
        raise CheckoutStateError from exc

    logger.info(
        "Checkout created order_id=%s payment_id=%s user_id=%s",
        order.id,
        payment.id,
        user.id,
    )
    return CheckoutResult(order=order, payment=payment, created=True)
