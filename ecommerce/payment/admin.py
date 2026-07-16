from django.contrib import admin

from .models import Order, OrderItem, Payment, RegisterAddress
from .services.inventory import (
    InventoryError,
    InvalidOrderTransition,
    resolve_paid_stock_issue,
    transition_order,
)


@admin.register(RegisterAddress)
class RegisterAddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "label",
        "fullname",
        "email",
        "city",
        "state",
        "is_default",
        "user",
    )
    list_filter = ("is_default", "state", "city")
    search_fields = ("fullname", "email", "phone", "user__username")
    list_select_related = ("user",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "amount_paid",
        "stock_deducted",
        "stock_restored",
        "payment_state",
        "date_ordered",
    )
    list_filter = ("status", "confirmation_status", "date_ordered")
    search_fields = (
        "=id",
        "fullname",
        "email",
        "user__username",
        "idempotency_key",
    )
    readonly_fields = (
        "date_ordered",
        "updated_at",
        "idempotency_key",
        "confirmation_sent_at",
        "stock_deducted_at",
        "stock_restored_at",
        "status",
    )
    date_hierarchy = "date_ordered"
    list_select_related = ("user",)
    actions = ('mark_processing', 'mark_shipped', 'mark_delivered', 'retry_stock_allocation')

    @admin.display(description="Payment attempts")
    def payment_attempt_count(self, obj):
        return obj.payments.count()

    @admin.display(boolean=True, description='Stock deducted')
    def stock_deducted(self, obj):
        return bool(obj.stock_deducted_at)

    @admin.display(boolean=True, description='Stock restored')
    def stock_restored(self, obj):
        return bool(obj.stock_restored_at)

    @admin.display(description='Payment')
    def payment_state(self, obj):
        payment = obj.payments.order_by('-date_paid', '-id').first()
        return payment.get_status_display() if payment else 'No payment'

    def _transition(self, request, queryset, target):
        changed = 0
        for order in queryset:
            try:
                transition_order(order.id, target)
                changed += 1
            except InvalidOrderTransition as exc:
                self.message_user(request, f'Order #{order.id}: {exc}', level='error')
        if changed:
            self.message_user(request, f'{changed} order(s) updated.')

    @admin.action(description='Mark selected orders processing')
    def mark_processing(self, request, queryset):
        self._transition(request, queryset, Order.Status.PROCESSING)

    @admin.action(description='Mark selected orders shipped')
    def mark_shipped(self, request, queryset):
        self._transition(request, queryset, Order.Status.SHIPPED)

    @admin.action(description='Mark selected orders delivered')
    def mark_delivered(self, request, queryset):
        self._transition(request, queryset, Order.Status.DELIVERED)

    @admin.action(description='Retry stock allocation for paid stock issues')
    def retry_stock_allocation(self, request, queryset):
        changed = 0
        for order in queryset:
            try:
                resolve_paid_stock_issue(order.id)
                changed += 1
            except (InventoryError, InvalidOrderTransition) as exc:
                self.message_user(request, f'Order #{order.id}: {exc}', level='error')
        if changed:
            self.message_user(request, f'{changed} order(s) allocated and marked paid.')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product_title",
        "product_sku",
        "product",
        "quantity",
        "price",
        "display_line_total",
    )
    list_filter = ("order__status",)
    search_fields = ("=order__id", "product_title", "product_sku", "product__title")
    readonly_fields = ("product_title", "product_sku")
    list_select_related = ("order", "product", "user")

    @admin.display(description="Line total")
    def display_line_total(self, obj):
        return obj.line_total


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "ref",
        "order",
        "user",
        "status",
        "amount_paid",
        "provider_transaction_id",
        "legacy_unreconciled",
        "date_paid",
    )
    list_filter = ("status", "date_paid")
    search_fields = (
        "ref",
        "provider_transaction_id",
        "email",
        "=order__id",
        "user__username",
    )
    readonly_fields = (
        "ref",
        "date_paid",
        "updated_at",
        "verified_at",
        "provider_paid_at",
        "provider_transaction_id",
    )
    date_hierarchy = "date_paid"
    list_select_related = ("order", "user")

    @admin.display(boolean=True, description="Legacy unreconciled")
    def legacy_unreconciled(self, obj):
        return obj.is_legacy_unreconciled
