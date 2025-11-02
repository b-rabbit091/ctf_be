from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from challenges.permissions import IsAdminOrReadOnly
from .models import Blog
from .serializers import BlogSerializer


class BlogViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for Blog.
    Admins can create, edit, delete.
    Users can only read.
    """
    queryset = Blog.objects.all().order_by('-created_at')
    serializer_class = BlogSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def perform_create(self, serializer):
        # Automatically assign current user as author
        serializer.save(author=self.request.user)

