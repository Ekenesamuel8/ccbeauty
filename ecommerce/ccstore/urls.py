
from django.urls import path

from . import views

urlpatterns = [
    path('', views.store, name='store'), #store page

    path('product/<slug:product_slug>/', views.product_info, name='product_info'), #product info page

    path('search/<slug:category_slug>/', views.pdt_category, name='pdt_category'), #category page

    path('search/', views.search, name='search'),  # Search results page
]