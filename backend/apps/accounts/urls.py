from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("me/travellers", views.TravellerViewSet, basename="traveller")

urlpatterns = [
    path("auth/register", views.RegisterView.as_view(), name="register"),
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/refresh", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("me", views.MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
