from django.urls import path
from .views import (
    MetaProjectListView,
    MetaProjectDetailView,
    MetaProjectModulesView,
    ProjectModuleDetailView
)

app_name = 'unified_projects'

urlpatterns = [
    path('', MetaProjectListView.as_view(), name='meta-project-list'),
    path('<int:pk>/', MetaProjectDetailView.as_view(), name='meta-project-detail'),
    path('<int:pk>/modules/', MetaProjectModulesView.as_view(), name='meta-project-modules'),
    path('<int:pk>/modules/<str:module_type>/', ProjectModuleDetailView.as_view(), name='meta-project-module-detail'),
]
