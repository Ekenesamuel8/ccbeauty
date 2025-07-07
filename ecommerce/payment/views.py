from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import RegisterAddress, Order, OrderItem, Payment
from cart.cart import Cart
from django.http import JsonResponse
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail

@login_required(login_url='login')
def payment_failed(request):    
    return render(request, 'payment/payment_failed.html')


@login_required(login_url='login')
def payment_success(request):

    return render(request, 'payment/payment_success.html')

@login_required(login_url='login')
def checkout(request):

    if request.user.is_authenticated:

        try:
            cart = Cart(request)
            #get the cart items
            total_items = cart.__len__()
            total_cost = cart.get_total_price()
            shipping_address = RegisterAddress.objects.get(user=request.user.id)
            context = {'shipping_address': shipping_address, 'total_cost': total_cost, 'cart': cart, 'total_items': total_items}
            return render(request, 'payment/checkout.html', context=context)
        except:
            return render(request, 'payment/checkout.html')
    else:

        return render(request, 'payment/checkout.html')

@login_required(login_url='login')    
def orders(request):

    if request.POST.get('action') == 'post':
        fullname = request.POST.get('fullname')
        email = request.POST.get('email')
        address1 = request.POST.get('address1')
        address2 = request.POST.get('address2')
        city = request.POST.get('city')
        state = request.POST.get('state')
        zip_code = request.POST.get('zipcode')
        #phone = request.POST.get('phone')

        shipping_address = (
            (address1 or '') + '\n' +
            (address2 or '') + '\n' +
            (city or '') + '\n' +
            (state or '') + '\n' +
            (zip_code or '')
        )

        #shipping cart info
        cart = Cart(request)

        #get total price of all items in cart
        total_cost = cart.get_total_price()


        if request.user.is_authenticated:#create order -> acount users with or without shipping information
                
            order = Order.objects.create(user=request.user, address1=shipping_address, amount_paid=total_cost, email=email, fullname=fullname)
            #get the fk for user and address, ammount paid, email, fullname

            order_id = order.pk
            #get the pk of the order above

            pdt_list = []
            for item in cart:
                #get the items containing in the cart summary
                OrderItem.objects.create(order_id=order_id, product=item['product'], price=item['price'], quantity=item['product_qty'], user=request.user)

                pdt_list.append(item['product'])

            send_mail( 'Order Received', 'HI!' + 'thank you for placing your order with us. Your order will be processed and shipped to you as soon as possible.'
                      + '\n\n' + str(pdt_list) + '\n\n' + 'Thank you for shopping with us!' + 'totalcost NGN' + str(cart.get_total_price()), settings.EMAIL_HOST_USER, [email], fail_silently=False
                      )

        else:#create order -> guest users

            order = Order.objects.create(address1=shipping_address, amount_paid=total_cost, email=email, fullname=fullname)

            order_id = order.pk

            pdt_list = []
            for item in cart:
                OrderItem.objects.create(order_id=order_id, product=item['product'], price=item['price'], quantity=item['product_qty'])

                pdt_list.append(item['product'])


            send_mail( 'Order Received', 'HI!' + '\n\n' + 'thank you for placing your order with us. Your order will be processed and shipped to you as soon as possible.'
                      + '\n\n' + str(pdt_list) + '\n\n' + 'Thank you for shopping with us!' + '\n\n' + 'totalcost NGN' + str(cart.get_total_price()), settings.EMAIL_HOST_USER, [email], fail_silently=False
                      )

        order_success = True

        response = JsonResponse({'success': order_success})

        return response
    
@login_required(login_url='login')
def verify_payment(request, ref):
    try:
        payment = Payment.objects.get(ref=ref)
        verified = payment.verify_payment()

        if verified:
            last_order = Order.objects.latest('date_ordered')

            if last_order:
                order = Order.objects.get(pk=last_order.id)

                order.is_verified = True
                order.save()

                #clear session for the the user shopping cart
                for key in list(request.session.keys()):
                    if key == 'sess_key':
                        del request.session[key]

                order_info = {
                    'id': order.id,
                    'total_cost': order.amount_paid,
                }

                context = {
                    'placed_order': order_info,
                    'payment': payment,
                }

                return render(request, 'payment/payment_success.html', context=context)
            else:
                messages.warning(request, 'Sorry, order id not found')
                return JsonResponse({'error message': 'Sorry, order id not found'}, status=400)
        else:
            messages.warning(request, 'Sorry, payment verification failed')
            return redirect('dashboard')
    except Payment.DoesNotExist:
        messages.warning(request, 'Sorry, payment not found for this ref')
        return JsonResponse({'error message': 'Sorry, payment not found'})

@login_required(login_url='login')
def makepayment(request):
    cart = Cart(request)
    PAYSTACK_PK = settings.PAYSTACK_PUBLIC_KEY
    total_cost = cart.get_total_price()
    email = request.user.email
    
    payment = Payment.objects.create(amount_paid=total_cost, email=email, user=request.user)  
    request.session['order_id'] = payment.pk
    payment.save()

    context = {
        'total_cost': total_cost,
        'email': email,
        'payment': payment,
        'PAYSTACK_PK': PAYSTACK_PK,
    }

    return render(request, 'payment/makepayment.html', context=context)