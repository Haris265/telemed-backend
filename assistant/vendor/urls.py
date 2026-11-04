from django.urls import path

from . import views

app_name = "vendor"

# Register with and without trailing slash so vendor POST never hits APPEND_SLASH 500.
urlpatterns = [
    path(
        "parent/ai-reply/",
        views.ParentAiReplyView.as_view(),
        name="parent-ai-reply",
    ),
    path(
        "parent/ai-reply",
        views.ParentAiReplyView.as_view(),
        name="parent-ai-reply-noslash",
    ),
    path(
        "clinic/ai-reply/",
        views.ClinicAiReplyView.as_view(),
        name="clinic-ai-reply",
    ),
    path(
        "clinic/ai-reply",
        views.ClinicAiReplyView.as_view(),
        name="clinic-ai-reply-noslash",
    ),
]
