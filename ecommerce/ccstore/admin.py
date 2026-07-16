from django.contrib import admin

# Register your models here.
from .models import Category, Product, ProductImage
from django.db.models import F, Q


class StockStateFilter(admin.SimpleListFilter):
    title = 'stock state'
    parameter_name = 'stock_state'

    def lookups(self, request, model_admin):
        return (('out', 'Out of stock'), ('low', 'Low stock'), ('healthy', 'Healthy stock'))

    def queryset(self, request, queryset):
        if self.value() == 'out':
            return queryset.filter(stock_quantity=0)
        if self.value() == 'low':
            return queryset.filter(stock_quantity__gt=0, stock_quantity__lte=F('low_stock_threshold'))
        if self.value() == 'healthy':
            return queryset.filter(stock_quantity__gt=F('low_stock_threshold'))
        return queryset

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image']
    can_delete = True
    show_change_link = False

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ProductImageInline]
    list_display = ('sku', 'title', 'Category', 'price', 'stock_quantity', 'low_stock', 'is_active', 'updated_at')
    list_filter = ('Category', 'is_active', StockStateFilter)
    search_fields = ('title', 'sku', 'brand')
    list_editable = ('stock_quantity', 'is_active')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Identity', {'fields': ('title', 'slug', 'sku', 'brand', 'Category')}),
        ('Commerce', {'fields': ('price', 'is_active', 'stock_quantity', 'low_stock_threshold')}),
        ('Content', {'fields': ('description', 'image')}),
        ('Audit', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(boolean=True, description='Low stock')
    def low_stock(self, obj):
        return obj.is_low_stock

    def delete_model(self, request, obj):
        # PROTECT supplies the clear admin error when historical lines exist.
        super().delete_model(request, obj)
