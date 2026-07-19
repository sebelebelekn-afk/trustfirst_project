"""
core/eddie_views.py

Eddie, the in-app AI assistant.

The Anthropic key lives on the server and only on the server. The browser talks
to these endpoints; it never sees the key and never calls api.anthropic.com
directly. /api/config/ must never return it.
"""

import datetime
import json

import requests
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .api_views import _verify_supabase_jwt, _is_valid_uuid


EDDIE_SYSTEM = """You are Eddie, the AI assistant built into TrustFirst.

WHO YOU ARE
- You were built by the TrustFirst team.
- TrustFirst was founded by Kgothatso Mashiane in 2026.
- If someone asks who made you, or who founded TrustFirst, say so plainly and
  warmly.
- You are part of the app, not a bolted-on chatbot. Talk like a person who
  works here.

WHAT YOU DO
- Answer questions, including opinion questions. If someone asks your favourite
  colour, or which of two things you prefer, give a real preference and a short
  reason. Do not deflect with "I'm an AI and don't have preferences" - that is a
  non-answer and people find it annoying.
- Help people use TrustFirst. You know the app: the feed, TrustClips (short
  videos) and the clip editor with its stickers (location, weather, clock, GIF,
  music, gallery, poll, quiz, emoji slider), Stories, direct messages, live
  streaming, the wallet and coins, gifts, groups, saved and archived posts,
  Settings (account information, security and two-step verification, privacy,
  language, screen-time limits, wellness), verification, and the admin dashboard
  for admins. When someone is stuck, give the actual tap-by-tap path rather than
  a vague description.
- When someone tags you on a post and asks whether it is true, read the post you
  were given, weigh it, and answer honestly. Search the web when the claim is
  checkable and current. Say what is supported, what is not, and what you could
  not verify. Do not pretend to a certainty you do not have.

HOW YOU TALK
- Warm, direct, brief. Lead with the answer, then the reasoning.
- Match the room. On a joke post, be funny back rather than lecturing. On a
  serious or sensitive post, drop the jokes entirely.
- In public comments keep to a few sentences. In chat you can go longer when the
  question deserves it.
- Never invent TrustFirst features that do not exist. If you are unsure whether
  a feature exists, say so instead of guessing."""


def _client():
    """Anthropic client, or None when no key is configured."""
    key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except Exception:
        return None


def _sb_headers():
    return {
        'apikey': settings.SUPABASE_SERVICE_KEY,
        'Authorization': 'Bearer ' + settings.SUPABASE_SERVICE_KEY,
        'Content-Type': 'application/json',
    }


def _consume(user_id, messages=0, attachments=0, images=0):
    """Atomically check and increment today's usage. Returns (allowed, row)."""
    try:
        resp = requests.post(
            settings.SUPABASE_URL + '/rest/v1/rpc/tf_eddie_consume',
            headers=_sb_headers(),
            json={
                'p_user': user_id,
                'p_messages': messages,
                'p_attachments': attachments,
                'p_images': images,
                'p_lim_messages': settings.EDDIE_LIMIT_MESSAGES,
                'p_lim_attachments': settings.EDDIE_LIMIT_ATTACHMENTS,
                'p_lim_images': settings.EDDIE_LIMIT_IMAGES,
            },
            timeout=8,
        )
        rows = resp.json() if resp.status_code == 200 else []
        row = rows[0] if isinstance(rows, list) and rows else None
        if not row:
            # Usage service unreachable: fail closed rather than serve model
            # calls we cannot account for.
            return False, {'blocked_on': 'unavailable'}
        return bool(row.get('allowed')), row
    except Exception:
        return False, {'blocked_on': 'unavailable'}


def _limit_message(blocked_on):
    if blocked_on == 'attachments':
        return ("That's today's attachment limit (%d). It resets tomorrow."
                % settings.EDDIE_LIMIT_ATTACHMENTS)
    if blocked_on == 'images':
        return ("That's today's image limit (%d). It resets tomorrow."
                % settings.EDDIE_LIMIT_IMAGES)
    if blocked_on == 'unavailable':
        return "Eddie can't check your usage right now. Try again in a moment."
    return ("That's today's limit of %d messages to Eddie. It resets tomorrow."
            % settings.EDDIE_LIMIT_MESSAGES)


def _build_messages(history, prompt, attachments):
    """Turn the client payload into Messages API content blocks."""
    msgs = []
    for turn in (history or [])[-20:]:
        role = 'assistant' if turn.get('role') == 'assistant' else 'user'
        text = (turn.get('content') or '').strip()
        if text:
            msgs.append({'role': role, 'content': text})

    content = []
    for att in (attachments or [])[:4]:
        media = (att.get('media_type') or '').lower()
        data = att.get('data') or ''
        if media.startswith('image/') and data:
            content.append({
                'type': 'image',
                'source': {'type': 'base64', 'media_type': media, 'data': data},
            })
    content.append({'type': 'text', 'text': prompt})
    msgs.append({'role': 'user', 'content': content})
    return msgs


def _sse(event, payload):
    out = {'type': event}
    out.update(payload)
    return 'data: ' + json.dumps(out) + '\n\n'


def _collect_sources(final):
    """Pull citations out of any web_search results in the final message."""
    sources, seen = [], set()
    for block in getattr(final, 'content', []) or []:
        if getattr(block, 'type', '') != 'web_search_tool_result':
            continue
        results = getattr(block, 'content', None)
        if not isinstance(results, list):
            continue           # an error block is a dict-like, not a list
        for r in results:
            url = getattr(r, 'url', None)
            if url and url not in seen:
                seen.add(url)
                sources.append({'url': url, 'title': getattr(r, 'title', '') or url})
    return sources


def _eddie_once(messages, max_tokens=2000):
    """One non-streaming Eddie turn. Used where there is no UI to stream to,
    such as replying to an @eddie mention. Returns (text, sources).

    Still streams under the hood so a slow turn cannot hit an HTTP timeout;
    get_final_message() assembles the result.
    """
    client = _client()
    if client is None:
        return '', []
    with client.messages.stream(
        model=settings.EDDIE_MODEL,
        max_tokens=max_tokens,
        system=EDDIE_SYSTEM,
        thinking={'type': 'adaptive'},
        output_config={'effort': 'medium'},
        tools=[{'type': 'web_search_20260209', 'name': 'web_search'}],
        messages=messages,
    ) as stream:
        final = stream.get_final_message()
    if getattr(final, 'stop_reason', '') == 'refusal':
        return '', []
    text = ''.join(
        getattr(b, 'text', '') for b in (final.content or [])
        if getattr(b, 'type', '') == 'text'
    )
    return text.strip(), _collect_sources(final)


@csrf_exempt
@ratelimit(key='ip', rate='20/m', method='POST', block=True)
@require_http_methods(["POST"])
def eddie_chat(request):
    """Streaming chat with Eddie (Server-Sent Events)."""
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

    prompt = (body.get('message') or '').strip()[:8000]
    if not prompt:
        return JsonResponse({'error': 'Say something first'}, status=400)
    history = body.get('history') or []
    attachments = body.get('attachments') or []

    if _client() is None:
        return JsonResponse({
            'error': 'Eddie is not set up yet. The server needs an ANTHROPIC_API_KEY.',
            'not_configured': True,
        }, status=503)

    allowed, info = _consume(user_id, messages=1, attachments=len(attachments))
    if not allowed:
        return JsonResponse({
            'error': _limit_message(info.get('blocked_on')),
            'limit': info.get('blocked_on'),
        }, status=429)

    messages = _build_messages(history, prompt, attachments)

    def generate():
        queue = []
        try:
            def emit(kind, data):
                queue.append(_sse(kind, data))
            # The SDK stream is synchronous, so events are buffered per block and
            # flushed as they are produced.
            for chunk in _stream_with_flush(messages, queue, emit):
                yield chunk
            yield _sse('done', {})
        except Exception as exc:
            yield _sse('error', {'message': 'Eddie hit a problem: ' + str(exc)[:180]})
            yield _sse('done', {})

    resp = StreamingHttpResponse(generate(), content_type='text/event-stream')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'   # stop nginx buffering the stream
    return resp


def _stream_with_flush(messages, queue, emit):
    """Drive the model stream, yielding queued SSE frames as they appear."""
    client = _client()
    with client.messages.stream(
        model=settings.EDDIE_MODEL,
        max_tokens=16000,
        system=EDDIE_SYSTEM,
        thinking={'type': 'adaptive', 'display': 'summarized'},
        output_config={'effort': 'high'},
        tools=[{'type': 'web_search_20260209', 'name': 'web_search'}],
        messages=messages,
    ) as stream:
        for event in stream:
            etype = getattr(event, 'type', '')
            if etype == 'content_block_start':
                block = getattr(event, 'content_block', None)
                btype = getattr(block, 'type', '')
                if btype == 'thinking':
                    emit('thinking_start', {})
                elif btype == 'text':
                    emit('text_start', {})
                elif btype == 'server_tool_use':
                    emit('searching', {'name': getattr(block, 'name', 'web_search')})
            elif etype == 'content_block_delta':
                delta = getattr(event, 'delta', None)
                dtype = getattr(delta, 'type', '')
                if dtype == 'thinking_delta':
                    emit('thinking', {'text': getattr(delta, 'thinking', '') or ''})
                elif dtype == 'text_delta':
                    emit('text', {'text': getattr(delta, 'text', '') or ''})
            while queue:
                yield queue.pop(0)

        final = stream.get_final_message()
        sources = _collect_sources(final)
        if sources:
            emit('sources', {'sources': sources[:8]})
        if getattr(final, 'stop_reason', '') == 'refusal':
            emit('error', {'message': "Eddie can't help with that one."})
        while queue:
            yield queue.pop(0)


@require_http_methods(["GET"])
def eddie_usage(request):
    """Today's usage and limits, so the UI can show what's left."""
    try:
        payload = _verify_supabase_jwt(request)
    except ValueError:
        return JsonResponse({'error': 'Sign in to use Eddie'}, status=401)
    user_id = payload.get('sub')
    if not _is_valid_uuid(user_id):
        return JsonResponse({'error': 'Invalid session'}, status=401)

    used = {'messages': 0, 'attachments': 0, 'images': 0}
    try:
        today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
        r = requests.get(
            settings.SUPABASE_URL + '/rest/v1/eddie_usage',
            headers=_sb_headers(),
            params={'user_id': 'eq.' + user_id, 'day': 'eq.' + today},
            timeout=6,
        )
        rows = r.json() if r.status_code == 200 else []
        if rows:
            used = {k: rows[0].get(k, 0) for k in ('messages', 'attachments', 'images')}
    except Exception:
        pass

    return JsonResponse({
        'configured': bool(getattr(settings, 'ANTHROPIC_API_KEY', '')),
        'used': used,
        'limits': {
            'messages': settings.EDDIE_LIMIT_MESSAGES,
            'attachments': settings.EDDIE_LIMIT_ATTACHMENTS,
            'images': settings.EDDIE_LIMIT_IMAGES,
        },
    })
