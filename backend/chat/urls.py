from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("health/live/", views.live, name="health-live"),
    path("conversations/", views.ConversationListCreate.as_view(), name="conversation-list"),
    path("conversations/<int:pk>/", views.ConversationDetail.as_view(), name="conversation-detail"),
    path("chat/", views.chat, name="chat"),
]
