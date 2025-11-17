# challenges/serializers.py
from rest_framework import serializers
from .models import Challenge, Category, Difficulty, SolutionType, ChallengeFile
from .utils import validate_uploaded_file


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description']


class DifficultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Difficulty
        fields = ['id', 'level', 'description']


class SolutionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolutionType
        fields = ['id', 'type', 'description']


class ChallengeFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ChallengeFile
        fields = ["id", "url", "original_name", "mime_type", "size", "uploaded_at"]

    def get_url(self, obj):
        return obj.file.url if obj.file else None


class ChallengeListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    difficulty = DifficultySerializer(read_only=True)

    class Meta:
        model = Challenge
        fields = ['id', 'title', 'description', 'category', 'difficulty']


class ChallengeDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    difficulty = DifficultySerializer()
    solution_type = SolutionTypeSerializer()
    files = ChallengeFileSerializer(many=True, read_only=True)

    class Meta:
        model = Challenge
        fields = [
            'id', 'title', 'description', 'constraints', 'input_format',
            'output_format', 'sample_input', 'sample_output', 'files',
            'category', 'difficulty', 'solution_type']


class ChallengeUpdateSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.all(), required=False)
    difficulty = serializers.PrimaryKeyRelatedField(queryset=Difficulty.objects.all(), required=False)
    solution_type = serializers.PrimaryKeyRelatedField(queryset=SolutionType.objects.all(), required=False)
    uploaded_files = serializers.ListField(
        child=serializers.FileField(allow_empty_file=False, max_length=None),
        write_only=True,
        required=False,
        help_text="Multiple image/zip files to attach to this challenge.",
    )

    class Meta:
        model = Challenge
        fields = [
            'title', 'description', 'constraints', 'input_format',
            'output_format', 'sample_input', 'sample_output',
            'category', 'difficulty', 'solution_type', 'uploaded_files'
        ]

    def validate_uploaded_files(self, files):
        for f in files:
            validate_uploaded_file(f)
        return files

    def _save_files(self, challenge, files):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        for f in files:
            ChallengeFile.objects.create(
                challenge=challenge,
                file=f,
                original_name=f.name,
                mime_type=f.content_type,
                size=f.size,
                uploaded_by=user if user and user.is_authenticated else None,
            )

    def create(self, validated_data):
        files = validated_data.pop("uploaded_files", [])
        challenge = super().create(validated_data)
        if files:
            self._save_files(challenge, files)
        return challenge

    def update(self, instance, validated_data):
        files = validated_data.pop("uploaded_files", [])
        challenge = super().update(instance, validated_data)
        if files:
            # appending; if you want to replace, you could instance.files.all().delete() first
            self._save_files(challenge, files)
        return challenge
