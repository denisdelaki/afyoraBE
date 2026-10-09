from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from core.utils import check_module_permission


class IsClinicianAuthorizedForClinicalAI(BasePermission):
    """
    DRF Permission class enforcing facility tenancy, active user status, and RBAC module permission.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        if not getattr(request.user, 'facility', None):
            raise PermissionDenied("Your account is not assigned to a facility.")

        # Evaluate module permission (EHR or clinical_ai)
        check_module_permission(request.user, 'ehr', request=request)
        return True
