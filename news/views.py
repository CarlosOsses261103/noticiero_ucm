from django.http import JsonResponse
from django.shortcuts import render

from .services import get_broadcast_context, get_or_create_article_audio, media_url


def index(request):
    return render(request, "news/index.html", get_broadcast_context())


def article_audio(request, article_id):
    audio_path = get_or_create_article_audio(article_id)

    if audio_path is None:
        return JsonResponse(
            {
                "audio_generated": False,
                "audio_url": "",
                "error": "No se encontro la noticia solicitada.",
            },
            status=404,
        )

    return JsonResponse(
        {
            "audio_generated": True,
            "audio_url": media_url(audio_path),
        }
    )
