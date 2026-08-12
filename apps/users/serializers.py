from rest_framework import serializers
from .models import User, Subject, UserRole, UserStatus, Language, Gender


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name', 'code', 'is_active']
        read_only_fields = ['id', 'is_active']


class UserSerializer(serializers.ModelSerializer):
    prepared_subjects = SubjectSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'date_of_birth',
            'gender',
            'region',
            'language',
            'status',
            'role',
            'google_id',
            'telegram_id',
            'telegram_first_name',
            'avatar',
            'prepared_subjects',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'username',
            'status',
            'role',
            'google_id',
            'telegram_id',
            'created_at',
            'updated_at',
        ]


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    prepared_subjects = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.filter(is_active=True),
        many=True,
        required=False
    )

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'date_of_birth',
            'gender',
            'region',
            'language',
            'prepared_subjects',
            'avatar',
        ]

    def update(self, instance, validated_data):
        prepared_subjects = validated_data.pop('prepared_subjects', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if prepared_subjects is not None:
            instance.prepared_subjects.set(prepared_subjects)

        return instance
