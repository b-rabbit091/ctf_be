# challenges/serializers.py
from rest_framework import serializers
from .models import Challenge, Category, Difficulty, SolutionType


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

    class Meta:
        model = Challenge
        fields = [
            'title', 'description', 'constraints', 'input_format',
            'output_format', 'sample_input', 'sample_output',
            'category', 'difficulty', 'solution_type'
        ]


from rest_framework import serializers
from .models import Challenge, FlagSolution, TextSolution, Category, Difficulty, SolutionType


class ChallengeCreateSerializer(serializers.ModelSerializer):
    flag_solution = serializers.CharField(required=False, allow_blank=True)
    procedure_solution = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Challenge
        fields = [
            "title", "description", "constraints", "input_format", "output_format",
            "sample_input", "sample_output", "category", "difficulty",
            "solution_type", "question_type", "files",
            "flag_solution", "procedure_solution"
        ]

    def create(self, validated_data):
        flag_value = validated_data.pop("flag_solution", None)
        procedure_content = validated_data.pop("procedure_solution", None)

        request = self.context.get("request")
        if request and request.user:
            validated_data["author"] = request.user

        challenge = Challenge.objects.create(**validated_data)

        if flag_value:
            flag_obj = FlagSolution.objects.filter(value=flag_value)
            if not flag_obj.exists():
                flag_obj = FlagSolution.objects.create(value=flag_value)
            else:
                flag_obj = flag_obj.first()
            flag_obj.challenges.add(challenge)

        if procedure_content:
            text_obj = TextSolution.objects.filter(content=procedure_content)
            if not text_obj.exists():
                text_obj = TextSolution.objects.create(content=procedure_content)
            else:
                text_obj = text_obj.first()
            text_obj.challenges.add(challenge)

        return challenge
