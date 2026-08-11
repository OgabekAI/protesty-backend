from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Test, Question, UserTestResult
from .serializers import (
    TestSerializer,
    QuestionSerializer,
    SubmitTestSerializer,
    UserTestResultSerializer
)
from .permissions import IsContentManagerOrAdmin, IsContentManagerOrReadOnly


class TestViewSet(viewsets.ModelViewSet):
    """
    API for managing and viewing tests:
    - Content Managers & Admins: Create, edit, delete, publish tests.
    - Students: List and view published tests.
    """
    queryset = Test.objects.all().prefetch_related('questions__options')
    serializer_class = TestSerializer
    permission_classes = [IsContentManagerOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # If user is not Content Manager/Admin, show only published tests
        is_staff_or_cm = user.is_authenticated and (
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_staff', False) or
            getattr(user, 'role', None) in ['ADMIN', 'CONTENT_MANAGER', 'admin', 'content_manager']
        )

        if not is_staff_or_cm:
            queryset = queryset.filter(is_published=True)

        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        subcategory = self.request.query_params.get('subcategory')
        if subcategory:
            queryset = queryset.filter(subcategory__icontains=subcategory)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user if self.request.user.is_authenticated else None)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        is_staff_or_cm = user.is_authenticated and (
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_staff', False) or
            getattr(user, 'role', None) in ['ADMIN', 'CONTENT_MANAGER', 'admin', 'content_manager']
        )

        # Hide correct answers from options when student views questions
        if not is_staff_or_cm:
            context['hide_correct'] = True

        return context

    @action(detail=True, methods=['post', 'patch'], permission_classes=[IsContentManagerOrAdmin])
    def publish(self, request, pk=None):
        """
        Allows Content Manager / Admin to directly publish a test without approval.
        """
        test = self.get_object()
        test.is_published = True
        test.save()
        return Response({
            "message": "Test muvaffaqiyatli nashr qilindi (published).",
            "test": TestSerializer(test, context=self.get_serializer_context()).data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post', 'patch'], permission_classes=[IsContentManagerOrAdmin])
    def unpublish(self, request, pk=None):
        """
        Allows Content Manager / Admin to unpublish a test.
        """
        test = self.get_object()
        test.is_published = False
        test.save()
        return Response({
            "message": "Test nashrdan olindi (unpublished).",
            "test": TestSerializer(test, context=self.get_serializer_context()).data
        }, status=status.HTTP_200_OK)


class QuestionViewSet(viewsets.ModelViewSet):
    """
    API for managing questions (Content Manager / Admin CRUD).
    """
    queryset = Question.objects.all().prefetch_related('options')
    serializer_class = QuestionSerializer
    permission_classes = [IsContentManagerOrAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()
        test_id = self.request.query_params.get('test_id')
        if test_id:
            queryset = queryset.filter(test_id=test_id)
        return queryset


class UserTestResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API for test submissions and viewing results history:
    - POST /api/v1/results/ : Submit test answers and get score + result
    - GET /api/v1/results/ : Recent results history for logged-in user
    - GET /api/v1/results/{id}/ : Detailed result review (question breakdown)
    """
    serializer_class = UserTestResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return UserTestResult.objects.none()
        
        # Staff/Admin can view all results if needed, normal users view own
        is_staff_or_cm = (
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_staff', False) or
            getattr(user, 'role', None) in ['ADMIN', 'CONTENT_MANAGER', 'admin', 'content_manager']
        )
        if is_staff_or_cm and self.request.query_params.get('all') == 'true':
            return UserTestResult.objects.all().prefetch_related('answers_breakdown__question__options')

        return UserTestResult.objects.filter(user=user).prefetch_related('answers_breakdown__question__options')

    def create(self, request, *args, **kwargs):
        """
        Submit a test attempt and calculate score.
        """
        serializer = SubmitTestSerializer(data=request.data, context={'request': request})
        serializer.is_validate_or_400 = True
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        result_serializer = UserTestResultSerializer(result, context={'request': request})
        return Response(result_serializer.data, status=status.HTTP_201_CREATED)
