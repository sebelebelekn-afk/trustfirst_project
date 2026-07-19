"""
core/eddie_image.py

Image generation for Eddie, via the OpenAI SDK.

Deliberately separate from eddie_views.py: chat and reasoning run on Claude,
image generation runs on OpenAI, and the two clients never mix in one call path.
Both keys are server-side only.

Generated images are uploaded to Supabase storage so they outlive the response
and can be shared; the endpoint returns a public URL, not raw base64.
"""

import base64
import json
import uuid

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .api_views import _verify_supabase_jwt, _is_valid_uuid
from .eddie_views import _consume, _limit_message, _sb_headers


def _openai_client():
    """OpenAI client, or None when no key is configured."""
    key = getattr(settings, 'OPENAI_API_KEY', '')
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        return None


def _extract_image(result):
    """Pull image bytes out of an images.generate result.

    Different image models default to different response shapes -- some return
    base64, some return a URL -- so handle both rather than assuming one.
    """
    data = getattr(result, 'data', None) or []
    if not data:
        return None, 'No image came back'
    item = data[0]

    b64 = getattr(item, 'b64_json', None)
    if b64:
        try:
            return base64.b64decode(b64), None
        except Exception:
            return None, 'Image data was unreadable'

    url = getattr(item, 'url', None)
    if url:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                return r.content, None
            return None, 'Could not download the generated image'
        except Exception:
            return None, 'Could not download the generated image'

    return None, 'No image came back'


def _upload_png(user_id, raw):
    """Store the image and return its public URL, or None."""
    path = 'eddie/%s/%s.png' % (user_id, uuid.uuid4().hex)
    try:
        headers = _sb_headers()
        headers['Content-Type'] = 'image/png'
        r = requests.post(
            settings.SUPABASE_URL + '/storage/v1/object/media/' + path,
            headers=headers,
            data=raw,
            timeout=30,
        )
        if r.status_code not in (200, 201):
            return None
        return settings.SUPABASE_URL + '/storage/v1/object/public/media/' + path
    except Exception:
        return None


@csrf_exempt
@ratelimit(key='ip', rate='6/m', method='POST', block=True)
@require_http_methods(["POST"])
def eddie_image(request):
    """Generate an image for Eddie. Counts against the daily image limit."""
    try:
        payload = _verify_supabase_jwt(request)
    except ValueError:
        return JsonResponse({'error': 'Sign in to use Eddie'}, status=401)
    user_id = payload.get('sub')
    if not _is_valid_uuid(user_id):
        return JsonResponse({'error': 'Invalid session'}, status=401)

    try:
        body = json.loads(request.body or b'{}')
    except Exception:
        return JsonResponse({'error': 'Bad request'}, status=400)

    prompt = (body.get('prompt') or '').strip()[:1000]
    if not prompt:
        return JsonResponse({'error': 'Describe the image you want'}, status=400)

    size = body.get('size') or '1024x1024'
    if size not in ('1024x1024', '1024x1536', '1536x1024'):
        size = '1024x1024'

    client = _openai_client()
    if client is None:
        return JsonResponse({
            'error': 'Image generation is not set up yet. The server needs an OPENAI_API_KEY.',
            'not_configured': True,
        }, status=503)

    # Charged before the call, so a failure can't be retried for free in a loop.
    allowed, info = _consume(user_id, images=1)
    if not allowed:
        return JsonResponse({
            'error': _limit_message(info.get('blocked_on')),
            'limit': info.get('blocked_on'),
        }, status=429)

    try:
        result = client.images.generate(
            model=getattr(settings, 'EDDIE_IMAGE_MODEL', 'gpt-image-1'),
            prompt=prompt,
            size=size,
            n=1,
        )
    except Exception as exc:
        return JsonResponse({'error': 'Could not make that image: ' + str(exc)[:180]}, status=502)

    raw, err = _extract_image(result)
    if err:
        return JsonResponse({'error': err}, status=502)

    url = _upload_png(user_id, raw)
    if not url:
        # Storage failed; hand back the bytes so the chat can still show it,
        # even though it won't survive a reload.
        return JsonResponse({
            'image_b64': base64.b64encode(raw).decode('ascii'),
            'stored': False,
            'prompt': prompt,
        })

    return JsonResponse({'url': url, 'stored': True, 'prompt': prompt})
