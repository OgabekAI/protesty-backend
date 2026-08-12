from django.urls import path
from .views import UserProfileView, SubjectListView

app_name = 'users'

urlpatterns = [
    path('users/me/', UserProfileView.as_view(), name='user-me'),
    path('subjects/', SubjectListView.as_view(), name='subject-list'),
]
