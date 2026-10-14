from django.urls import path

from . import views

superadmin_urlpatterns = [
    path("dashboard/", views.SuperadminDashboardView.as_view(), name="superadmin-dashboard"),
    path("packages/", views.PackageListCreateView.as_view(), name="superadmin-packages"),
    path(
        "packages/<uuid:uuid>/",
        views.PackageDetailView.as_view(),
        name="superadmin-package-detail",
    ),
    path("clinics/", views.SuperadminClinicListView.as_view(), name="superadmin-clinics"),
    path(
        "clinics/<int:pk>/",
        views.SuperadminClinicDetailView.as_view(),
        name="superadmin-clinic-detail",
    ),
    path(
        "clinic-admins/",
        views.ClinicAdminCreateView.as_view(),
        name="superadmin-clinic-admin-create",
    ),
    path(
        "purchase-requests/",
        views.PurchaseRequestListView.as_view(),
        name="superadmin-purchase-requests",
    ),
    path(
        "purchase-requests/<uuid:uuid>/approve/",
        views.PurchaseRequestApproveView.as_view(),
        name="superadmin-purchase-approve",
    ),
    path(
        "purchase-requests/<uuid:uuid>/reject/",
        views.PurchaseRequestRejectView.as_view(),
        name="superadmin-purchase-reject",
    ),
    path("assign/", views.DirectAssignView.as_view(), name="superadmin-assign"),
    path(
        "subscriptions/",
        views.SubscriptionListView.as_view(),
        name="superadmin-subscriptions",
    ),
    path("payments/", views.PaymentListView.as_view(), name="superadmin-payments"),
    path("ledger/", views.LedgerListView.as_view(), name="superadmin-ledger"),
    path(
        "ledger/adjustment/",
        views.LedgerAdjustmentView.as_view(),
        name="superadmin-ledger-adjustment",
    ),
]

clinic_urlpatterns = [
    path("me/", views.ClinicMeView.as_view(), name="clinic-me"),
    path("packages/", views.ClinicPackageListView.as_view(), name="clinic-packages"),
    path(
        "purchase-requests/",
        views.ClinicPurchaseRequestListCreateView.as_view(),
        name="clinic-purchase-requests",
    ),
    path(
        "subscriptions/",
        views.ClinicSubscriptionListView.as_view(),
        name="clinic-subscriptions",
    ),
    path("payments/", views.ClinicPaymentListView.as_view(), name="clinic-payments"),
    path("ledger/", views.ClinicLedgerListView.as_view(), name="clinic-ledger"),
    path("specialities/", views.ClinicSpecialityListView.as_view(), name="clinic-specialities"),
    path("doctors/", views.ClinicDoctorListView.as_view(), name="clinic-doctors"),
    path(
        "doctors/import/template/",
        views.ClinicDoctorImportTemplateView.as_view(),
        name="clinic-doctors-import-template",
    ),
    path(
        "doctors/import/",
        views.ClinicDoctorImportView.as_view(),
        name="clinic-doctors-import",
    ),
    path(
        "doctors/<uuid:uuid>/",
        views.ClinicDoctorDetailView.as_view(),
        name="clinic-doctor-detail",
    ),
    path(
        "appointments/",
        views.ClinicAppointmentListView.as_view(),
        name="clinic-appointments",
    ),
    path(
        "appointments/<int:pk>/",
        views.ClinicAppointmentDetailView.as_view(),
        name="clinic-appointment-detail",
    ),
]
