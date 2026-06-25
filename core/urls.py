from django.urls import path
from django.views.generic import TemplateView
from django.contrib.staticfiles.views import serve as static_serve
from . import views
from . import api_views

urlpatterns = [
    path('', views.feed, name='feed'),
    path('api/config/', api_views.get_config, name='api_config'),
    path('api/stripe/create-verification/', api_views.create_stripe_verification, name='api_stripe_verification'),
    path('api/stripe/webhook/', api_views.stripe_webhook, name='api_stripe_webhook'),
    path('api/email/send/', api_views.send_email, name='api_email_send'),
    path('api/email/brevo/', api_views.send_email_brevo, name='api_email_brevo'),
    path('api/didit/create-verification/', api_views.didit_create_verification, name='api_didit_verify'),
    path('api/didit/webhook/', api_views.didit_webhook, name='api_didit_webhook'),
    path('api/translate/start/', api_views.elevenlabs_translate_start, name='api_translate_start'),
    path('api/translate/status/', api_views.elevenlabs_translate_status, name='api_translate_status'),
    path('api/translate/result/', api_views.elevenlabs_translate_result, name='api_translate_result'),
    path('api/liveness/submit/', api_views.submit_liveness, name='api_liveness'),
    path('sw.js', views.service_worker, name='sw'),
    path('manifest.json', views.manifest, name='manifest'),
path('api/giphy/search/', api_views.giphy_search, name='api_giphy'),
]