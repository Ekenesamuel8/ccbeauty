from .cart import Cart

def cart(request):

    return {'cart': Cart(request)}
# In this case, we are creating a new dictionary with the key 'cart' and the value Cart(request).
# This dictionary will be available in all templates.