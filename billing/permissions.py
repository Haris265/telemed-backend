from rest_framework.permissions import BasePermission

from accounts.permissions import IsClinicAdmin
from billing.services import clinic_access_state


class HasActiveClinicPackage(BasePermission):
    """
    Clinic admins may only mutate doctors/appointments when unlocked
    (active paid package, no pending offer/invoice).
    """

    message = "Clinic package is inactive or unpaid. Accept offer and pay invoice to unlock."

    def has_permission(self, request, view):
        if not IsClinicAdmin().has_permission(request, view):
            return False
        # Safe read methods still require unlock for ops endpoints
        clinic = request.user.clinic_admin_profile.clinic
        state = clinic_access_state(clinic)
        return not state["access_locked"]
