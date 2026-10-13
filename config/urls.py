from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from billing.urls import clinic_urlpatterns, superadmin_urlpatterns
from catalog.urls import doctor_urlpatterns

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/admin/", include("catalog.urls")),
    path("api/doctor/", include((doctor_urlpatterns, "doctor"))),
    path("api/patient/", include("patients.urls")),
    path("api/whatsapp/", include("whatsapp.urls")),
    path("api/assistant/", include("assistant.urls")),
    path("api/superadmin/", include((superadmin_urlpatterns, "superadmin"))),
    path("api/clinic/", include((clinic_urlpatterns, "clinic"))),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
