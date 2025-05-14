from django.shortcuts import render, get_object_or_404
from . models import Category, Product

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
    context = {'pdt' : product} #create a dictionary with product
    return render(request, 'ccstore/product_info.html', context) #render the product_info.html template

def pdt_category(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug) #get category by slug
    products = Product.objects.filter(Category=category) #get all products in this category
    return render(request, 'ccstore/pdt_category.html', {'category':category, 'products':products}) #render the category.html template