from django.db import models

from django.contrib.auth.models import User

from ccstore.models import Product

import secrets

from payment.paystack import Paystack

class RegisterAddress(models.Model):

    fullname = models.CharField(max_length=300)

    email = models.EmailField(max_length=300)

    address1 = models.CharField(max_length=200)

    address2 = models.CharField(max_length=200, blank=True)

    city = models.CharField(max_length=100)

    state = models.CharField(max_length=100)

    country = models.CharField(max_length=100, null=True, blank=True)

    zipcode = models.CharField(max_length=10)

    phone = models.CharField(max_length=14)

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)



    class Meta:

        verbose_name = 'RegisterAddress'

        verbose_name_plural = 'RegisterAddress'


    def __str__(self):
        return 'shipping Adress -' + str(self.id)
    

class Order(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    fullname = models.CharField(max_length=300)

    email = models.EmailField(max_length=300)

    address1 = models.CharField(max_length=20000)

    amount_paid = models.DecimalField(max_digits=8, decimal_places=2)

    date_ordered = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return 'Order - #' + str(self.id)
    

class OrderItem(models.Model):
    #fk
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True)

    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)


    quantity = models.PositiveBigIntegerField(default=1)

    price = models.DecimalField(max_digits=8, decimal_places=2)


    def __str__(self):
        return 'OrderItem - #' + str(self.id)
    

class Payment(models.Model):

    #order = models.ForeignKey(Order, on_delete=models.CASCADE , null=True , blank=True) 

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    #payment_id = models.CharField(max_length=100)
    #payment_method = models.CharField(max_length=100)

    amount_paid = models.DecimalField(max_digits=8, decimal_places=2)

    email = models.CharField(max_length=200)

    date_paid = models.DateTimeField(auto_now_add=True)

    ref = models.CharField(max_length=200)

    verified = models.BooleanField(default=False)


    def __str__(self):
        return f'{self.user} - {self.amount_paid}'
    
    def save(self, *args, **kwargs):
        if not self.ref:
            ref = secrets.token_urlsafe(27)
            while Payment.objects.filter(ref=ref).exists():
                ref = secrets.token_urlsafe(27)
            self.ref = ref
        super().save(*args, **kwargs)

    def amount_value(self):
        return int(self.amount_paid) * 100# Convert to kobo
    
    def verify_payment(self):
        paystack = Paystack()
        status, result = paystack.verify_payment(self.ref)# No need to pass amount_paid
        if status:
            if result['amount'] / 100 == self.amount_paid:# Use 'amount' from Paystack API
                self.verified = True
                self.save()
        if self.verified:
            return True
        else:
            return False
