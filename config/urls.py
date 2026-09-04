from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve


urlpatterns = [
    path("", include("news.urls")),
]


# En desarrollo Django sirve los archivos multimedia normalmente.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )

# En Cloud Run usamos esta ruta para que sigan disponibles
# el video, las imágenes y los audios con DEBUG=False.
else:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]