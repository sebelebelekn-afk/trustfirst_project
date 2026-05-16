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
    path('api/liveness/submit/', api_views.submit_liveness, name='api_liveness'),
    path('sw.js', TemplateView.as_view(
        template_name='core/sw.js',
        content_type='application/javascript'
    ), name='sw'),
    path('manifest.json', TemplateView.as_view(
        template_name='core/manifest.json',
        content_type='application/manifest+json'
    ), name='manifest'),
path('api/giphy/search/', api_views.giphy_search, name='api_giphy'),
]