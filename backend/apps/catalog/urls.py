from django.urls import path

from . import views

urlpatterns = [
    path("airports", views.AirportListView.as_view(), name="airport-list"),
    path("airlines", views.AirlineListView.as_view(), name="airline-list"),
    path("aircraft", views.AircraftListView.as_view(), name="aircraft-list"),
    path("currencies", views.CurrencyListView.as_view(), name="currency-list"),
]
