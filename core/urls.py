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

    # Real pages at real URLs, so they can be linked, shared and indexed. These
    # must come before the catch-all share routes at the bottom of this file,
    # or /privacy/ would be read as somebody's profile.
    path('privacy/', views.legal_page, {'page': 'privacy'}, name='legal_privacy'),
    path('terms/', views.legal_page, {'page': 'terms'}, name='legal_terms'),
    path('cookies/', views.legal_page, {'page': 'cookies'}, name='legal_cookies'),
    path('accessibility/', views.legal_page, {'page': 'accessibility'}, name='legal_accessibility'),
    path('help/', views.legal_page, {'page': 'help'}, name='legal_help'),

    # A permanent address for the Android build, so a shared link never rots and
    # the marketing site never needs editing when a new APK is uploaded.
    path('download/android/', views.download_android, name='download_android'),
    path('download/status.json', views.download_status, name='download_status'),

    path('api/config/', api_views.get_config, name='api_config'),
    path('api/upload/sign/', api_views.r2_sign_upload, name='api_upload_sign'),
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
    path('api/push/test/', api_views.push_test, name='api_push_test'),
    path('api/live/token/', api_views.livekit_token, name='api_live_token'),
    path('api/eddie/post/', api_views.eddie_post, name='api_eddie_post'),
    path('api/auth/username-login/', api_views.username_login, name='api_username_login'),

    # Wallet top-ups. The checkout is opened here, the money is added only by
    # the webhook, and the status endpoint is how the app finds out whether a
    # payment landed after the person is sent back from Yoco.
    path('api/wallet/create-checkout/', api_views.wallet_create_checkout, name='api_wallet_checkout'),
    path('api/wallet/yoco-webhook/', api_views.wallet_yoco_webhook, name='api_wallet_yoco_webhook'),
    path('api/wallet/deposit-status/', api_views.wallet_deposit_status, name='api_wallet_deposit_status'),
    # Run once per mode, by an admin, to tell Yoco where to deliver events.
    path('api/wallet/register-yoco-webhook/', api_views.wallet_register_yoco_webhook, name='api_wallet_register_hook'),
    path('sw.js', views.service_worker, name='sw'),
    path('manifest.json', views.manifest, name='manifest'),
path('api/giphy/search/', api_views.giphy_search, name='api_giphy'),
    path('api/music/search/', api_views.music_search, name='api_music'),

    # Shared links. The app is a single page, so these all serve the same
    # template and the client reads the path on boot to open what was shared.
    # Without them a copied link 404'd instead of opening the post.
    path('post/<str:target_id>/', views.feed, name='post_permalink'),
    path('clip/<str:target_id>/', views.feed, name='clip_permalink'),
    path('profile/<str:username>/', views.feed, name='profile_permalink'),
]