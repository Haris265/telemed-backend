from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("playground/", views.PlaygroundPageView.as_view(), name="playground"),
    path("chat/", views.PlaygroundChatView.as_view(), name="chat"),
    path("reset/", views.PlaygroundResetView.as_view(), name="reset"),
    path(
        "parent/playground/",
        views.ParentPlaygroundPageView.as_view(),
        name="parent_playground",
    ),
    path("parent/chat/", views.ParentPlaygroundChatView.as_view(), name="parent_chat"),
    path(
        "parent/reset/",
        views.ParentPlaygroundResetView.as_view(),
        name="parent_reset",
    ),
]
