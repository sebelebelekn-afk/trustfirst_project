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
import random
import re
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


# ---- turning a request into a prompt ---------------------------------------
#
# What somebody types in a chat box is a request, not a prompt. "Can you
# generate an image of a man looking over a futuristic african city" was being
# sent to the image model verbatim, question and all, and the model spent part
# of its attention on "can you generate an image of". Every assistant that
# produces good pictures rewrites the request into a described scene first --
# subject, setting, light, framing, style -- and that rewrite is most of the
# visible difference between Eddie's output and theirs.
#
# It runs on the fast chat model, so it costs a few hundred milliseconds. If it
# fails, is slow, or comes back with something odd, the cleaned-up original is
# used instead: a worse picture beats no picture.

_REWRITE_SYSTEM = """You turn a person's request into a prompt for an image model.

Reply with the prompt and nothing else. No preamble, no quotes, no explanation,
no "here is". Just the prompt.

Describe what the picture contains, as a scene: the subject and what they are
doing, the setting, the time of day and quality of light, the framing and
camera distance, and the style. Be concrete and visual. Around 40 to 60 words.

Keep every specific thing the person asked for - who or what is in it, where,
what mood. Do not add people, text or objects they did not ask for, and never
invent a brand, a logo or a real person's likeness. If the request is already a
detailed prompt, tidy it and return it rather than rewriting it from scratch.

Drop the asking part entirely. "Can you generate an image of a red bicycle"
describes a red bicycle; it does not describe someone asking a question."""


# The asking part, for when the rewrite is unavailable. Deliberately narrow:
# it only strips a leading request, so "a painting of a man drawing a bicycle"
# keeps every word that describes the picture.
_FRAMING_RE = re.compile(
    r'^\s*(?:hey\s+|ok(?:ay)?[,\s]+|please\s+|eddie[,:\s]+)*'
    r'(?:can|could|would|will)?\s*(?:you|u)?\s*(?:please\s+)?'
    r'(?:make|draw|create|generate|render|design|paint|sketch|give\s+me|show\s+me)[\s:,]+'
    r'(?:me\s+)?'
    # The article belongs to this noun phrase, not to the subject. Matching it
    # on its own turned "draw me a banana" into "banana": the "a" was read as
    # the one in "a picture of" and eaten even though no such word followed.
    r'(?:(?:an?|some|the)\s+)?'
    r'(?:image|picture|photo|photograph|drawing|illustration|render|artwork|art|painting|sketch)'
    r'(?:\s+(?:of|showing|with|depicting))?'
    r'\s*[:,]?\s*',
    re.I)

# The same opener with no "picture of" in it: "draw me a banana", "paint a
# sunset". Tried only after the one above, so the longer form wins.
_FRAMING_SHORT_RE = re.compile(
    r'^\s*(?:hey\s+|ok(?:ay)?[,\s]+|please\s+|eddie[,:\s]+)*'
    r'(?:can|could|would|will)?\s*(?:you|u)?\s*(?:please\s+)?'
    r'(?:make|draw|create|generate|render|design|paint|sketch|give\s+me|show\s+me)[\s:,]+'
    r'(?:me\s+)?(?:of\s+)?',
    re.I)


def _strip_framing(prompt):
    """Take the request wrapper off, leaving what the picture is of."""
    text = prompt or ''
    out = _FRAMING_RE.sub('', text, count=1).strip()
    if out == text.strip():
        out = _FRAMING_SHORT_RE.sub('', text, count=1).strip()
    # If stripping ate the whole thing, the request WAS the subject.
    return out or text.strip()


def _rewrite_prompt(prompt):
    """A described scene, from a typed request. Never raises."""
    cleaned = _strip_framing(prompt)
    if (getattr(settings, 'EDDIE_IMAGE_REWRITE', 'on') or 'on').strip().lower() \
            in ('off', 'false', '0', 'no'):
        return cleaned
    try:
        from . import eddie_providers
        if not eddie_providers.is_configured():
            return cleaned
        text, _ = eddie_providers.once({
            'history': [],
            'prompt': prompt,
            'attachments': [],
            # Short on purpose. route_text picks the engine, and a long one
            # would route this to the slow model; nobody waits twenty seconds
            # extra for a prompt rewrite.
            'route_text': 'image prompt',
        }, _REWRITE_SYSTEM, 220)
    except Exception:
        return cleaned

    text = (text or '').strip().strip('"').strip()

    # Small models like to announce the answer before giving it. When the first
    # line is that announcement -- anything ending in a colon -- the prompt is
    # the rest, so take the rest rather than throwing the whole reply away.
    if '\n' in text:
        head, rest = text.split('\n', 1)
        if head.rstrip().endswith(':') and rest.strip():
            text = rest.strip()
    text = text.strip().strip('"').strip()

    # What is left still has to look like a description of a picture. Listing
    # every chatty opener would be a losing game, so this checks the shape: a
    # preamble with nothing after it ends in a colon, a refusal opens with one
    # of a few stock phrases, and anything too short or too long is not a
    # prompt. Any of those and what the person typed is the better bet.
    lowered = text.lower()
    if len(text) < 15 or len(text) > 900 or text.endswith(':'):
        return cleaned
    if lowered.startswith((
            "i can't", "i cannot", "i'm sorry", "sorry", "i am unable",
            "sure", "certainly", "of course", "absolutely", "okay", "ok,",
            "here is", "here's", "as an ai")):
        return cleaned
    return text


# Shape follows the subject. A cityscape in a square crops off the city; a
# portrait in a square wastes half the frame. Landscape is the default because
# most of what people ask Eddie for is a scene.
_PORTRAIT = re.compile(
    r'\b(portrait|vertical|tall|phone\s+wallpaper|lock\s*screen|story|poster|'
    r'full[\s-]?body|standing\s+person|book\s+cover)\b', re.I)
_SQUARE = re.compile(
    r'\b(square|avatar|profile\s+p(?:ic|icture)|icon|logo|album\s+cover|'
    r'sticker|emoji|thumbnail)\b', re.I)


def _dimensions(prompt):
    """(width, height) for what is being asked for."""
    if _SQUARE.search(prompt or ''):
        return 1024, 1024
    if _PORTRAIT.search(prompt or ''):
        return 768, 1344
    return 1344, 768


# OpenAI takes three sizes and refuses anything else, so the shape chosen above
# is snapped to the nearest one it accepts rather than sent as-is.
def _openai_size(width, height):
    if width > height:
        return '1536x1024'
    if height > width:
        return '1024x1536'
    return '1024x1024'


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

# Pollinations rations anonymous traffic per IP, and every request from this
# app leaves on the same one. A busy minute therefore looks exactly like a
# broken backend unless you retry, so a refusal that might clear gets one
# second attempt before anybody is told it failed.
_POLL_TIMEOUT = 40
_POLL_RETRY_AFTER = 3


def _pollinations_generate(prompt, size):
    """Generate with no API key at all. Returns (bytes, error).

    The prompt goes in the URL path, so it is percent-encoded and length-capped
    rather than trusted. Nothing user-identifying is sent: no key, no user id.
    The referrer names the app, which is how Pollinations asks callers to
    identify themselves and is what separates us from anonymous traffic.
    """
    import logging
    import time as _time
    log = logging.getLogger(__name__)

    try:
        width, height = (int(x) for x in size.split('x', 1))
    except Exception:
        width = height = 1024
    path = urllib.parse.quote(prompt[:900], safe='')
    referrer = (getattr(settings, 'APP_PUBLIC_URL', '')
                or 'https://gettrustfirst.co.za')
    # Without a seed Pollinations uses 42 every time, so the same words always
    # produced the same picture and "Try again" returned the image you were
    # already looking at.
    url = ('https://image.pollinations.ai/prompt/' + path
           + '?width=%d&height=%d&nologo=true&model=flux&seed=%d&referrer=%s'
           % (width, height, random.randint(1, 2 ** 31 - 1),
              urllib.parse.quote(referrer, safe='')))

    # A registered token moves this off the anonymous tier, which is what
    # forces every request onto the small 'sana' model at medium quality, caps
    # it at 768px and stamps the watermark on regardless of nologo. Free to
    # get; without one the parameters above are accepted and then ignored.
    headers = {'Referer': referrer}
    token = getattr(settings, 'POLLINATIONS_TOKEN', '')
    if token:
        headers['Authorization'] = 'Bearer ' + token

    last = None
    for attempt in (1, 2):
        try:
            r = requests.get(url, timeout=_POLL_TIMEOUT, headers=headers)
        except Exception as exc:
            last = 'The image service did not respond in time'
            log.warning('Image: pollinations attempt %d did not respond (%s)',
                        attempt, str(exc)[:160])
            if attempt == 1:
                _time.sleep(_POLL_RETRY_AFTER)
                continue
            return None, last

        if r.status_code == 200:
            # An error page rendered as HTML would sail through a status check.
            if (r.content or b'')[:2] in (b'\xff\xd8', b'\x89P', b'RI'):
                return r.content, None
            log.warning('Image: pollinations returned %s, %d bytes, not an image: %s',
                        r.headers.get('content-type', '?'), len(r.content or b''),
                        (r.content or b'')[:200])
            return None, 'The image service returned something that is not an image'

        # Whatever went wrong, write it down. Without this the only evidence
        # was "could not make that one", which says nothing anybody can act on.
        log.warning('Image: pollinations attempt %d refused with HTTP %s: %s',
                    attempt, r.status_code, (r.text or '')[:200].replace('\n', ' '))

        if r.status_code in (429, 500, 502, 503, 504) and attempt == 1:
            _time.sleep(_POLL_RETRY_AFTER)
            continue

        if r.status_code == 429:
            return None, ('The image service is busy right now. '
                          'Give it a minute and try again.')
        return None, 'The image service could not make that one'

    return None, last or 'The image service could not make that one'


# ---- Eddie's own mark ------------------------------------------------------
#
# Only on pictures from a backend that does not stamp its own.
#
# Pollinations' free tier puts "pollinations.ai" in the corner, and nologo=true
# is accepted and then ignored unless the request is authenticated. Painting
# "Eddie AI" over that, or cropping it off, would be taking the attribution off
# somebody else's free service and putting ours on their work. Not ours to do.
# On Cloudflare or OpenAI there is no such mark and the picture is Eddie's
# output to sign, so it gets signed.
#
# The mark never costs a picture: any failure here returns the bytes untouched.

_MARK_TEXT = 'Eddie AI'
_MARK_FONTS = (
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
)

# Backends that put their own name on the picture. Ours does not go on top.
_SELF_BRANDED = {'pollinations'}


def _mark_font(size):
    from PIL import ImageFont
    for path in _MARK_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)          # Pillow >= 10.1
    except Exception:
        from PIL import ImageFont as _IF
        return _IF.load_default()


def _watermark(raw, provider):
    """Sign the picture, unless the backend already signed it."""
    if not raw or provider in _SELF_BRANDED:
        return raw
    mode = (getattr(settings, 'EDDIE_IMAGE_WATERMARK', 'on') or 'on').strip().lower()
    if mode in ('off', 'false', '0', 'no'):
        return raw
    try:
        import io
        from PIL import Image, ImageDraw

        im = Image.open(io.BytesIO(raw))
        fmt = (im.format or 'PNG').upper()
        im = im.convert('RGB')
        w, h = im.size

        # Scales with the picture, so it reads the same on a 768px square and
        # a 1344px wide one instead of being a speck on the big one.
        size = max(13, int(w * 0.022))
        pad = max(10, int(w * 0.016))
        font = _mark_font(size)

        layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        try:
            box = draw.textbbox((0, 0), _MARK_TEXT, font=font)
            tw, th = box[2] - box[0], box[3] - box[1]
        except Exception:
            tw, th = draw.textlength(_MARK_TEXT, font=font), size
        x, y = w - tw - pad, h - th - pad - int(size * 0.35)

        # White on a bright sky is unreadable, and a picture is as likely to
        # end in a sunset as in a night street, so the mark reads what is
        # behind it and picks the colour that shows up against it.
        patch = im.crop((max(0, int(x)), max(0, int(y)), w, h)).convert('L')
        light_behind = (sum(patch.getdata()) / max(1, len(patch.getdata()))) > 128
        ink    = (20, 20, 20, 225) if light_behind else (255, 255, 255, 225)
        shadow = (255, 255, 255, 130) if light_behind else (0, 0, 0, 140)

        off = max(1, size // 14)
        draw.text((x + off, y + off), _MARK_TEXT, font=font, fill=shadow)
        draw.text((x, y), _MARK_TEXT, font=font, fill=ink)

        im = Image.alpha_composite(im.convert('RGBA'), layer).convert('RGB')
        out = io.BytesIO()
        if fmt == 'JPEG':
            im.save(out, 'JPEG', quality=92, optimize=True)
        else:
            im.save(out, 'PNG', optimize=True)
        return out.getvalue()
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Image: watermark skipped', exc_info=True)
        return raw


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

    # What they typed is the request; what the model needs is a described
    # scene. The rewrite is also what decides the shape, so it happens before
    # the size is chosen.
    scene = _rewrite_prompt(prompt)

    width, height = _dimensions(prompt + ' ' + scene)
    size = body.get('size')
    if size in ('1024x1024', '1024x1536', '1536x1024'):
        width, height = (int(x) for x in size.split('x', 1))
    size = '%dx%d' % (width, height)

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
        raw, err = _cloudflare_generate(scene)
    elif provider == 'openai':
        raw, err = _openai_generate(scene, _openai_size(width, height))
    else:
        raw, err = _pollinations_generate(scene, size)
    if err:
        return JsonResponse({'error': err}, status=502)

    raw = _watermark(raw, provider)

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
