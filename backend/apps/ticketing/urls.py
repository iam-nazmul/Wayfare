from django.urls import path

from . import views

urlpatterns = [
    path(
        "bookings/<str:pnr>/tickets",
        views.BookingTicketListView.as_view(),
        name="booking-ticket-list",
    ),
]
