from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import AgentModelConfig
from .serializers import AgentModelConfigSerializer


class AgentModelConfigViewSet(viewsets.ModelViewSet):
    """Dedicated Chat and Agent model configuration, separate from AI mode settings."""

    queryset = AgentModelConfig.objects.all()
    serializer_class = AgentModelConfigSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = AgentModelConfig.objects.all()
        role = self.request.query_params.get('role')
        return queryset.filter(role=role) if role else queryset

    def perform_create(self, serializer):
        role = serializer.validated_data['role']
        if serializer.validated_data.get('is_active', True):
            AgentModelConfig.objects.filter(role=role).update(is_active=False)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        role = serializer.validated_data.get('role', serializer.instance.role)
        if serializer.validated_data.get('is_active', serializer.instance.is_active):
            AgentModelConfig.objects.filter(role=role).exclude(pk=serializer.instance.pk).update(is_active=False)
        serializer.save()