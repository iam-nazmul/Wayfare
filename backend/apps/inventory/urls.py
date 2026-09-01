from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

ops_router = DefaultRouter()
ops_router.register("ops/schedules", views.OpsScheduleViewSet, basename="ops-schedule")
ops_router.register("ops/routes", views.OpsRouteViewSet, basename="ops-route")
ops_router.register("ops/seat-maps", views.OpsSeatMapTemplateViewSet, basename="ops-seatmap")
ops_router.register("ops/flights", views.OpsFlightViewSet, basename="ops-flight")

urlpatterns = [
    path(
        "flights/<uuid:public_id>/seatmap",
        views.FlightSeatMapView.as_view(),
        name="flight-seatmap",
    ),
    path(
        "ops/flights/<uuid:public_id>/manifest",
        views.OpsFlightManifestView.as_view(),
        name="ops-flight-manifest",
    ),
    path("", include(ops_router.urls)),
]
