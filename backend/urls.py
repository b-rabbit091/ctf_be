from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="CTF Platform API",
        default_version="v1",
        description="API documentation for the Capture The Flag learning platform",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="support@ctfplatform.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)
urlpatterns = [
    # path('admin/', admin.site.urls),
    path("ctf/api/users/", include("users.urls")),
    path("ctf/api/challenges/", include("challenges.urls")),  # challenge endpoints
    path("ctf/api/submissions/", include("submissions.urls")),  # challenge endpoints
    path("ctf/api/blogs/", include("blogs.urls")),
    path("ctf/api/dashboard/", include("dashboard.urls")),
    path("ctf/api/chat/", include("chat.urls")),
    re_path(r"^swagger(?P<format>\.json|\.yaml)$", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    path("ctf/swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("ctf/redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
