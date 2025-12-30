from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import exceptions


class ActiveUserTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if not user.is_active:
            raise exceptions.AuthenticationFailed("Email is not verified")
        return data
