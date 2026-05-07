"""Admin Mixins"""
from django.contrib import messages
from django.conf import settings


class DeleteLimitMixin:
    """删除数量限制Mixin"""
    
    def get_deleted_objects(self, objs, request):
        """获取要删除的对象，并检查数量限制"""
        max_delete_count = getattr(settings, 'DATA_UPLOAD_MAX_NUMBER_FIELDS', 10000)
        
        if len(objs) > max_delete_count:
            messages.error(request, f'最大删除条数不能超过{max_delete_count}条，请减少选择数量后重试。')
            return []
        
        return super().get_deleted_objects(objs, request)


class PaginationMixin:
    """翻页配置Mixin"""
    
    list_per_page = 15
    list_max_show_all = 100
    
    def get_list_per_page(self):
        """获取每页显示条数"""
        return self.list_per_page
    
    def get_list_max_show_all(self):
        """获取最大显示全部条数"""
        return self.list_max_show_all


class StandardAdminMixin(DeleteLimitMixin, PaginationMixin):
    """标准Admin Mixin，包含删除限制和翻页配置"""
    pass
