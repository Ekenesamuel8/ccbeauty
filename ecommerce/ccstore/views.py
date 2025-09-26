from django.shortcuts import render, get_object_or_404
from . models import Category, Product, ProductImage
from django.db.models import Q

# Create your views here.
def store(request):
    products = Product.objects.all() #get all products
    context = {'my_products': products} #create a dictionary with products
    return render(request, 'ccstore/store.html', context) #render the store.html template

def category(request):
    all_categories = Category.objects.all() #get all categories
    return{'all_categories': all_categories} #return all categories

def product_info(request, product_slug):
    product = get_object_or_404(Product, slug=product_slug) #get product by slug
    images = product.images.all()  # Get all extra images linked to this product
    context = {'pdt' : product, 'images': images} #create a dictionary with product
    return render(request, 'ccstore/product_info.html', context) #render the product_info.html template

def pdt_category(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug) #get category by slug
    products = Product.objects.filter(Category=category) #get all products in this category
    return render(request, 'ccstore/pdt_category.html', {'category':category, 'products':products}) #render the category.html template

def search(request):
    query = request.GET.get('q', '') #get the search query from the URL
    if query:
        products = Product.objects.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(Category__name__icontains=query)) #filter products by title or description containing the query
    else:
        products = Product.objects.none() #if no query, get no products

    context = {
        'query' : query,
        'products' : products,
    }
    return render(request, 'ccstore/search_results.html', context) #render the search.html template with products and query