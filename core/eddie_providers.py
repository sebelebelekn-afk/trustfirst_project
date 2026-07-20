"""
core/eddie_providers.py

The engine behind Eddie, kept separate from the HTTP and storage layer.

TrustFirst runs on donated time and no budget, so the default engine is
Google's Gemini free tier. Anthropic stays supported and is one env var away
for the day there is funding: set EDDIE_PROVIDER=anthropic. Nothing else in
the app changes, because both backends emit the same events and the same
`sources` shape that eddie_views.py already stores and feed.js already renders.

Web search is the one Eddie feature the free tier will not do. Google offers
free Search grounding on gemini-2.5-flash only, and that model is closed to
new API keys, so a new free account gets a quota error the moment it asks to
ground. Eddie therefore treats search as optional: it tries once, and on a
quota refusal it turns search off for an hour and tells the model to stop
implying it looked anything up. Add billing and search switches itself back on
with no code change.

No key ever reaches the browser. Callers pass a neutral spec:

    {'history': [{'role': 'user'|'assistant', 'text': str}, ...],
     'prompt': str,
     'attachments': [{'media_type': str, 'data': <base64>}, ...]}
"""

import time

from django.conf import settings


# Grounding is billed, and asking for it costs a round trip to be told so.
# Once refused, stop asking for a while rather than burning a call per message.
_SEARCH_OFF_UNTIL = 0.0
_SEARCH_COOLDOWN = 3600

_NO_SEARCH_NOTE = (
    "\n\nRIGHT NOW: web search is switched off, so you cannot look anything up. "
    "Answer from what you already know. When a claim needs checking against a "
    "live source, say so plainly instead of implying you checked it, and never "
    "invent a citation.")


def _search_on():
    """Whether to ask for Search grounding on this call.

    Defaults off, and not out of caution: a free key is refused, and the
    refusal is not fast. Probing costs roughly 40 seconds of dead time before
    the retry even starts, which is most of the way to a gateway timeout. Set
    EDDIE_WEB_SEARCH=auto once billing exists and it will probe once per
    process, or =on to skip probing entirely.
    """
    mode = (getattr(settings, 'EDDIE_WEB_SEARCH', '') or 'off').strip().lower()
    if mode in ('on', 'true', '1', 'yes'):
        return True
    if mode not in ('auto', 'try'):
        return False
    return time.time() >= _SEARCH_OFF_UNTIL


def _search_off():
    global _SEARCH_OFF_UNTIL
    _SEARCH_OFF_UNTIL = time.time() + _SEARCH_COOLDOWN


def _is_quota(text):
    return any(s in text for s in (
        'quota', 'billing', 'resource_exhausted', 'resource exhausted',
        'exceeded', '429',
    ))


def _is_shape(text):
    """A "you asked for something I don't support" error, not a real failure."""
    return any(s in text for s in (
        'invalid', 'unknown', 'unsupported', 'not supported', 'unexpected',
        'no attribute', 'not a supported',
    ))


# ---- which engine ---------------------------------------------------------

def _have(name):
    return bool(getattr(settings, name, ''))


def active():
    """The engine that answers an ordinary message.

    An explicit EDDIE_PROVIDER only wins if that provider actually has a key,
    so a half-finished deploy falls back to an engine that can answer rather
    than failing every request. Groq comes first because it replies in well
    under a second where Gemini takes tens of seconds.
    """
    choice = (getattr(settings, 'EDDIE_PROVIDER', '') or '').strip().lower()
    keys = {'groq': _have('GROQ_API_KEY'),
            'gemini': _have('GEMINI_API_KEY'),
            'anthropic': _have('ANTHROPIC_API_KEY')}
    if choice in keys and keys[choice]:
        return choice
    for name in ('groq', 'gemini', 'anthropic'):
        if keys[name]:
            return name
    return None


# Signals that a question deserves the slower, stronger model. Deliberately
# short: over-routing to Gemini is how Eddie got slow in the first place.
_DEEP_HINTS = (
    'explain', 'why ', 'compare', 'analyse', 'analyze', 'step by step',
    'pros and cons', 'in detail', 'research', 'debug', 'fact check',
    'fact-check', 'is it true', 'walk me through',
)


def _needs_depth(spec):
    """Route to the stronger model, or keep it on the fast one."""
    if spec.get('attachments'):
        return True             # Groq's text models cannot read images or PDFs
    # route_text is what the person actually wrote. Mentions wrap the question
    # in a few hundred characters of framing, and routing on that would send
    # every "@eddie lol" to the slow engine.
    prompt = (spec.get('route_text') or spec.get('prompt') or '').lower()
    if len(prompt) > 400:
        return True
    return any(h in prompt for h in _DEEP_HINTS)


def _route(spec):
    """Pick the engine for this specific turn."""
    choice = (getattr(settings, 'EDDIE_PROVIDER', '') or '').strip().lower()
    if choice in ('groq', 'gemini', 'anthropic') and _have(
            {'groq': 'GROQ_API_KEY', 'gemini': 'GEMINI_API_KEY',
             'anthropic': 'ANTHROPIC_API_KEY'}[choice]):
        return choice           # an explicit choice is not second-guessed

    # Fast by default, deep when the question earns it and a deep engine exists.
    if _needs_depth(spec):
        for name, key in (('gemini', 'GEMINI_API_KEY'),
                          ('anthropic', 'ANTHROPIC_API_KEY')):
            if _have(key):
                return name
    return active()


def is_configured():
    return active() is not None


def not_configured_message():
    return ('Eddie is not set up yet. The server needs a GROQ_API_KEY or '
            'GEMINI_API_KEY (both have free tiers), or an ANTHROPIC_API_KEY.')


# ---- shape helpers --------------------------------------------------------

def _attr(obj, name, default=None):
    """Read a field whether the SDK hands back objects or plain dicts."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _add_source(url, title, sources, seen):
    if not url or url in seen:
        return
    seen.add(url)
    sources.append({'url': url, 'title': title or url})


# ---- Gemini ---------------------------------------------------------------

def _gemini_client():
    key = getattr(settings, 'GEMINI_API_KEY', '')
    if not key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=key)
    except Exception:
        return None


def _gemini_input(spec):
    """Neutral spec -> Interactions API `input` array.

    History is passed in full on every call because we run stateless
    (store=False): TrustFirst already keeps conversations in Supabase, and not
    duplicating them on Google's servers is one less copy of user data.
    """
    items = []
    for turn in (spec.get('history') or [])[-20:]:
        text = (turn.get('text') or '').strip()
        if not text:
            continue
        items.append({
            'type': 'model_output' if turn.get('role') == 'assistant' else 'user_input',
            'content': [{'type': 'text', 'text': text}],
        })

    parts = []
    for att in (spec.get('attachments') or [])[:4]:
        media = (att.get('media_type') or '').lower()
        data = att.get('data') or ''
        if not data:
            continue
        if media.startswith('image/'):
            parts.append({'type': 'image', 'data': data, 'mime_type': media})
        elif media == 'application/pdf':
            parts.append({'type': 'document', 'data': data, 'mime_type': media})
    parts.append({'type': 'text', 'text': spec.get('prompt') or ''})
    items.append({'type': 'user_input', 'content': parts})
    return items


def _gemini_model():
    return getattr(settings, 'EDDIE_GEMINI_MODEL', '') or 'gemini-3.5-flash'


def _gemini_create(client, system, items, max_tokens, stream):
    """Call the Interactions API, shedding optional features if refused.

    Two things can be withdrawn independently. Search is billed, so a quota
    refusal means drop the tool and retry the same request. Thinking controls
    vary by model (gemini-flash-latest accepts low/high but not medium), so a
    shape error means step down the config ladder. Anything else -- bad key,
    network, real quota exhaustion -- surfaces, because silently swallowing
    those would leave Eddie mysteriously mute.
    """
    model = _gemini_model()
    # Thinking is what people wait for. 'low' still produces visible thought
    # summaries but answers in a fraction of the time, which matters more in a
    # chat bubble than a longer deliberation nobody reads.
    level = (getattr(settings, 'EDDIE_THINKING', '') or 'low').strip().lower()
    if level not in ('minimal', 'low', 'medium', 'high'):
        level = 'low'
    # Each rung drops exactly one thing, so a model that dislikes the level
    # (gemini-flash-latest takes low/high but not medium) does not also lose
    # its thought summaries, and vice versa.
    configs = [
        {'max_output_tokens': max_tokens,
         'thinking_level': level, 'thinking_summaries': 'auto'},
        {'max_output_tokens': max_tokens,
         'thinking_level': 'low', 'thinking_summaries': 'auto'},
        {'max_output_tokens': max_tokens, 'thinking_level': 'low'},
        {'max_output_tokens': max_tokens},
    ]
    rung = 0
    last = None

    # Bounded: at most one search-drop per config rung.
    for _ in range(len(configs) * 2):
        if rung >= len(configs):
            break
        use_search = _search_on()
        kwargs = {
            'model': model,
            'system_instruction': system if use_search else system + _NO_SEARCH_NOTE,
            'input': items,
            'generation_config': configs[rung],
            'store': False,
            'stream': stream,
        }
        if use_search:
            kwargs['tools'] = [{'type': 'google_search'}]
        try:
            return client.interactions.create(**kwargs)
        except Exception as exc:
            last = exc
            text = str(exc).lower()
            if use_search and _is_quota(text):
                _search_off()
                continue                    # same rung, without the tool
            if _is_shape(text):
                rung += 1
                continue
            raise
    raise last


def _gemini_harvest_delta(delta, sources, seen):
    """Pull citations out of a google_search_result delta."""
    for key in ('results', 'content', 'chunks'):
        block = _attr(delta, key)
        if isinstance(block, list):
            for item in block:
                web = _attr(item, 'web') or item
                _add_source(_attr(web, 'uri') or _attr(web, 'url'),
                            _attr(web, 'title'), sources, seen)


def _gemini_harvest_final(interaction, sources, seen):
    """Pull url_citation annotations off the completed interaction."""
    for step in (_attr(interaction, 'steps') or []):
        for block in (_attr(step, 'content') or []):
            for ann in (_attr(block, 'annotations') or []):
                if _attr(ann, 'type') == 'url_citation':
                    _add_source(_attr(ann, 'url'), _attr(ann, 'title'),
                                sources, seen)


def _gemini_thought_text(delta):
    """Thought summaries carry text one level deeper than plain text deltas."""
    content = _attr(delta, 'content')
    if content is not None:
        text = _attr(content, 'text')
        if text:
            return text
        if isinstance(content, str):
            return content
    return _attr(delta, 'text') or ''


def _gemini_stream(spec, system, queue, emit, max_tokens):
    client = _gemini_client()
    if client is None:
        emit('error', {'message': not_configured_message()})
        while queue:
            yield queue.pop(0)
        return

    stream = _gemini_create(client, system, _gemini_input(spec), max_tokens, True)
    sources, seen = [], set()
    thinking_open = False
    text_open = False

    for event in stream:
        etype = _attr(event, 'event_type')

        if etype == 'step.start':
            if _attr(_attr(event, 'step'), 'type') == 'google_search_call':
                emit('searching', {'name': 'web_search'})

        elif etype == 'step.delta':
            delta = _attr(event, 'delta')
            dtype = _attr(delta, 'type')
            if dtype == 'thought_summary':
                if not thinking_open:
                    emit('thinking_start', {})
                    thinking_open = True
                emit('thinking', {'text': _gemini_thought_text(delta)})
            elif dtype == 'text':
                if not text_open:
                    emit('text_start', {})
                    text_open = True
                emit('text', {'text': _attr(delta, 'text') or ''})
            elif dtype == 'google_search_result':
                _gemini_harvest_delta(delta, sources, seen)

        elif etype == 'interaction.completed':
            _gemini_harvest_final(_attr(event, 'interaction'), sources, seen)

        elif etype == 'error':
            emit('error', {'message': "Eddie can't help with that one."})

        while queue:
            yield queue.pop(0)

    if sources:
        emit('sources', {'sources': sources[:8]})
    while queue:
        yield queue.pop(0)


def _gemini_once(spec, system, max_tokens):
    client = _gemini_client()
    if client is None:
        return '', []
    result = _gemini_create(client, system, _gemini_input(spec), max_tokens, False)
    sources, seen = [], set()
    _gemini_harvest_final(result, sources, seen)

    text = _attr(result, 'output_text')
    if not text:
        chunks = []
        for step in (_attr(result, 'steps') or []):
            if _attr(step, 'type') != 'model_output':
                continue
            for block in (_attr(step, 'content') or []):
                if _attr(block, 'type') == 'text':
                    chunks.append(_attr(block, 'text') or '')
        text = ''.join(chunks)
    return (text or '').strip(), sources


# ---- Groq -----------------------------------------------------------------
#
# Groq speaks the OpenAI wire format, so this rides the openai package that is
# already a dependency for image generation. No new library for a whole engine.

def _groq_client():
    key = getattr(settings, 'GROQ_API_KEY', '')
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key, base_url='https://api.groq.com/openai/v1')
    except Exception:
        return None


def _groq_messages(spec, system):
    """Neutral spec -> OpenAI chat messages.

    Attachments are dropped rather than described: _needs_depth() already
    routes anything with a file to a model that can actually read it, so
    reaching here with one means the deep engines are unavailable, and a
    silent drop beats a confident answer about a file nobody looked at.
    """
    msgs = [{'role': 'system', 'content': system}]
    for turn in (spec.get('history') or [])[-20:]:
        text = (turn.get('text') or '').strip()
        if text:
            msgs.append({
                'role': 'assistant' if turn.get('role') == 'assistant' else 'user',
                'content': text,
            })
    prompt = spec.get('prompt') or ''
    if spec.get('attachments'):
        prompt += ("\n\n(The person attached a file. You cannot see it. Say so "
                   "plainly and ask them to describe it.)")
    msgs.append({'role': 'user', 'content': prompt})
    return msgs


def _groq_model():
    return getattr(settings, 'EDDIE_GROQ_MODEL', '') or 'llama-3.3-70b-versatile'


def _groq_stream(spec, system, queue, emit, max_tokens):
    client = _groq_client()
    if client is None:
        emit('error', {'message': not_configured_message()})
        while queue:
            yield queue.pop(0)
        return

    stream = client.chat.completions.create(
        model=_groq_model(),
        messages=_groq_messages(spec, system),
        max_tokens=min(max_tokens, 8000),
        stream=True,
    )
    text_open = False
    for chunk in stream:
        choices = getattr(chunk, 'choices', None) or []
        if not choices:
            continue
        delta = getattr(choices[0], 'delta', None)
        piece = getattr(delta, 'content', None)
        if piece:
            if not text_open:
                emit('text_start', {})
                text_open = True
            emit('text', {'text': piece})
        while queue:
            yield queue.pop(0)
    while queue:
        yield queue.pop(0)


def _groq_once(spec, system, max_tokens):
    client = _groq_client()
    if client is None:
        return '', []
    result = client.chat.completions.create(
        model=_groq_model(),
        messages=_groq_messages(spec, system),
        max_tokens=min(max_tokens, 8000),
    )
    choices = getattr(result, 'choices', None) or []
    if not choices:
        return '', []
    return ((getattr(choices[0].message, 'content', '') or '').strip(), [])


# ---- Anthropic ------------------------------------------------------------

def _anthropic_client():
    key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    except Exception:
        return None


def _anthropic_messages(spec):
    """Neutral spec -> Messages API content blocks."""
    msgs = []
    for turn in (spec.get('history') or [])[-20:]:
        text = (turn.get('text') or '').strip()
        if text:
            msgs.append({
                'role': 'assistant' if turn.get('role') == 'assistant' else 'user',
                'content': text,
            })

    content = []
    for att in (spec.get('attachments') or [])[:4]:
        media = (att.get('media_type') or '').lower()
        data = att.get('data') or ''
        if not data:
            continue
        if media.startswith('image/'):
            content.append({
                'type': 'image',
                'source': {'type': 'base64', 'media_type': media, 'data': data},
            })
        elif media == 'application/pdf':
            # Documents go before the question, same as images.
            content.append({
                'type': 'document',
                'source': {'type': 'base64', 'media_type': 'application/pdf',
                           'data': data},
            })
    content.append({'type': 'text', 'text': spec.get('prompt') or ''})
    msgs.append({'role': 'user', 'content': content})
    return msgs


def _anthropic_sources(final):
    """Pull citations out of any web_search results in the final message."""
    sources, seen = [], set()
    for block in getattr(final, 'content', []) or []:
        if getattr(block, 'type', '') != 'web_search_tool_result':
            continue
        results = getattr(block, 'content', None)
        if not isinstance(results, list):
            continue           # an error block is a dict-like, not a list
        for r in results:
            _add_source(getattr(r, 'url', None), getattr(r, 'title', ''),
                        sources, seen)
    return sources


def _anthropic_stream(spec, system, queue, emit, max_tokens):
    client = _anthropic_client()
    if client is None:
        emit('error', {'message': not_configured_message()})
        while queue:
            yield queue.pop(0)
        return

    with client.messages.stream(
        model=settings.EDDIE_MODEL,
        max_tokens=max_tokens,
        system=system,
        thinking={'type': 'adaptive', 'display': 'summarized'},
        output_config={'effort': 'high'},
        tools=[{'type': 'web_search_20260209', 'name': 'web_search'}],
        messages=_anthropic_messages(spec),
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
        sources = _anthropic_sources(final)
        if sources:
            emit('sources', {'sources': sources[:8]})
        if getattr(final, 'stop_reason', '') == 'refusal':
            emit('error', {'message': "Eddie can't help with that one."})
        while queue:
            yield queue.pop(0)


def _anthropic_once(spec, system, max_tokens):
    """Streams under the hood so a slow turn cannot hit an HTTP timeout."""
    client = _anthropic_client()
    if client is None:
        return '', []
    with client.messages.stream(
        model=settings.EDDIE_MODEL,
        max_tokens=max_tokens,
        system=system,
        thinking={'type': 'adaptive'},
        output_config={'effort': 'medium'},
        tools=[{'type': 'web_search_20260209', 'name': 'web_search'}],
        messages=_anthropic_messages(spec),
    ) as stream:
        final = stream.get_final_message()
    if getattr(final, 'stop_reason', '') == 'refusal':
        return '', []
    text = ''.join(
        getattr(b, 'text', '') for b in (final.content or [])
        if getattr(b, 'type', '') == 'text'
    )
    return text.strip(), _anthropic_sources(final)


# ---- dispatch -------------------------------------------------------------

_STREAMERS = {
    'groq': _groq_stream,
    'gemini': _gemini_stream,
    'anthropic': _anthropic_stream,
}

_ONCERS = {
    'groq': _groq_once,
    'gemini': _gemini_once,
    'anthropic': _anthropic_once,
}


def stream_turn(spec, system, queue, emit, max_tokens=16000):
    """Drive one streaming turn, yielding queued SSE frames as they appear."""
    fn = _STREAMERS.get(_route(spec), _groq_stream)
    return fn(spec, system, queue, emit, max_tokens)


def once(spec, system, max_tokens=2000):
    """One non-streaming turn. Returns (text, sources)."""
    fn = _ONCERS.get(_route(spec), _groq_once)
    return fn(spec, system, max_tokens)
