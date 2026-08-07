from django.urls import path

from appointments.views import (
    AdminAppointmentDetailView,
    AdminAppointmentListCreateView,
    AdminPatientDetailView,
    AdminPatientListView,
)

from .doctor_views import (
    DoctorAppointmentAttachmentDetailView,
    DoctorAppointmentAttachmentListCreateView,
    DoctorAppointmentDetailView,
    DoctorAppointmentEndVisitView,
    DoctorAppointmentListView,
    DoctorAppointmentStartVisitView,
    DoctorClinicAvailabilityListCreateView,
    DoctorClinicAvailabilityReplaceView,
    DoctorClinicDetailView,
    DoctorClinicListCreateView,
    DoctorClinicalNoteView,
    DoctorDashboardView,
    DoctorMeView,
    DoctorPatientDetailView,
    DoctorPatientListView,
    DoctorPrescriptionView,
)
from .views import (
    AdminDeactivateUnsubscribedDoctorsView,
    AdminDoctorAvailabilityListView,
    AdminSubscriptionDetailView,
    AdminSubscriptionListCreateView,
    ClinicDetailView,
    ClinicListCreateView,
    DashboardStatsView,
    DoctorAvailabilityDetailView,
    DoctorAvailabilityListCreateView,
    DoctorDetailView,
    DoctorListView,
    DoctorOnboardingView,
    SpecialityDetailView,
    SpecialityListCreateView,
)

urlpatterns = [
    path("dashboard/", DashboardStatsView.as_view(), name="admin-dashboard"),
    path("specialities/", SpecialityListCreateView.as_view(), name="admin-specialities"),
    path(
        "specialities/<int:pk>/",
        SpecialityDetailView.as_view(),
        name="admin-speciality-detail",
    ),
    path("clinics/", ClinicListCreateView.as_view(), name="admin-clinics"),
    path("clinics/<int:pk>/", ClinicDetailView.as_view(), name="admin-clinic-detail"),
    path("doctors/onboarding/", DoctorOnboardingView.as_view(), name="admin-doctor-onboard"),
    path("doctors/", DoctorListView.as_view(), name="admin-doctors"),
    path(
        "doctors/<uuid:uuid>/availability/",
        AdminDoctorAvailabilityListView.as_view(),
        name="admin-doctor-availability",
    ),
    path("doctors/<uuid:uuid>/", DoctorDetailView.as_view(), name="admin-doctor-detail"),
    path(
        "subscriptions/",
        AdminSubscriptionListCreateView.as_view(),
        name="admin-subscriptions",
    ),
    path(
        "subscriptions/deactivate-unsubscribed/",
        AdminDeactivateUnsubscribedDoctorsView.as_view(),
        name="admin-deactivate-unsubscribed",
    ),
    path(
        "subscriptions/<uuid:uuid>/",
        AdminSubscriptionDetailView.as_view(),
        name="admin-subscription-detail",
    ),
    path("patients/", AdminPatientListView.as_view(), name="admin-patients"),
    path(
        "patients/<uuid:uuid>/",
        AdminPatientDetailView.as_view(),
        name="admin-patient-detail",
    ),
    path("appointments/", AdminAppointmentListCreateView.as_view(), name="admin-appointments"),
    path(
        "appointments/<int:pk>/",
        AdminAppointmentDetailView.as_view(),
        name="admin-appointment-detail",
    ),
]

doctor_urlpatterns = [
    path("me/", DoctorMeView.as_view(), name="doctor-me"),
    path("dashboard/", DoctorDashboardView.as_view(), name="doctor-dashboard"),
    path("clinics/", DoctorClinicListCreateView.as_view(), name="doctor-clinics"),
    path(
        "clinics/<int:pk>/",
        DoctorClinicDetailView.as_view(),
        name="doctor-clinic-detail",
    ),
    path(
        "clinics/<int:pk>/availability/",
        DoctorClinicAvailabilityListCreateView.as_view(),
        name="doctor-clinic-availability",
    ),
    path(
        "clinics/<int:pk>/availability/replace/",
        DoctorClinicAvailabilityReplaceView.as_view(),
        name="doctor-clinic-availability-replace",
    ),
    path("availability/", DoctorAvailabilityListCreateView.as_view(), name="doctor-availability"),
    path(
        "availability/<int:pk>/",
        DoctorAvailabilityDetailView.as_view(),
        name="doctor-availability-detail",
    ),
    path("appointments/", DoctorAppointmentListView.as_view(), name="doctor-appointments"),
    path(
        "appointments/<int:pk>/",
        DoctorAppointmentDetailView.as_view(),
        name="doctor-appointment-detail",
    ),
    path(
        "appointments/<int:pk>/start/",
        DoctorAppointmentStartVisitView.as_view(),
        name="doctor-appointment-start",
    ),
    path(
        "appointments/<int:pk>/end/",
        DoctorAppointmentEndVisitView.as_view(),
        name="doctor-appointment-end",
    ),
    path(
        "appointments/<int:pk>/attachments/",
        DoctorAppointmentAttachmentListCreateView.as_view(),
        name="doctor-appointment-attachments",
    ),
    path(
        "appointments/<int:pk>/attachments/<int:attachment_id>/",
        DoctorAppointmentAttachmentDetailView.as_view(),
        name="doctor-appointment-attachment-detail",
    ),
    path(
        "appointments/<int:pk>/clinical/",
        DoctorClinicalNoteView.as_view(),
        name="doctor-appointment-clinical",
    ),
    path(
        "appointments/<int:pk>/prescription/",
        DoctorPrescriptionView.as_view(),
        name="doctor-appointment-prescription",
    ),
    path("patients/", DoctorPatientListView.as_view(), name="doctor-patients"),
    path(
        "patients/<uuid:uuid>/",
        DoctorPatientDetailView.as_view(),
        name="doctor-patient-detail",
    ),
]
