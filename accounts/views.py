from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .serializers import TelemedTokenObtainPairSerializer


class LoginView(TokenObtainPairView):
    serializer_class = TelemedTokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    pass
