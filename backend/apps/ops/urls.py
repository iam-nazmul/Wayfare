from django.urls import path

from . import views

urlpatterns = [
    path(
        "bookings/<str:pnr>/rebook-options",
        views.RebookOptionListView.as_view(),
        name="rebook-option-list",
    ),
    path("bookings/<str:pnr>/rebook", views.RebookView.as_view(), name="booking-rebook"),
    path("ops/disruptions", views.OpsDisruptionListView.as_view(), name="ops-disruption-list"),
]
