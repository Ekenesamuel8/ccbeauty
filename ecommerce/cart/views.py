from django.shortcuts import render, get_object_or_404

from .cart import Cart

from ccstore.models import Product

from django.http import JsonResponse
# Create your views here.

def cart_summary(request):

    cart = Cart(request)#create cart object

    return render(request, 'cart/cart_summary.html', {'cart': cart})#render cart summary page

def add_cart(request):

    cart = Cart(request)
    
    if request.POST.get('action') == 'post':

        product_id = int(request.POST.get('product_id'))

        product_quantity = int(request.POST.get('product_quantity'))
        
        product = get_object_or_404(Product, id=product_id)

        cart.add(product=product, product_qty=product_quantity)

        cart_len = cart.__len__()

        response = JsonResponse({'qty': cart_len})

        return response


def remove_cart(request):
    
    cart = Cart(request)

    if request.POST.get('action') == 'post':

        product_id = int(request.POST.get('product_id'))

        cart.delete(product=product_id)

        cart_len = cart.__len__()

        cart_total = cart.get_total_price()

        response = JsonResponse({'qty': cart_len, 'cart_total': cart_total})

        return response
    

def update_cart(request):

    cart = Cart(request)

    if request.POST.get('action') == 'post':

        product_id = int(request.POST.get('product_id'))

        product_quantity = int(request.POST.get('product_qty'))

        cart.update(product=product_id, qty=product_quantity)

        cart_qty = cart.__len__()

        cart_total = cart.get_total_price()

        response = JsonResponse({'qty': cart_qty, 'cart_total': cart_total})

        return response




