"""
core/api_views.py
"""

import json
import os
import re
import uuid

import httpx
import stripe
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit


def _is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


def _verify_supabase_jwt(request):
    """Return decoded payload or raise ValueError."""
    import jwt as pyjwt
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        raise ValueError('missing')
    token = auth_header[7:]
    jwt_secret = os.environ.get('SUPABASE_JWT_SECRET', '')
    if not jwt_secret:
        raise ValueError('misconfigured')
    return pyjwt.decode(token, jwt_secret, algorithms=['HS256'], audience='authenticated')


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
    try:
        _verify_supabase_jwt(request)
    except ValueError as e:
        msg = str(e)
        if msg == 'misconfigured':
            return JsonResponse({'error': 'Server misconfigured'}, status=500)
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        body = json.loads(request.body or '{}')
        user_id = body.get('user_id', '')
        if not _is_valid_uuid(user_id):
            return JsonResponse({'error': 'Invalid user_id'}, status=400)

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

        if user_id and _is_valid_uuid(user_id):
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
        if not _is_valid_uuid(user_id):
            return JsonResponse({'error': 'Invalid user_id'}, status=400)

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


# ---------------------------------------------------------------------------
# 7. BREVO EMAIL (transactional email; key stays server-side)
# ---------------------------------------------------------------------------
@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@csrf_exempt
@require_http_methods(["POST"])
def send_email_brevo(request):
    try:
        _verify_supabase_jwt(request)
    except ValueError as e:
        if str(e) == 'misconfigured':
            return JsonResponse({'error': 'Server misconfigured'}, status=500)
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if not settings.BREVO_API_KEY:
        return JsonResponse({'error': 'Email not configured'}, status=500)

    try:
        body = json.loads(request.body or '{}')
        to = body.get('to', '')
        subject = body.get('subject', 'TrustFirst Notification')
        raw_html = body.get('html', '')

        if not to or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', to):
            return JsonResponse({'error': 'Invalid recipient'}, status=400)

        # Only allow a safe subset of HTML tags
        allowed = re.compile(r'<(?!\/?(b|i|u|p|br|h[1-6]|ul|ol|li|strong|em|a)\b)[^>]+>', re.IGNORECASE)
        html = allowed.sub('', raw_html)[:20000] or '<p></p>'

        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={
                'api-key': settings.BREVO_API_KEY,
                'Content-Type': 'application/json',
                'accept': 'application/json',
            },
            json={
                'sender': {'name': 'TrustFirst', 'email': 'noreply@trustfirst.app'},
                'to': [{'email': to}],
                'subject': subject,
                'htmlContent': html,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return JsonResponse({'ok': True})
        return JsonResponse({'error': 'Email failed'}, status=502)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


# ---------------------------------------------------------------------------
# 8. DIDIT IDENTITY VERIFICATION (blue badge — replaces Stripe Identity)
# ---------------------------------------------------------------------------
@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@csrf_exempt
@require_http_methods(["POST"])
def didit_create_verification(request):
    try:
        payload = _verify_supabase_jwt(request)
    except ValueError as e:
        if str(e) == 'misconfigured':
            return JsonResponse({'error': 'Server misconfigured'}, status=500)
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if not settings.DIDIT_API_KEY or not settings.DIDIT_WORKFLOW_ID:
        return JsonResponse({'error': 'Verification not configured (set DIDIT_WORKFLOW_ID)'}, status=500)

    user_id = payload.get('sub')
    if not _is_valid_uuid(user_id):
        return JsonResponse({'error': 'Invalid user'}, status=400)

    try:
        callback = request.build_absolute_uri('/api/didit/webhook/')
        resp = requests.post(
            'https://verification.didit.me/v3/session/',
            headers={'x-api-key': settings.DIDIT_API_KEY, 'Content-Type': 'application/json'},
            json={
                'workflow_id': settings.DIDIT_WORKFLOW_ID,
                'vendor_data': user_id,
                'callback': callback,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return JsonResponse({
                'session_id': data.get('session_id'),
                'session_url': data.get('session_url') or data.get('url'),
            })
        return JsonResponse({'error': 'Could not start verification'}, status=502)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def didit_webhook(request):
    # Verify the webhook signature if a secret is configured (HMAC-SHA256 over the raw body)
    secret = os.environ.get('DIDIT_WEBHOOK_SECRET', '')
    if secret:
        import hmac as _hmac
        import hashlib as _hashlib
        sig = request.META.get('HTTP_X_SIGNATURE', '') or request.META.get('HTTP_X_DIDIT_SIGNATURE', '')
        expected = _hmac.new(secret.encode(), request.body, _hashlib.sha256).hexdigest()
        if not (sig and _hmac.compare_digest(sig, expected)):
            return JsonResponse({'error': 'Invalid signature'}, status=401)

    try:
        body = json.loads(request.body or '{}')
        status = (body.get('status') or body.get('decision') or '').lower()
        user_id = body.get('vendor_data')

        approved = status in ('approved', 'verified', 'completed', 'success')
        if approved and user_id and _is_valid_uuid(user_id):
            headers = {
                "apikey": settings.SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            }
            try:
                httpx.patch(
                    f"{settings.SUPABASE_URL}/rest/v1/users?id=eq.{user_id}",
                    headers=headers,
                    json={"verified": True, "badge_status": "verified", "badge_tier": "verify-blue"},
                    timeout=10,
                )
                httpx.patch(
                    f"{settings.SUPABASE_URL}/rest/v1/verification_applications?user_id=eq.{user_id}&badge_type=eq.blue&status=eq.pending",
                    headers=headers,
                    json={"status": "approved"},
                    timeout=10,
                )
            except Exception as ex:
                print(f"[Didit webhook] supabase patch error: {ex}")

        return JsonResponse({'status': 'ok'})
    except Exception:
        # Always return 200 so the provider doesn't keep retrying on a parse error
        return JsonResponse({'status': 'ok'})


# ---------------------------------------------------------------------------
# 9. ELEVENLABS DUBBING (translate a clip's audio to English; key server-side)
# ---------------------------------------------------------------------------
@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@csrf_exempt
@require_http_methods(["POST"])
def elevenlabs_translate_start(request):
    try:
        _verify_supabase_jwt(request)
    except ValueError as e:
        if str(e) == 'misconfigured':
            return JsonResponse({'error': 'Server misconfigured'}, status=500)
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if not settings.ELEVENLABS_API_KEY:
        return JsonResponse({'error': 'Translation not configured'}, status=500)

    try:
        body = json.loads(request.body or '{}')
        source_url = body.get('source_url', '')
        target_lang = (body.get('target_lang') or 'en')[:5]
        if not source_url or not source_url.startswith('http'):
            return JsonResponse({'error': 'Invalid source_url'}, status=400)

        resp = requests.post(
            'https://api.elevenlabs.io/v1/dubbing',
            headers={'xi-api-key': settings.ELEVENLABS_API_KEY},
            data={
                'source_url': source_url,
                'target_lang': target_lang,
                'source_lang': 'auto',
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return JsonResponse({
                'dubbing_id': data.get('dubbing_id'),
                'expected_duration_sec': data.get('expected_duration_sec'),
            })
        return JsonResponse({'error': 'Could not start translation'}, status=502)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


@require_http_methods(["GET"])
def elevenlabs_translate_status(request):
    try:
        _verify_supabase_jwt(request)
    except ValueError:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    dubbing_id = request.GET.get('id', '')[:80]
    if not dubbing_id:
        return JsonResponse({'error': 'Missing id'}, status=400)
    try:
        resp = requests.get(
            f'https://api.elevenlabs.io/v1/dubbing/{dubbing_id}',
            headers={'xi-api-key': settings.ELEVENLABS_API_KEY},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            status = data.get('status', 'dubbing')
            out = {'status': status}
            if status == 'dubbed':
                # Public URL the client can use to fetch the dubbed media
                out['result_url'] = request.build_absolute_uri(
                    f'/api/translate/result/?id={dubbing_id}&lang=en'
                )
            return JsonResponse(out)
        return JsonResponse({'error': 'Status check failed'}, status=502)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


@require_http_methods(["GET"])
def elevenlabs_translate_result(request):
    from django.http import StreamingHttpResponse
    dubbing_id = request.GET.get('id', '')[:80]
    lang = request.GET.get('lang', 'en')[:5]
    if not dubbing_id:
        return JsonResponse({'error': 'Missing id'}, status=400)
    try:
        upstream = requests.get(
            f'https://api.elevenlabs.io/v1/dubbing/{dubbing_id}/audio/{lang}',
            headers={'xi-api-key': settings.ELEVENLABS_API_KEY},
            stream=True,
            timeout=30,
        )
        if upstream.status_code != 200:
            return JsonResponse({'error': 'Result not ready'}, status=502)
        content_type = upstream.headers.get('Content-Type', 'video/mp4')
        return StreamingHttpResponse(
            upstream.iter_content(chunk_size=8192),
            content_type=content_type,
        )
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)
