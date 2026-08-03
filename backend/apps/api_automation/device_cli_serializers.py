from rest_framework import serializers


class DeviceCliExecuteSerializer(serializers.Serializer):
    device_id = serializers.RegexField(regex=r'^[A-Za-z0-9_-]{1,128}$')
    operation = serializers.RegexField(regex=r'^[A-Za-z][A-Za-z0-9_]{0,63}$', required=False)
    arguments = serializers.DictField(child=serializers.CharField(), required=False, default=dict)
    command = serializers.CharField(max_length=4096, required=False, trim_whitespace=True)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=300, required=False)

    def validate(self, attrs):
        has_operation = bool(attrs.get('operation'))
        has_command = bool(attrs.get('command'))
        if has_operation and has_command:
            raise serializers.ValidationError('command 与 operation 不能同时提供。')
        if has_command and attrs.get('arguments'):
            raise serializers.ValidationError('直接 command 不支持 arguments。')
        return attrs