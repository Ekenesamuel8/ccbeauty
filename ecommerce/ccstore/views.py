from django.shortcuts import render, get_object_or_404
from . models import Category, Product, ProductImage
from django.db.models import Q
from django.core.paginator import Paginator

PAGE_SIZE = 12


def _page(request, queryset):
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page'))

# Create your views here.
def store(request):
    products = _page(request, Product.objects.filter(is_active=True).select_related('Category').order_by('title', 'id'))
    context = {'my_products': products} #create a dictionary with products
    return render(request, 'ccstore/store.html', context) #render the store.html template

def category(request):
    all_categories = Category.objects.all() #get all categories
    return{'all_categories': all_categories} #return all categories

def product_info(request, product_slug):
    product = get_object_or_404(Product.objects.select_related('Category'), slug=product_slug, is_active=True)
    images = product.images.all()  # Get all extra images linked to this product
    context = {'pdt' : product, 'images': images} #create a dictionary with product
    return render(request, 'ccstore/product_info.html', context) #render the product_info.html template

def pdt_category(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug) #get category by slug
    products = _page(request, Product.objects.filter(Category=category, is_active=True).order_by('title', 'id'))
    return render(request, 'ccstore/pdt_category.html', {'category':category, 'products':products}) #render the category.html template

def search(request):
    query = request.GET.get('q', '').strip()
    if query:
        products = Product.objects.filter(is_active=True).filter(
            Q(title__icontains=query) | Q(description__icontains=query) |
            Q(brand__icontains=query) | Q(Category__name__icontains=query) |
            Q(sku__icontains=query)
        ).select_related('Category').distinct().order_by('title', 'id')
    else:
        products = Product.objects.none()
    products = _page(request, products)

    context = {
        'query' : query,
        'products' : products,
    }
    return render(request, 'ccstore/search_results.html', context) #render the search.html template with products and query
