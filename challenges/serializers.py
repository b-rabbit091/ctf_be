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
    category =  CategorySerializer()
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