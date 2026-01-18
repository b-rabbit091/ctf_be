from rest_framework import serializers

from .models import Blog


class BlogSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Blog
        fields = ["id", "title", "slug", "content", "cover_image", "cover_image_url", "author", "author_username", "created_at", "updated_at"]
        read_only_fields = ["id", "slug", "author", "created_at", "updated_at"]

    def get_cover_image_url(self, obj):
        request = self.context.get("request")
        if obj.cover_image and request:
            return request.build_absolute_uri(obj.cover_image.url)
        return None
