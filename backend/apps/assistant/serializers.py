from rest_framework import serializers
from .models import AgentModelConfig, AssistantSession, AssistantMessage, ChatMessage


class AgentModelConfigSerializer(serializers.ModelSerializer):
    api_key_masked = serializers.SerializerMethodField()

    def get_api_key_masked(self, obj):
        if not obj.api_key:
            return ''
        return f'{obj.api_key[:8]}****'

    class Meta:
        model = AgentModelConfig
        fields = [
            'id', 'name', 'role', 'model_type', 'api_key', 'base_url', 'model_name',
            'api_key_masked', 'max_tokens', 'temperature', 'top_p', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
        extra_kwargs = {'api_key': {'write_only': True, 'required': False}}


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'created_at']
        read_only_fields = ['created_at']


class AssistantMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantMessage
        fields = ['id', 'message_type', 'content', 'created_at']


class AssistantSessionSerializer(serializers.ModelSerializer):
    messages = AssistantMessageSerializer(many=True, read_only=True)
    chat_messages = ChatMessageSerializer(many=True, read_only=True)
    
    class Meta:
        model = AssistantSession
        fields = ['id', 'session_id', 'title', 'created_at', 'updated_at', 'messages', 'chat_messages']


class AssistantSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantSession
        fields = ['session_id', 'title']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)