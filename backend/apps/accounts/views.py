from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .selectors import travellers_for
from .serializers import RegisterSerializer, TravellerSerializer, UserSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]  # public sign-up is the product's front door
    throttle_scope = "login"

    @extend_schema(
        request=RegisterSerializer, responses={201: UserSerializer}, tags=["auth"]
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """See ``TokenObtainPairView.post``; adds the login throttle scope."""

    permission_classes = [AllowAny]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    """See ``TokenRefreshView.post``; rotation and blacklisting are configured in SIMPLE_JWT."""

    permission_classes = [AllowAny]


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None}, tags=["auth"])
    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except (TokenError, AttributeError):
                pass  # already expired or blacklist app not installed — logout is still complete
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: UserSerializer}, tags=["accounts"])
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        request=UserSerializer, responses={200: UserSerializer}, tags=["accounts"]
    )
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


@extend_schema(tags=["accounts"])
class TravellerViewSet(viewsets.ModelViewSet):
    serializer_class = TravellerSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "public_id"

    def get_queryset(self):
        return travellers_for(self.request.user)

    def perform_create(self, serializer) -> None:
        serializer.save(user=self.request.user)
