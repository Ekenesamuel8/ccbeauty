from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User, auth
from django.contrib.auth import authenticate, login

from django.contrib.sites.shortcuts import get_current_site
from urllib3 import request

from .token import user_tokenizer_generate

from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from .form import RegisterForm, LoginForm, UpdateUserForm, UserProfileForm
from payment.form import AddressForm
from payment.models import RegisterAddress

from django.contrib.auth.decorators import login_required

from django.contrib import messages
from payment.models import Order, RegisterAddress, OrderItem

from .models import UserProfile
from django_ratelimit.decorators import ratelimit
from axes.decorators import axes_dispatch

def register(request):

    form = RegisterForm()
    #creating an instance of the RegisterForm class

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        #creating an instance of the RegisterForm class with the data from the form

        if form.is_valid():
            user = form.save()
            
            user.is_active = False

            user.save()

            #sending the email verification email
            current_site = get_current_site(request)
            #getting the current site name

            subject = 'account verification email'
            #setting the subject of the email

            message = render_to_string('account/registration/email_verification.html', {
                'user': user,
                'domain': current_site.domain,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'token': user_tokenizer_generate.make_token(user),
            })
            #creating the message of the email

            user.email_user(subject=subject, message=message)

            return redirect("email_verification_sent")
            #redirecting to the email_verification_sent page
        
    context = {'form': form}
    #passing the form to the context dictionary

    return render(request, 'account/registration/register.html', context)
    #render the register.html template with the context dictionary



def email_verification(request, uidb64, token):
    
    unique_id = force_str(urlsafe_base64_decode(uidb64))
    #decoding the unique id
    user = User.objects.get(pk=unique_id) 
    #getting the user with the unique id

    if user_tokenizer_generate.check_token(user, token):
        #check if the user has  clicked the link in the email
        user.is_active = True
        #activating the user
        user.save()
        #saving the user
        return redirect("email_verification_success")
        #redirecting to the email_verification_success page

    else:
        return redirect("email_verification_failed")
        #redirecting to the email_verification_failed page
    
    


def email_verification_success(request):
    
    return render(request, 'account/registration/email_verification_success.html')


def email_verification_sent(request):
    
    return render(request, 'account/registration/email_verification_sent.html')


def email_verification_failed(request):
    
    return render(request, 'account/registration/email_verification_failed.html')

@ratelimit(key='post:username', rate='6/m', method='POST', block=True, group='login')  # 6 attempts per minute per username
@axes_dispatch
def login_view(request):

    form = LoginForm()

    if request.method == 'POST':
        print("POST request received, rate limit status:", getattr(request, 'limited', False))  # Debug
        form = LoginForm(request, data=request.POST)
        #creating an instance of the LoginForm class with the data from the form

        if form.is_valid():

            user = form.get_user()
            #getting the user from the form

            if user is not None:

                login(request, user)
                #logging in the user

                messages.success(request, 'You are now logged in')

                return redirect('store')
        else:
            print(form.errors)  # Debug: Print errors to console
            messages.error(request, 'Invalid username/email or password.')  # Show error to user
    else:
        form = LoginForm(request=request)  # Initialize with request for GET            
    context = {'form': form}
    #passing the form to the context dictionary

    return render(request, 'account/login.html', context=context)


def rate_limit_exceeded(request, exception):
    messages.error(request, 'Too many login attempts. Please try again in a minute.')
    return render(request, 'account/rate_limit_exceeded.html')


def logout(request):

    try:    

        for key in list(request.session.keys()):
            #iterating over the session keys
            if key == 'sess_key':
                #checking if the key is 'sess_key'
                continue
                #continue to the next iteration
            else:
                del request.session[key]
        #deleting the session keys
 
    except KeyError:
        pass
    messages.success(request, 'You are now logged out')

    return redirect('store')
    #redirecting to the store page

@login_required(login_url='login')
def dashboard(request):
    user_details = RegisterAddress.objects.filter(user=request.user).first()
    #getting the user details using the user id

    if user_details:
        address = user_details.address1 + ' ' + user_details.address2 + ' ' + user_details.city + ' ' + user_details.state + ' ' + user_details.zipcode
    else:
        address = None
        #if the user has not input his address, set the address to None

    profile_picture, created = UserProfile.objects.get_or_create(user=request.user)

    context = {
        'user_details' : user_details,
        'address': address,
        'profile_picture': profile_picture,
    }

    return render(request, 'account/dashboard.html', context=context)

@login_required(login_url='login')
def profile_account(request):

    user_form = UpdateUserForm(instance=request.user)
    #creating an instance of the UpdateUserForm class with the data from the form

    user_profile, created = UserProfile.objects.get_or_create(user=request.user)

    user_picture = UserProfileForm(instance=user_profile)

    if request.method == 'POST':
        if 'update_user' in request.POST:
            user_form = UpdateUserForm(request.POST, instance=request.user)
            #creating an instance of the UpdateUserForm class with the data from the form

            if user_form.is_valid():
                user_form.save()

                return redirect('dashboard')
            
        elif 'update_profile' in request.POST:
            user_picture = UserProfileForm(request.POST, request.FILES, instance=user_profile)
            #creating an instance of the UserProfileForm class with the data from the form

            if user_picture.is_valid():
                user_picture.save()

    context = {'user_form': user_form, 'user_picture': user_picture}
    
    return render(request, 'account/profile_account.html', context=context)

@login_required(login_url='login')
def delete_profile(request):

    user = User.objects.get(id=request.user.id)
    #getting the user with the id

    if request.method == 'POST':
        user.delete()
        #deleting the user

        return redirect('store')
        #redirecting to the store page
    
    return render(request, 'account/delete_profile.html')


@login_required(login_url='login')
def manage_shipping_address(request):

    try:

        address = RegisterAddress.objects.get(user=request.user.id)
        #getting the address of the user using the user id(if the user has input his address b4)

    except RegisterAddress.DoesNotExist:

        address = None

    form = AddressForm(instance=address)
    #creating an instance of the AddressForm class with the data from the form
    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        #creating an instance of the AddressForm class with the data from the form

        if form.is_valid():
            user_address = form.save(commit=False)
            #saving the form

            user_address.user = request.user
            #setting the user of the address to the current user

            user_address.save()
            #saving the address

            return redirect('dashboard')


    context = {'form': form}
    #passing the form to the context dictionary

    return render(request, 'account/manage_shipping_address.html', context=context)


@login_required(login_url='login')
def order_history(request):
    orders = Order.objects.filter(user=request.user)
    order_items = OrderItem.objects.filter(user=request.user)
    #getting all the orders of the user

    context = {
        'orders': orders,
        'order_items': order_items
    }

    return render(request, 'account/order_history.html', context=context)

