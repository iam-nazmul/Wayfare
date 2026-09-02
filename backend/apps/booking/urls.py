from django.urls import path

from . import views

urlpatterns = [
    path("search/flights", views.FlightSearchView.as_view(), name="search-flights"),
    path(
        "search/flights/<uuid:search_id>/offers",
        views.SearchOffersView.as_view(),
        name="search-offers",
    ),
    path("search/calendar", views.FareCalendarView.as_view(), name="search-calendar"),
    path("offers/<uuid:offer_id>", views.OfferDetailView.as_view(), name="offer-detail"),
    path("me/bookings", views.MyBookingsView.as_view(), name="my-bookings"),
    path("bookings", views.BookingCreateView.as_view(), name="booking-create"),
    path("bookings/<str:pnr>", views.BookingDetailView.as_view(), name="booking-detail"),
    path("bookings/<str:pnr>/cancel", views.BookingCancelView.as_view(), name="booking-cancel"),
    path(
        "bookings/<str:pnr>/change/quote",
        views.BookingChangeQuoteView.as_view(),
        name="booking-change-quote",
    ),
    path(
        "bookings/<str:pnr>/change/confirm",
        views.BookingChangeConfirmView.as_view(),
        name="booking-change-confirm",
    ),
]
