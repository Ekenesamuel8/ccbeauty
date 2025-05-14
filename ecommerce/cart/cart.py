from decimal import Decimal

from ccstore.models import Product


class Cart():
    def __init__(self, request):

        self.session = request.session

        cart = self.session.get('sess_key')

        if 'sess_key' not in self.session:
            cart = self.session['sess_key'] = {}

        self.cart = cart

    def add(self, product, product_qty):
        product_id = str(product.id)

        if product_id in self.cart:
            self.cart[product_id]['product_qty'] = product_qty

        else:
            self.cart[product_id] = {'price': str(product.price), 'product_qty': product_qty}

        self.session.modified = True


    def __len__(self):
        return sum(item['product_qty'] for item in self.cart.values())
    

    def __iter__(self):

        all_pdt_id = self.cart.keys()#get all product id from cart

        products = Product.objects.filter(id__in=all_pdt_id)#get all product objects from db

        cart = self.cart.copy()#copy cart

        for product in products:#iterate over products
            cart[str(product.id)]['product'] = product #add product object to cart

        for item in cart.values():#iterate over cart values
            item['price'] = Decimal(item['price'])#convert price to decimal
            item['total_price'] = item['price'] * item['product_qty']#calculate total price
            yield item


    def get_total_price(self):
        #calculate total price of all items in cart
        return sum(Decimal(item['price']) * item['product_qty'] for item in self.cart.values())
        

    def delete(self, product):
        product_id = str(product)#convert product id to string

        if product_id in self.cart:#check if product id is in cart

            del self.cart[product_id]#delete product from cart

        self.session.modified = True


    def update(self, product, qty):

        product_id = str(product)

        product_qty = qty

        if product_id in self.cart:

            self.cart[product_id]['product_qty'] = product_qty

        self.session.modified = True