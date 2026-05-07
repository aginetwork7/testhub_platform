from django.urls import path
from . import views
from . import import_views

urlpatterns = [
    # 导入相关
    path('import/template/', import_views.TestCaseImportTemplateView.as_view(), name='testcase-import-template'),
    path('import/upload/', import_views.TestCaseImportUploadView.as_view(), name='testcase-import-upload'),
    path('import/records/', import_views.TestCaseImportRecordListView.as_view(), name='testcase-import-records'),

    # 测试用例相关
    path('', views.TestCaseListCreateView.as_view(), name='testcase-list'),
    path('<int:pk>/', views.TestCaseDetailView.as_view(), name='testcase-detail'),
]