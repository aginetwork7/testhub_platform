from django.contrib import admin
from .models import MetaProject, MetaProjectMember, ProjectModule


@admin.register(MetaProject)
class MetaProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'owner', 'created_at', 'updated_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(MetaProjectMember)
class MetaProjectMemberAdmin(admin.ModelAdmin):
    list_display = ['meta_project', 'user', 'role', 'joined_at']
    list_filter = ['role']
    search_fields = ['meta_project__name', 'user__username']


@admin.register(ProjectModule)
class ProjectModuleAdmin(admin.ModelAdmin):
    list_display = ['meta_project', 'module_type', 'created_at', 'updated_at']
    list_filter = ['module_type']
    search_fields = ['meta_project__name']
    readonly_fields = ['created_at', 'updated_at']
