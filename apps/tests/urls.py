from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TestViewSet, QuestionViewSet, UserTestResultViewSet

router = DefaultRouter()
router.register(r'tests', TestViewSet, basename='tests')
router.register(r'questions', QuestionViewSet, basename='questions')
router.register(r'results', UserTestResultViewSet, basename='results')

urlpatterns = [
    path('', include(router.urls)),
]
