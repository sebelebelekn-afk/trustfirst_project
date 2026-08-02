from django.urls import path
from django.views.generic import TemplateView
from django.contrib.staticfiles.views import serve as static_serve
from . import views
from . import api_views
from . import eddie_views
from . import eddie_image
from . import eddie_voice

urlpatterns = [
    path('', views.feed, name='feed'),
    path('api/config/', api_views.get_config, name='api_config'),
    path('api/eddie/chat/', eddie_views.eddie_chat, name='api_eddie_chat'),
    path('api/eddie/usage/', eddie_views.eddie_usage, name='api_eddie_usage'),
    path('api/eddie/history/', eddie_views.eddie_history, name='api_eddie_history'),
    path('api/eddie/conversation/', eddie_views.eddie_conversation, name='api_eddie_convo'),
    path('api/eddie/delete/', eddie_views.eddie_delete_conversation, name='api_eddie_delete'),
    path('api/eddie/image/', eddie_image.eddie_image, name='api_eddie_image'),
    path('api/eddie/mention/', eddie_views.eddie_mention, name='api_eddie_mention'),
    path('api/eddie/speak/', eddie_voice.eddie_speak, name='api_eddie_speak'),
    path('api/eddie/algorithm/', eddie_views.eddie_algorithm, name='api_eddie_algorithm'),
    path('api/stripe/create-verification/', api_views.create_stripe_verification, name='api_stripe_verification'),
    path('api/stripe/webhook/', api_views.stripe_webhook, name='api_stripe_webhook'),
    path('api/email/send/', api_views.send_email, name='api_email_send'),
    path('api/email/brevo/', api_views.send_email_brevo, name='api_email_brevo'),
    path('api/didit/create-verification/', api_views.didit_create_verification, name='api_didit_verify'),
    path('api/didit/webhook/', api_views.didit_webhook, name='api_didit_webhook'),
    path('api/translate/start/', api_views.elevenlabs_translate_start, name='api_translate_start'),
    path('api/translate/status/', api_views.elevenlabs_translate_status, name='api_translate_status'),
    path('api/translate/result/', api_views.elevenlabs_translate_result, name='api_translate_result'),
    path('api/transcribe/', api_views.elevenlabs_transcribe, name='api_transcribe'),
    path('api/translate-text/', api_views.translate_text, name='api_translate_text'),
    path('api/liveness/submit/', api_views.submit_liveness, name='api_liveness'),
    path('api/moderate/comment-image/', api_views.moderate_comment_image, name='api_moderate_comment_image'),
    path('api/live/token/', api_views.livekit_token, name='api_live_token'),
    path('sw.js', views.service_worker, name='sw'),
    path('manifest.json', views.manifest, name='manifest'),
path('api/giphy/search/', api_views.giphy_search, name='api_giphy'),
    path('api/music/search/', api_views.music_search, name='api_music'),
]