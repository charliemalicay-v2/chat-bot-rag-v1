from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("health/live/", views.live, name="health-live"),
]
