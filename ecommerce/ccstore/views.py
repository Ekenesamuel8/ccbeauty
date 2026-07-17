from django.shortcuts import render, get_object_or_404
from . models import Category, Product, ProductImage
from django.db.models import Count, Q
from django.core.paginator import Paginator

PAGE_SIZE = 12
SORT_OPTIONS = {
    'newest': ('-created_at', '-id'),
    'price_asc': ('price', 'id'),
    'price_desc': ('-price', 'id'),
    'name': ('title', 'id'),
}


def _page(request, queryset):
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page'))


def _sorted(request, queryset, default='name'):
    selected = request.GET.get('sort', default)
    if selected not in SORT_OPTIONS:
        selected = default
    return queryset.order_by(*SORT_OPTIONS[selected]), selected

# Create your views here.
def store(request):
    active_products = Product.objects.filter(is_active=True).select_related('Category')
    products = _page(request, active_products.order_by('title', 'id'))
    featured_products = active_products.order_by('-created_at', '-id')[:8]
    featured_categories = (
        Category.objects.annotate(
            active_product_count=Count('product', filter=Q(product__is_active=True))
        )
        .filter(active_product_count__gt=0)
        .order_by('name', 'id')[:6]
    )
    context = {
        'my_products': products,
        'featured_products': featured_products,
        'featured_categories': featured_categories,
    }
    return render(request, 'ccstore/store.html', context) #render the store.html template

def category(request):
    all_categories = Category.objects.order_by('name', 'id') #get all categories
    return{'all_categories': all_categories} #return all categories

def product_info(request, product_slug):
    product = get_object_or_404(Product.objects.select_related('Category'), slug=product_slug, is_active=True)
    images = product.images.all()  # Get all extra images linked to this product
    related_products = (
        Product.objects.filter(Category=product.Category, is_active=True)
        .exclude(pk=product.pk)
        .select_related('Category')
        .order_by('-created_at', '-id')[:4]
    ) if product.is_available else Product.objects.none()
    context = {'pdt' : product, 'images': images, 'related_products': related_products} #create a dictionary with product
    return render(request, 'ccstore/product_info.html', context) #render the product_info.html template

def pdt_category(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug) #get category by slug
    queryset, selected_sort = _sorted(
        request,
        Product.objects.filter(Category=category, is_active=True).select_related('Category'),
    )
    products = _page(request, queryset)
    return render(request, 'ccstore/pdt_category.html', {
        'category': category,
        'products': products,
        'selected_sort': selected_sort,
    }) #render the category.html template

def search(request):
    query = request.GET.get('q', '').strip()
    if query:
        products = Product.objects.filter(is_active=True).filter(
            Q(title__icontains=query) | Q(description__icontains=query) |
            Q(brand__icontains=query) | Q(Category__name__icontains=query) |
            Q(sku__icontains=query)
        ).select_related('Category').distinct()
        products, selected_sort = _sorted(request, products)
    else:
        products = Product.objects.none()
        selected_sort = 'name'
    products = _page(request, products)

    context = {
        'query' : query,
        'products' : products,
        'selected_sort': selected_sort,
    }
    return render(request, 'ccstore/search_results.html', context) #render the search.html template with products and query
