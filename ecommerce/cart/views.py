import logging

from django.shortcuts import render

from .cart import Cart

from ccstore.models import Product

from django.http import JsonResponse
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def _error(message, status=400):
    return JsonResponse({'error': message}, status=status)


def _positive_quantity(value):
    if isinstance(value, bool):
        raise ValueError
    text = str(value or '').strip()
    if not text.isdigit():
        raise ValueError
    quantity = int(text)
    if quantity < 1 or quantity > 99:
        raise ValueError
    return quantity


def _available_product(product_id, quantity):
    try:
        product = Product.objects.get(pk=int(product_id))
    except (Product.DoesNotExist, TypeError, ValueError):
        return None, _error('This product is not available.', 404)
    if not product.is_active:
        logger.warning('Cart rejected inactive product_id=%s sku=%s', product.id, product.sku)
        return None, _error('This product is not available.')
    if product.stock_quantity < quantity:
        logger.warning(
            'Cart rejected insufficient stock product_id=%s sku=%s requested=%s available=%s',
            product.id, product.sku, quantity, product.stock_quantity,
        )
        message = 'This product is out of stock.' if product.stock_quantity == 0 else f'Only {product.stock_quantity} item(s) are available.'
        return None, _error(message)
    return product, None
# Create your views here.

def cart_summary(request):
    cart = Cart(request)
    cart_items = list(cart)
    cart_is_valid = bool(cart_items) and len(cart_items) == len(cart.cart) and all(
        item.get('product')
        and item['product'].is_active
        and item['product_qty'] <= item['product'].stock_quantity
        for item in cart_items
    )
    return render(
        request,
        'cart/cart_summary.html',
        {'cart': cart, 'cart_items': cart_items, 'cart_is_valid': cart_is_valid},
    )

@require_POST
def add_cart(request):

    cart = Cart(request)
    
    if request.POST.get('action') == 'post':

        try:
            product_quantity = _positive_quantity(request.POST.get('product_quantity'))
        except ValueError:
            return _error('Choose a quantity between 1 and 99.')
        product, error = _available_product(request.POST.get('product_id'), product_quantity)
        if error:
            return error

        cart.add(product=product, product_qty=product_quantity)

        cart_len = cart.__len__()

        response = JsonResponse({'qty': cart_len})

        return response
    return _error('Invalid cart request.')


@require_POST
def remove_cart(request):
    
    cart = Cart(request)

    if request.POST.get('action') == 'post':

        product_id = int(request.POST.get('product_id'))

        cart.delete(product=product_id)

        cart_len = cart.__len__()

        cart_total = cart.get_total_price()

        response = JsonResponse({'qty': cart_len, 'cart_total': cart_total})

        return response
    

@require_POST
def update_cart(request):

    cart = Cart(request)

    if request.POST.get('action') == 'post':

        try:
            product_quantity = _positive_quantity(request.POST.get('product_qty'))
        except ValueError:
            return _error('Choose a quantity between 1 and 99.')
        product, error = _available_product(request.POST.get('product_id'), product_quantity)
        if error:
            return error
        product_id = product.id

        cart.update(product=product_id, qty=product_quantity)

        cart_qty = cart.__len__()

        cart_total = cart.get_total_price()

        response = JsonResponse({'qty': cart_qty, 'cart_total': cart_total})

        return response
    return _error('Invalid cart request.')




