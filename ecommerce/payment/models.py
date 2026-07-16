import secrets
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from ccstore.models import Product
from payment.paystack import Paystack


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = "pending_payment", "Pending payment"
    PAID = "paid", "Paid"
    PROCESSING = "processing", "Processing"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"
    PAYMENT_FAILED = "payment_failed", "Payment failed"


class PaymentStatus(models.TextChoices):
    INITIALIZED = "initialized", "Initialized"
    PENDING = "pending", "Pending"
    VERIFIED = "verified", "Verified"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"


class RegisterAddress(models.Model):
    fullname = models.CharField(max_length=300)
    email = models.EmailField(max_length=300)
    address1 = models.CharField(max_length=200)
    address2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, null=True, blank=True)
    zipcode = models.CharField(max_length=10)
    phone = models.CharField(max_length=14)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "RegisterAddress"
        verbose_name_plural = "RegisterAddress"

    def __str__(self):
        return f"Shipping address - {self.id}"


class Order(models.Model):
    Status = OrderStatus

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=(
            "The account may be deleted while the copied customer details remain "
            "on this historical order."
        ),
    )
    fullname = models.CharField(max_length=300)
    email = models.EmailField(max_length=300)
    address1 = models.CharField(max_length=20000)
    amount_paid = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="order total",
    )
    date_ordered = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
        db_index=True,
    )
    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text="Durable checkout token; legacy orders remain null.",
    )

    class Meta:
        ordering = ("-date_ordered", "-id")
        indexes = [
            models.Index(
                fields=("user", "-date_ordered"),
                name="order_user_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_paid__gte=0),
                name="order_amount_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=OrderStatus.values),
                name="order_status_valid",
            ),
        ]

    def __str__(self):
        return f"Order - #{self.id}"

    @property
    def total(self):
        """Compatibility-friendly name for the persisted decimal order total."""
        return self.amount_paid


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        null=True,
        help_text="Protected so deleting a product cannot erase this order line.",
    )
    product_title = models.CharField(
        max_length=250,
        help_text="Immutable product-name snapshot captured when the line is created.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    quantity = models.PositiveBigIntegerField(default=1)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="orderitem_qty_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="orderitem_price_gte_zero",
            ),
        ]

    def __str__(self):
        return f"OrderItem - #{self.id}"

    def clean(self):
        super().clean()
        if not self.product_title and not self.product_id:
            raise ValidationError(
                {"product_title": "A historical product title is required."}
            )

    def save(self, *args, **kwargs):
        if self._state.adding and not self.product_title and self.product_id:
            self.product_title = self.product.title
        super().save(*args, **kwargs)

    @property
    def line_total(self):
        return self.price * self.quantity


class Payment(models.Model):
    Status = PaymentStatus

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
        help_text=(
            "Legacy payments created before the explicit relationship remain "
            "unreconciled with order=NULL."
        ),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2)
    email = models.CharField(max_length=200)
    date_paid = models.DateTimeField(auto_now_add=True)
    ref = models.CharField(max_length=200, unique=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIALIZED,
        db_index=True,
    )

    class Meta:
        ordering = ("-date_paid", "-id")
        indexes = [
            models.Index(
                fields=("order", "-date_paid"),
                name="payment_order_date_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_paid__gte=0),
                name="payment_amount_gte_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=PaymentStatus.values),
                name="payment_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.ref} - {self.amount_paid}"

    def save(self, *args, **kwargs):
        if self.ref:
            return super().save(*args, **kwargs)

        # The database constraint is authoritative. Retry only the extremely
        # unlikely collision produced while generating a new reference.
        for _ in range(5):
            self.ref = secrets.token_urlsafe(27)
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError:
                if type(self).objects.filter(ref=self.ref).exists():
                    self.ref = ""
                    continue
                raise
        raise IntegrityError("Unable to generate a unique payment reference")

    @property
    def verified(self):
        """Temporary compatibility alias; status is the sole persisted state."""
        return self.status == self.Status.VERIFIED

    @verified.setter
    def verified(self, value):
        self.status = self.Status.VERIFIED if value else self.Status.INITIALIZED

    @property
    def is_legacy_unreconciled(self):
        return self.order_id is None

    def amount_value(self):
        return int(self.amount_paid * Decimal("100"))

    def verify_payment(self):
        paystack = Paystack()
        status, result = paystack.verify_payment(self.ref)
        if status:
            paid_amount = Decimal(result["amount"]) / Decimal("100")
            if paid_amount == self.amount_paid:
                self.verified = True
                self.save(update_fields=("status",))
        return self.verified
