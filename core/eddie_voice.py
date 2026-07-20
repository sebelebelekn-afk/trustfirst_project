"""
core/eddie_voice.py

Read-aloud for Eddie, cached.

Most devices only ship decades-old formant voices, which is why the browser's
own speechSynthesis sounds like a robot. So speech is synthesised server-side
and the browser is only the fallback.

The cache is the point of this module. Synthesis is the expensive part of
Eddie by a wide margin -- ElevenLabs' free tier is measured in thousands of
characters per month, not millions -- and the same audio gets requested over
and over: a user replays a reply, a second user asks the same question, a
thread gets reopened. Audio is stored under a hash of exactly what produced
it, so any repeat is a static file served by Supabase's CDN at no cost and no
latency.

Because the key is a hash of the text, finding a cached clip requires already
knowing the text it was made from, so the shared cache leaks nothing that the
requester did not already have.

Providers, in order: ElevenLabs (best voice, tightest quota), then Groq's
neural TTS (free, needs its model terms accepted once). If both are out the
view says so and the client falls back to the browser.
"""

import hashlib
import json

import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .api_views import _verify_supabase_jwt, _is_valid_uuid
from .eddie_views import _sb_headers


# Its own bucket, not `media`: that one is deliberately restricted to images
# and video, and widening it for audio would undo a security decision.
BUCKET = 'eddie_voice'
PREFIX = ''


# ---- cache ----------------------------------------------------------------

def _cache_key(text, voice, model):
    raw = '%s|%s|%s' % (model or '', voice or '', text)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _public_url(name):
    return '%s/storage/v1/object/public/%s/%s%s' % (
        settings.SUPABASE_URL, BUCKET, PREFIX, name)


def _cached_url(key):
    """Return a public URL if this clip was already synthesised.

    mp3 first because ElevenLabs is the preferred provider; wav is Groq's.
    """
    for ext in ('mp3', 'wav'):
        url = _public_url(key + '.' + ext)
        try:
            r = requests.head(url, timeout=5)
            if r.status_code == 200:
                return url
        except Exception:
            return None          # network is down; treat as a miss, not an error
    return None


def _store(key, raw, ext, mime):
    """Upload the clip and return its public URL, or None."""
    name = key + '.' + ext
    try:
        headers = _sb_headers()
        headers['Content-Type'] = mime
        headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        r = requests.post(
            '%s/storage/v1/object/%s/%s%s' % (
                settings.SUPABASE_URL, BUCKET, PREFIX, name),
            headers=headers, data=raw, timeout=30,
        )
        # 409 means another request synthesised the same text first, which is a
        # cache hit arriving late rather than a failure.
        if r.status_code in (200, 201, 409):
            return _public_url(name)
        return None
    except Exception:
        return None


# ---- ElevenLabs -----------------------------------------------------------

_EL_VOICE = {}          # process-level cache of the resolved voice id


def _elevenlabs_voice():
    """Resolve a voice id, preferring the configured one.

    Voice ids are per-account, so a hardcoded default would 402 on somebody
    else's key. Ask the account what it has and keep the answer.
    """
    configured = getattr(settings, 'EDDIE_TTS_VOICE_ID', '')
    if configured:
        return configured
    if 'id' in _EL_VOICE:
        return _EL_VOICE['id']

    key = getattr(settings, 'ELEVENLABS_API_KEY', '')
    if not key:
        return None
    try:
        r = requests.get('https://api.elevenlabs.io/v1/voices',
                         headers={'xi-api-key': key}, timeout=20)
        if r.status_code != 200:
            return None
        voices = r.json().get('voices') or []
        wanted = (getattr(settings, 'EDDIE_TTS_VOICE', '') or '').lower()
        pick = None
        if wanted:
            pick = next((v for v in voices
                         if wanted in (v.get('name') or '').lower()), None)
        pick = pick or next((v for v in voices
                             if v.get('category') == 'premade'), None)
        pick = pick or (voices[0] if voices else None)
        _EL_VOICE['id'] = pick.get('voice_id') if pick else None
        return _EL_VOICE['id']
    except Exception:
        return None


def _elevenlabs_tts(text):
    """Returns (bytes, ext, mime, error)."""
    key = getattr(settings, 'ELEVENLABS_API_KEY', '')
    if not key:
        return None, None, None, 'not configured'
    voice = _elevenlabs_voice()
    if not voice:
        return None, None, None, 'no voice available'
    try:
        r = requests.post(
            'https://api.elevenlabs.io/v1/text-to-speech/' + voice,
            headers={'xi-api-key': key, 'Content-Type': 'application/json'},
            json={'text': text,
                  'model_id': getattr(settings, 'EDDIE_TTS_EL_MODEL', '')
                              or 'eleven_turbo_v2_5'},
            timeout=60,
        )
    except Exception:
        return None, None, None, 'unreachable'
    if r.status_code == 200 and r.content:
        return r.content, 'mp3', 'audio/mpeg', None
    detail = ''
    try:
        detail = json.dumps(r.json().get('detail', ''))[:200]
    except Exception:
        pass
    # 401/402/429 all mean "out of quota or plan"; the caller moves on.
    return None, None, None, ('%s %s' % (r.status_code, detail)).strip()


# ---- Groq -----------------------------------------------------------------

def _groq_tts(text):
    """Returns (bytes, ext, mime, error)."""
    key = getattr(settings, 'GROQ_API_KEY', '')
    if not key:
        return None, None, None, 'not configured'
    try:
        r = requests.post(
            'https://api.groq.com/openai/v1/audio/speech',
            headers={'Authorization': 'Bearer ' + key},
            json={'model': getattr(settings, 'EDDIE_TTS_MODEL', '')
                           or 'canopylabs/orpheus-v1-english',
                  'input': text,
                  'voice': getattr(settings, 'EDDIE_TTS_GROQ_VOICE', '') or 'tara',
                  'response_format': 'wav'},
            timeout=60,
        )
    except Exception:
        return None, None, None, 'unreachable'
    if r.status_code == 200 and r.content:
        return r.content, 'wav', 'audio/wav', None
    detail = ''
    try:
        detail = (r.json().get('error') or {}).get('message', '')[:200]
    except Exception:
        pass
    return None, None, None, ('%s %s' % (r.status_code, detail)).strip()


# ---- view -----------------------------------------------------------------

@csrf_exempt
@ratelimit(key='ip', rate='30/m', method='POST', block=True)
@require_http_methods(["POST"])
def eddie_speak(request):
    """Return a URL for spoken audio, synthesising only on a cache miss."""
    try:
        payload = _verify_supabase_jwt(request)
    except ValueError:
        return JsonResponse({'error': 'Sign in first'}, status=401)
    if not _is_valid_uuid(payload.get('sub')):
        return JsonResponse({'error': 'Invalid session'}, status=401)

    try:
        body = json.loads(request.body or b'{}')
    except Exception:
        return JsonResponse({'error': 'Bad request'}, status=400)

    text = ' '.join((body.get('text') or '').split())[:1200]
    if not text:
        return JsonResponse({'error': 'Nothing to read'}, status=400)

    voice = getattr(settings, 'EDDIE_TTS_VOICE', '') or 'default'
    model = getattr(settings, 'EDDIE_TTS_EL_MODEL', '') or 'eleven_turbo_v2_5'
    key = _cache_key(text, voice, model)

    hit = _cached_url(key)
    if hit:
        return JsonResponse({'url': hit, 'cached': True})

    tried = {}
    for name, fn in (('elevenlabs', _elevenlabs_tts), ('groq', _groq_tts)):
        raw, ext, mime, err = fn(text)
        if raw:
            url = _store(key, raw, ext, mime)
            if url:
                return JsonResponse({'url': url, 'cached': False,
                                     'provider': name})
            return JsonResponse({'error': 'Could not store the audio',
                                 'fallback': True}, status=503)
        tried[name] = err

    # Every provider declined. The client falls back to the browser's own
    # voice, so this is a downgrade rather than a failure.
    return JsonResponse({
        'error': 'No server voice available right now',
        'fallback': True,
        'tried': tried,
    }, status=503)
