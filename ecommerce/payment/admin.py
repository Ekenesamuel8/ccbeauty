from django.contrib import admin

from . models import RegisterAddress, Order, OrderItem, Payment 



admin.site.register(RegisterAddress) #register the model in the admin site

admin.site.register(Order) #register the model in the admin site

admin.site.register(OrderItem) #register the model in the admin site

admin.site.register(Payment) #register the model in the admin site