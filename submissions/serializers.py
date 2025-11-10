from rest_framework import serializers
from .models import UserFlagSubmission, UserTextSubmission, SubmissionStatus
from challenges.models import Challenge
from users.models import User

class UserFlagSubmissionSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source='user', write_only=True)
    challenge_id = serializers.PrimaryKeyRelatedField(queryset=Challenge.objects.all(), source='challenges', write_only=True)
    status = serializers.SlugRelatedField(slug_field='status', queryset=SubmissionStatus.objects.all())

    class Meta:
        model = UserFlagSubmission
        fields = ['id', 'user_id', 'challenge_id', 'value', 'status', 'updated_at']
        read_only_fields = ['id', 'updated_at']

    def create(self, validated_data):
        # Pop challenge for ManyToMany
        challenge = validated_data.pop('challenges')
        submission = UserFlagSubmission.objects.create(**validated_data)
        submission.challenges.add(challenge)
        return submission


class UserTextSubmissionSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), source='user', write_only=True)
    challenge_id = serializers.PrimaryKeyRelatedField(queryset=Challenge.objects.all(), source='challenges', write_only=True)
    status = serializers.SlugRelatedField(slug_field='status', queryset=SubmissionStatus.objects.all())

    class Meta:
        model = UserTextSubmission
        fields = ['id', 'user_id', 'challenge_id', 'content', 'status', 'updated_at']
        read_only_fields = ['id', 'updated_at']

    def create(self, validated_data):
        challenge = validated_data.pop('challenges')
        submission = UserTextSubmission.objects.create(**validated_data)
        submission.challenges.add(challenge)
        return submission
