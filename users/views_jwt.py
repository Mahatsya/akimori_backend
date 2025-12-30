from rest_framework_simplejwt.views import TokenObtainPairView
from .jwt import ActiveUserTokenObtainPairSerializer


class ActiveUserTokenObtainPairView(TokenObtainPairView):
    serializer_class = ActiveUserTokenObtainPairSerializer
