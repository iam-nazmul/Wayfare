from django.urls import path

from . import views

urlpatterns = [
    path("collect", views.CollectView.as_view(), name="collect"),
]
