from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("", include("home.urls")),
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
    path("academy/", include("academy.urls")),
    path("news/", include("news.urls")),
    path("shop/", include("shop.urls", namespace="shop")),

    # CKEditor 5 (required for upload endpoint + related routes)
    path("ckeditor5/", include("django_ckeditor_5.urls")),
]

# Serve user-uploaded media in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)