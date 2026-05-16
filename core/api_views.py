"""
core/api_views.py
"""

import json
import os
import re

import httpx
import stripe
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit


# ---------------------------------------------------------------------------
# 1. CONFIG ENDPOINT
# ---------------------------------------------------------------------------
@require_http_methods(["GET"])
def get_config(request):
    # Never expose server-side-only keys (GIPHY, service keys) here
    return JsonResponse({
        "supabase_url": settings.SUPABASE_URL,
        "supabase_anon_key": settings.SUPABASE_ANON_KEY,
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
    })


# ---------------------------------------------------------------------------
# 2. STRIPE IDENTITY — Create Verification Session
# ---------------------------------------------------------------------------
@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@csrf_exempt
@require_http_methods(["POST"])
def create_stripe_verification(request):
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        body = json.loads(request.body or '{}')
        user_id = body.get('user_id', '')

        session = stripe.identity.VerificationSession.create(
            type='document',
            metadata={'user_id': user_id},
            options={
                'document': {
                    'allowed_document_types': ['driving_license', 'passport', 'id_card'],
                    'require_id_number': False,
                    'require_live_capture': True,
                    'require_matching_selfie': True,
                }
            }
        )

        return JsonResponse({
            'client_secret': session.client_secret,
            'session_id': session.id,
        })

    except stripe.error.StripeError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


# ---------------------------------------------------------------------------
# 3. STRIPE IDENTITY — Webhook
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    if event['type'] == 'identity.verification_session.verified':
        session = event['data']['object']
        user_id = session.get('metadata', {}).get('user_id')
        session_id = session.get('id')

        if user_id:
            import httpx
            try:
                patch = httpx.patch(
                    f"{settings.SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                    headers={
                        "apikey": settings.SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                    json={"stripe_identity_id": session_id, "identity_verified": True},
                    timeout=10,
                )
                if patch.status_code not in (200, 204):
                    print(f"[Webhook] Supabase update failed: {patch.status_code}")
            except Exception as ex:
                print(f"[Webhook] Supabase patch error: {ex}")

    return JsonResponse({'status': 'ok'})


# ---------------------------------------------------------------------------
# 4. EMAIL — Send via Resend
# ---------------------------------------------------------------------------
@ratelimit(key='ip', rate='3/m', method='POST', block=True)
@csrf_exempt
@require_http_methods(["POST"])
def send_email(request):
    try:
        body = json.loads(request.body or '{}')
        to = body.get('to')
        subject = body.get('subject', 'TrustFirst Notification')
        raw_html = body.get('html', '')

        # Strip dangerous tags — never allow arbitrary HTML from client
        import html as html_module
        # Allow only a safe subset — sanitize by escaping then re-allowing safe tags
        ALLOWED_TAGS = re.compile(r'<(?!\/?(b|i|u|p|br|h[1-6]|ul|ol|li|strong|em|a)\b)[^>]+>', re.IGNORECASE)
        html = ALLOWED_TAGS.sub('', raw_html)
        # Cap length to prevent abuse
        html = html[:10000]

        if not to:
            return JsonResponse({'error': 'Missing recipient'}, status=400)
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', to):
            return JsonResponse({'error': 'Invalid email address'}, status=400)

        import jwt as pyjwt
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        token = auth_header[7:]
        jwt_secret = os.environ.get('SUPABASE_JWT_SECRET', '')
        if not jwt_secret:
            return JsonResponse({'error': 'Server misconfigured'}, status=500)

        try:
            pyjwt.decode(token, jwt_secret, algorithms=['HS256'], audience='authenticated')
        except pyjwt.ExpiredSignatureError:
            return JsonResponse({'error': 'Token expired'}, status=401)
        except pyjwt.PyJWTError:
            return JsonResponse({'error': 'Invalid token'}, status=401)

        resp = requests.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': f"Bearer {settings.RESEND_API_KEY}",
                'Content-Type': 'application/json',
            },
            json={
                'from': 'TrustFirst <noreply@trustfirst.app>',
                'to': [to],
                'subject': subject,
                'html': html,
            },
            timeout=10,
        )

        if resp.status_code == 200:
            return JsonResponse({'ok': True})
        else:
            return JsonResponse({'error': 'Email failed'}, status=502)

    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


# ---------------------------------------------------------------------------
# 5. LIVENESS — Submit base64 frame for spoof detection
# ---------------------------------------------------------------------------
@ratelimit(key='ip', rate='10/m', method='POST', block=True)
@csrf_exempt
@require_http_methods(["POST"])
def submit_liveness(request):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body or '{}')
        user_id = body.get('user_id', '')
        image_b64 = body.get('image_b64', '')

        if not image_b64 or not user_id:
            return JsonResponse({'error': 'Missing image_b64 or user_id'}, status=400)

        # Server tracks step count — never trust the client
        from django.core.cache import cache
        cache_key = f'liveness_steps:{user_id}'
        steps_done = cache.get(cache_key, 0) + 1
        cache.set(cache_key, steps_done, timeout=600)  # 10-minute session

        vision_key = settings.GOOGLE_CLOUD_VISION_API_KEY
        vision_url = f'https://vision.googleapis.com/v1/images:annotate?key={vision_key}'

        vision_payload = {
            "requests": [{
                "image": {"content": image_b64},
                "features": [{"type": "SAFE_SEARCH_DETECTION"}]
            }]
        }

        vision_resp = requests.post(vision_url, json=vision_payload, timeout=10)
        vision_data = vision_resp.json()

        safe_search = vision_data.get('responses', [{}])[0].get('safeSearchAnnotation', {})
        spoof_signal = safe_search.get('spoof', 'UNKNOWN')
        SPOOF_FAIL = {'LIKELY', 'VERY_LIKELY'}
        is_live = spoof_signal not in SPOOF_FAIL and steps_done >= 5

        if is_live:
            cache.delete(f'liveness_steps:{user_id}')  # Reset on success
            patch_resp = httpx.patch(
                f"{settings.SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                headers={
                    "apikey": settings.SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"liveness_verified": True, "liveness_steps": steps_done},
                timeout=10,
            )
            if patch_resp.status_code not in (200, 204):
                return JsonResponse({'error': 'Supabase update failed'}, status=502)

        return JsonResponse({'ok': True, 'verified': is_live})

    except requests.exceptions.Timeout:
        return JsonResponse({'error': 'Vision API timeout'}, status=504)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


# ---------------------------------------------------------------------------
# 6. GIPHY SEARCH PROXY (keeps API key server-side)
# ---------------------------------------------------------------------------
@ratelimit(key='ip', rate='20/m', method='GET', block=True)
@require_http_methods(["GET"])
def giphy_search(request):
    q = request.GET.get('q', '')[:100]
    if not q:
        return JsonResponse({'data': []})

    gif_type = request.GET.get('type', 'gifs')[:10]
    if gif_type not in ('gifs', 'stickers'):
        gif_type = 'gifs'
    action = 'search' if q else 'trending'
    resp = requests.get(
        f'https://api.giphy.com/v1/{gif_type}/{action}',
        params={
            'api_key': settings.GIPHY_API_KEY,
            'q': q or '',
            'limit': 21,
            'rating': 'g',
        },
        timeout=5,
    )

    if resp.status_code == 200:
        return JsonResponse(resp.json())
    return JsonResponse({'data': []}, status=502)
