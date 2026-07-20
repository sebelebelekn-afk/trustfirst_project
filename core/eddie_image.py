"""
core/eddie_image.py

Image generation for Eddie.

Deliberately separate from eddie_views.py: chat and image generation are
different providers on different accounts, and the two never mix in one call
path. Every key here is server-side only.

Three backends, in the order they are picked when nothing is configured:

  pollinations  no key, no account, no setup. The floor that keeps image
                generation working on a non-profit's budget.
  cloudflare    Workers AI, 10,000 neurons a day free. Better quality and an
                actual account behind it, once someone has 10 minutes.
  openai        gpt-image-1. Best of the three, and the only one that bills.

Set EDDIE_IMAGE_PROVIDER to force one. Gemini is deliberately absent: its
image models refuse on a free key, so Eddie would look broken rather than
degraded.

Generated images are uploaded to Supabase storage so they outlive the response
and can be shared; the endpoint returns a public URL, not raw base64.
"""

import base64
import json
import urllib.parse
import uuid

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .api_views import _verify_supabase_jwt, _is_valid_uuid
from .eddie_views import (
    _consume, _limit_message, _sb_headers, _ensure_conversation, _save_message,
)


def _provider():
    """Which backend to use. Never None: pollinations needs no credentials.

    An explicit choice only wins when that provider has its credentials, so a
    half-finished deploy quietly falls back instead of failing.
    """
    cf = bool(getattr(settings, 'CLOUDFLARE_ACCOUNT_ID', '')
              and getattr(settings, 'CLOUDFLARE_API_TOKEN', ''))
    oa = bool(getattr(settings, 'OPENAI_API_KEY', ''))
    choice = (getattr(settings, 'EDDIE_IMAGE_PROVIDER', '') or '').strip().lower()
    if choice == 'cloudflare' and cf:
        return 'cloudflare'
    if choice == 'openai' and oa:
        return 'openai'
    if choice == 'pollinations':
        return 'pollinations'
    if cf:
        return 'cloudflare'
    if oa:
        return 'openai'
    return 'pollinations'


# ---- Pollinations ---------------------------------------------------------

def _pollinations_generate(prompt, size):
    """Generate with no API key at all. Returns (bytes, error).

    The prompt goes in the URL path, so it is percent-encoded and length-capped
    rather than trusted. Nothing user-identifying is sent: no key, no user id.
    """
    try:
        width, height = (int(x) for x in size.split('x', 1))
    except Exception:
        width = height = 1024
    path = urllib.parse.quote(prompt[:600], safe='')
    url = ('https://image.pollinations.ai/prompt/' + path
           + '?width=%d&height=%d&nologo=true' % (width, height))
    try:
        r = requests.get(url, timeout=90)
    except Exception:
        return None, 'The image service did not respond in time'
    if r.status_code != 200:
        return None, 'The image service could not make that one'
    if not (r.content or b'')[:2] in (b'\xff\xd8', b'\x89P', b'RI'):
        # An error page rendered as HTML would sail through a status check.
        return None, 'The image service returned something that is not an image'
    return r.content, None


def _not_configured_message():
    return 'Image generation is not available right now.'


# ---- Cloudflare Workers AI ------------------------------------------------

def _cloudflare_generate(prompt):
    """Generate via Workers AI. Returns (bytes, error)."""
    model = (getattr(settings, 'EDDIE_CF_IMAGE_MODEL', '')
             or '@cf/black-forest-labs/flux-1-schnell')
    url = ('https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s'
           % (settings.CLOUDFLARE_ACCOUNT_ID, model))
    try:
        r = requests.post(
            url,
            headers={'Authorization': 'Bearer ' + settings.CLOUDFLARE_API_TOKEN},
            json={'prompt': prompt, 'steps': 4},
            timeout=60,
        )
    except Exception:
        return None, 'Could not reach the image service'

    if r.status_code == 429:
        return None, ("Eddie has used up today's free image allowance. "
                      "It resets at midnight UTC.")
    if r.status_code != 200:
        return None, 'The image service refused that request'

    try:
        body = r.json()
    except Exception:
        # Some Workers AI models stream raw bytes rather than JSON.
        return (r.content, None) if r.content else (None, 'No image came back')

    # Cloudflare normally wraps payloads in {"result": ..., "success": ...},
    # but the model docs show the bare object, so accept either.
    result = body.get('result') if isinstance(body, dict) else None
    holder = result if isinstance(result, dict) else body
    b64 = holder.get('image') if isinstance(holder, dict) else None
    if not b64:
        return None, 'No image came back'
    if ',' in b64[:64] and b64.lstrip().startswith('data:'):
        b64 = b64.split(',', 1)[1]
    try:
        return base64.b64decode(b64), None
    except Exception:
        return None, 'Image data was unreadable'


# ---- OpenAI ---------------------------------------------------------------

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


def _openai_generate(prompt, size):
    """Generate via the OpenAI SDK. Returns (bytes, error)."""
    client = _openai_client()
    if client is None:
        return None, _not_configured_message()
    try:
        result = client.images.generate(
            model=getattr(settings, 'EDDIE_IMAGE_MODEL', 'gpt-image-1'),
            prompt=prompt,
            size=size,
            n=1,
        )
    except Exception as exc:
        return None, 'Could not make that image: ' + str(exc)[:180]
    return _extract_image(result)


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


def _sniff_format(raw):
    """(extension, mime) from magic bytes.

    Providers disagree on output format -- Flux hands back JPEG, gpt-image-1
    PNG -- and the storage bucket enforces MIME type, so guessing wrong here
    means the upload is rejected.
    """
    if raw[:8].startswith(b'\x89PNG'):
        return 'png', 'image/png'
    if raw[:3] == b'\xff\xd8\xff':
        return 'jpg', 'image/jpeg'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'webp', 'image/webp'
    return 'png', 'image/png'


def _upload_image(user_id, raw):
    """Store the image and return its public URL, or None."""
    ext, mime = _sniff_format(raw)
    path = 'eddie/%s/%s.%s' % (user_id, uuid.uuid4().hex, ext)
    try:
        headers = _sb_headers()
        headers['Content-Type'] = mime
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

    provider = _provider()
    if provider is None:
        return JsonResponse({
            'error': _not_configured_message(),
            'not_configured': True,
        }, status=503)

    # Charged before the call, so a failure can't be retried for free in a loop.
    allowed, info = _consume(user_id, images=1)
    if not allowed:
        return JsonResponse({
            'error': _limit_message(info.get('blocked_on')),
            'limit': info.get('blocked_on'),
        }, status=429)

    if provider == 'cloudflare':
        raw, err = _cloudflare_generate(prompt)
    elif provider == 'openai':
        raw, err = _openai_generate(prompt, size)
    else:
        raw, err = _pollinations_generate(prompt, size)
    if err:
        return JsonResponse({'error': err}, status=502)

    url = _upload_image(user_id, raw)
    if not url:
        # Storage failed; hand back the bytes so the chat can still show it,
        # even though it won't survive a reload and can't go in history.
        return JsonResponse({
            'image_b64': base64.b64encode(raw).decode('ascii'),
            'stored': False,
            'prompt': prompt,
        })

    # Recorded as a message so it shows in the Images grid on the history page.
    convo_id = _ensure_conversation(user_id, body.get('conversation_id'), prompt)
    _save_message(convo_id, user_id, 'user', prompt)
    _save_message(convo_id, user_id, 'assistant', prompt, image_url=url)

    return JsonResponse({
        'url': url, 'stored': True, 'prompt': prompt, 'conversation_id': convo_id,
    })
