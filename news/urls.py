from django.urls import path

from . import views


app_name = "news"

urlpatterns = [
    path("", views.index, name="index"),
    path("api/audio/<slug:article_id>/", views.article_audio, name="article_audio"),
]
