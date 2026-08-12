from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Subject
from .serializers import UserSerializer, UserProfileUpdateSerializer, SubjectSerializer


class UserProfileView(APIView):
    """
    GET /api/v1/users/me/ - Retrieve current user profile.
    PATCH /api/v1/users/me/ - Update current user profile.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Return full updated user details
        full_serializer = UserSerializer(request.user)
        return Response(full_serializer.data, status=status.HTTP_200_OK)


class SubjectListView(APIView):
    """
    GET /api/v1/subjects/ - List active subjects for user selection.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        subjects = Subject.objects.filter(is_active=True)
        serializer = SubjectSerializer(subjects, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
