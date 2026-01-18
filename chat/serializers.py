from __future__ import annotations

from rest_framework import serializers

from chat.models import ChatTurn


class ChatRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)
    context = serializers.DictField(required=False)

    def validate(self, attrs):
        ctx = attrs.get("context") or {}
        # Accept multiple possible keys from frontend context
        challenge_id = ctx.get("challenge_id") or ctx.get("challenge") or ctx.get("challengeId")
        if challenge_id is None:
            raise serializers.ValidationError({"context": "context.challenge_id is required."})

        try:
            challenge_id = int(challenge_id)
        except Exception:
            raise serializers.ValidationError({"context": "challenge_id must be an integer."})

        if challenge_id <= 0:
            raise serializers.ValidationError({"context": "challenge_id must be a positive integer."})

        attrs["challenge_id"] = challenge_id
        attrs["context"] = ctx
        return attrs


class ChatResponseSerializer(serializers.Serializer):
    reply = serializers.CharField()
    id = serializers.CharField(required=False)
    created_at = serializers.CharField(required=False)
    percent_on_track = serializers.IntegerField(min_value=0, max_value=100, required=False)


class ChatHistoryQuerySerializer(serializers.Serializer):
    challenge_id = serializers.IntegerField(min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class ChatTurnHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatTurn
        fields = ("id", "role", "content", "created_at", "meta")
