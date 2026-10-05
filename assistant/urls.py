from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("playground/", views.PlaygroundPageView.as_view(), name="playground"),
    path("chat/", views.PlaygroundChatView.as_view(), name="chat"),
    path("reset/", views.PlaygroundResetView.as_view(), name="reset"),
]
