from django.contrib import admin

from .models import Order, OrderItem, Payment, RegisterAddress


@admin.register(RegisterAddress)
class RegisterAddressAdmin(admin.ModelAdmin):
    list_display = ("id", "fullname", "email", "city", "state", "user")
    search_fields = ("fullname", "email", "phone", "user__username")
    list_select_related = ("user",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "fullname",
        "email",
        "status",
        "amount_paid",
        "payment_attempt_count",
        "date_ordered",
    )
    list_filter = ("status", "date_ordered")
    search_fields = (
        "=id",
        "fullname",
        "email",
        "user__username",
        "idempotency_key",
    )
    readonly_fields = ("date_ordered", "updated_at", "idempotency_key")
    date_hierarchy = "date_ordered"
    list_select_related = ("user",)

    @admin.display(description="Payment attempts")
    def payment_attempt_count(self, obj):
        return obj.payments.count()


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "product_title",
        "product",
        "quantity",
        "price",
        "display_line_total",
    )
    list_filter = ("order__status",)
    search_fields = ("=order__id", "product_title", "product__title")
    readonly_fields = ("product_title",)
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
        "legacy_unreconciled",
        "date_paid",
    )
    list_filter = ("status", "date_paid")
    search_fields = ("ref", "email", "=order__id", "user__username")
    readonly_fields = ("ref", "date_paid")
    date_hierarchy = "date_paid"
    list_select_related = ("order", "user")

    @admin.display(boolean=True, description="Legacy unreconciled")
    def legacy_unreconciled(self, obj):
        return obj.is_legacy_unreconciled
