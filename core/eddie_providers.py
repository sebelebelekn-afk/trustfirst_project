"""
core/eddie_providers.py

The engine behind Eddie, kept separate from the HTTP and storage layer.

TrustFirst runs on donated time and no budget, so the default engine is
Google's Gemini free tier. Anthropic stays supported and is one env var away
for the day there is funding: set EDDIE_PROVIDER=anthropic. Nothing else in
the app changes, because both backends emit the same events and the same
`sources` shape that eddie_views.py already stores and feed.js already renders.

Web search is the one Eddie feature the paid tiers hand over and the free ones
do not. Google offers free Search grounding on gemini-2.5-flash only, and that
model is closed to new API keys, so a new free account gets a quota error the
moment it asks to ground. Eddie therefore treats Gemini grounding as optional:
it tries once, and on a quota refusal it turns search off for an hour and tells
the model to stop implying it looked anything up. Add billing and it switches
itself back on with no code change.

There are two ways Eddie searches without that bill. Groq serves "compound"
models that run a web search server-side, on the same free tier and the same
key as ordinary chat; when the key can reach one, fact-checks are routed to it
and the searches it ran come back as citations. When it cannot, the keyless
Wikipedia lookup in eddie_search.py supplies the evidence instead. Either way
the prompt is written to match what actually happened on the turn, because a
model told it has sources will write as though it does.

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
    # A turn that needs the web goes to the engine that can reach it, before
    # anything else gets a say.
    #
    # This used to sit below the EDDIE_PROVIDER check, which meant pinning a
    # provider for ordinary chat silently switched web search off for every
    # question that needed it -- the one setting nobody would expect to do
    # that. It also beats _needs_depth(), which reads "is it true" as a deep
    # question and sends it to Gemini, whose search is the billed one.
    if spec.get('wants_search'):
        client = _groq_client()
        if client is not None and _groq_search_model(client):
            return 'groq'

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


# A searching model reads whole web pages into its own context before it
# answers, so the room left for our half of the request is much smaller than
# for a plain chat turn. Twenty turns of history and an eight-thousand
# character system prompt is what came back as "Request Entity Too Large".
_GROQ_SEARCH_HISTORY = 6
_GROQ_SEARCH_TURN_CHARS = 700

# Groq charges the tokens you *declare* against the per-minute budget, not the
# ones the model produces, and a compound model's search spends that same
# budget on the pages it reads. Declaring 2,000 for the answer leaves too
# little for the searching. Enough for any reply a chat bubble should hold.
_GROQ_SEARCH_MAX_TOKENS = 1500


def _groq_messages(spec, system, searching=False):
    """Neutral spec -> OpenAI chat messages.

    Attachments are dropped rather than described: _needs_depth() already
    routes anything with a file to a model that can actually read it, so
    reaching here with one means the deep engines are unavailable, and a
    silent drop beats a confident answer about a file nobody looked at.
    """
    msgs = [{'role': 'system', 'content': system}]
    depth = _GROQ_SEARCH_HISTORY if searching else 20
    for turn in (spec.get('history') or [])[-depth:]:
        text = (turn.get('text') or '').strip()
        if searching and len(text) > _GROQ_SEARCH_TURN_CHARS:
            text = text[:_GROQ_SEARCH_TURN_CHARS] + '...'
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


# Groq retires models on its own schedule, and when it does every request comes
# back 404 "The model ... does not exist or you do not have access to it". One
# hardcoded name is therefore a dependency on somebody else's roadmap: Eddie
# stopped answering in chat and in comments the day llama-3.3-70b-versatile went
# away, and nothing in this codebase had changed.
#
# So there is a list, tried in order, and the first one that answers is
# remembered for the life of the process. Setting EDDIE_GROQ_MODEL pins a
# specific model and skips all of this.
#
# Ordered by how likely each is to actually answer on a free tier, not by size.
# The biggest model has the smallest per-minute token budget, so gpt-oss-120b
# sits last: falling off the retired 70b landed straight on it and a one-word
# "Hi" came back 413.
_GROQ_FALLBACKS = [
    'llama-3.3-70b-versatile',
    'meta-llama/llama-4-scout-17b-16e-instruct',
    'llama-3.1-8b-instant',          # small, generous limits, always up
    'qwen/qwen3-32b',
    'openai/gpt-oss-120b',           # largest, tightest budget, last resort
]

# Groq counts the tokens you *ask* for against the per-minute budget, not the
# tokens you use. Asking for 8000 against a tier that allows 8000 a minute means
# a single "Hi" is refused as too large before the model reads a word of it.
# Enough for any answer this app shows, and far enough under the limit that a
# short question is never refused for being long.
_GROQ_MAX_TOKENS = 2000

_GROQ_WORKING = None


def _groq_model():
    pinned = getattr(settings, 'EDDIE_GROQ_MODEL', '')
    if pinned:
        return pinned
    return _GROQ_WORKING or _GROQ_FALLBACKS[0]


def _groq_is_missing_model(exc):
    """A 404 for the model itself, rather than any other failure."""
    text = str(exc)
    return ('model_not_found' in text
            or ('404' in text and 'does not exist' in text))


def _groq_is_too_large(exc):
    """413: this model's per-minute token budget is smaller than the request.

    Worth moving on for the same reason a retired model is. The limit belongs to
    the model and the tier, not to the question, so the next model down may well
    accept exactly the same request — which is what happened here: falling off a
    retired 70b landed on a 120b whose free-tier budget is smaller, and a plain
    "Hi" came back 413.
    """
    text = str(exc).lower()
    return ('413' in text
            # Groq's own wording for this is "Request Entity Too Large", which
            # contains neither "413" nor "request too large" once the SDK has
            # taken the status code off the front of it.
            or 'too large' in text
            or 'payload too large' in text
            or ('rate_limit_exceeded' in text and 'tokens per m' in text))


# What Groq is actually serving today, asked once an hour.
#
# The list above is a guess written down at a point in time, and every name on
# it will be retired eventually: that is exactly how Eddie went silent before,
# when llama-3.3-70b-versatile was withdrawn and the list had no way to know.
# Groq publishes what it currently serves, so ask it, and keep the written list
# only as the order of preference and as the answer when the network is down.
_GROQ_LIVE = {'at': 0.0, 'names': [], 'search': []}
_GROQ_LIVE_TTL = 3600


def _groq_param_size(name):
    """Billions of parameters read off the model name, or 32 when it says none.

    Model ids carry it by convention: llama-3.1-8b-instant, gpt-oss-120b. The
    version number must not be mistaken for it, so only a number immediately
    followed by 'b' at a word boundary counts.
    """
    import re
    sizes = re.findall(r'(\d+(?:\.\d+)?)\s*b\b', name.lower())
    if not sizes:
        return 32.0
    return max(float(s) for s in sizes)


def _groq_live_models(client):
    """Model ids Groq will accept right now, best-first. Never raises."""
    if time.time() - _GROQ_LIVE['at'] < _GROQ_LIVE_TTL and _GROQ_LIVE['names']:
        return _GROQ_LIVE['names']
    names, search = [], []
    try:
        listing = client.models.list()
        for m in (getattr(listing, 'data', None) or []):
            mid = _attr(m, 'id')
            # Only text chat models. Whisper and the guard models are on the
            # same list and cannot answer a message.
            if not mid or not _attr(m, 'active', True):
                continue
            low = mid.lower()
            if any(s in low for s in ('whisper', 'guard', 'tts', 'embed', 'prompt-guard')):
                continue
            # The compound models run tools server-side, web search among them.
            # They are held back for fact-checks rather than left in the
            # ordinary rotation: they are slower than a plain chat model and a
            # "how do I post a clip" does not need a search engine.
            if _is_search_model(mid):
                search.append(mid)
                continue
            names.append(mid)
    except Exception:
        return _GROQ_FALLBACKS            # offline, or an older SDK: use the list

    _GROQ_LIVE['search'] = search

    if not names:
        return _GROQ_FALLBACKS

    # Keep our preference order for the ones we know, then anything new Groq has
    # added, so a replacement model is reachable without a code change.
    known = [m for m in _GROQ_FALLBACKS if m in names]
    rest = [m for m in names if m not in _GROQ_FALLBACKS]
    # Smallest first among the unknown. On a free tier the per-minute token
    # budget shrinks as the model grows, so the big ones are the ones that
    # refuse a short question for being too large. A name with no size in it
    # sorts as mid-range rather than being pushed to either end.
    rest.sort(key=lambda n: (_groq_param_size(n), n))
    _GROQ_LIVE['names'] = known + rest
    _GROQ_LIVE['at'] = time.time()
    return _GROQ_LIVE['names']


# ---- Groq's search-capable models -----------------------------------------
#
# Groq serves "compound" models: the same open-weights models, wrapped in a
# server-side agent that can run a web search before it answers. The search
# happens on Groq's side, it needs no second account and no second key, and it
# is covered by the same free tier as ordinary chat. For TrustFirst that is the
# difference between Eddie guessing at a claim and Eddie checking one.
#
# Whether a given key can reach them is not assumed. Groq publishes what it
# will serve that key, so the list is read at runtime and a compound model is
# used only if it is actually on it. When it is not, fact-checks fall back to
# the keyless Wikipedia lookup in eddie_search.py, which is why that exists.

_GROQ_SEARCH_PREF = ('groq/compound', 'groq/compound-mini')


def _is_search_model(name):
    return 'compound' in (name or '').lower()


def _groq_search_model(client):
    """A Groq model that can search the web, or None if this key has none."""
    try:
        _groq_live_models(client)           # fills _GROQ_LIVE['search']
    except Exception:
        return None
    have = _GROQ_LIVE.get('search') or []
    for name in _GROQ_SEARCH_PREF:
        if name in have:
            return name
    return have[0] if have else None


def can_search_live():
    """Whether Eddie has a real web search available on this deploy.

    Answered from the hourly model-list cache, so asking costs nothing on the
    hot path. False is not a failure: it means fact-checks use the Wikipedia
    lookup instead, and the prompt is written to match.
    """
    client = _groq_client()
    if client is None:
        return False
    return _groq_search_model(client) is not None


_URL_RE = None


def _groq_executed_sources(message):
    """Citations out of a compound model's server-side tool run.

    The shape of executed_tools is Groq's to change, and it has more than one
    form in the wild -- a structured results list on some responses, a text
    blob on others -- so both are read, and anything unrecognised yields no
    sources rather than an exception. Losing the citations is survivable;
    losing the answer is not.
    """
    global _URL_RE
    sources, seen = [], set()
    try:
        tools = _attr(message, 'executed_tools') or []
        for tool in tools:
            # The structured form: output/search_results carrying url + title.
            for key in ('search_results', 'results', 'output'):
                block = _attr(tool, key)
                if isinstance(block, dict):
                    block = block.get('results') or block.get('sources')
                if isinstance(block, list):
                    for item in block:
                        _add_source(_attr(item, 'url') or _attr(item, 'link'),
                                    _attr(item, 'title'), sources, seen)
            # The text form: pull the links out of whatever came back.
            out = _attr(tool, 'output')
            if isinstance(out, str) and out:
                if _URL_RE is None:
                    import re
                    _URL_RE = re.compile(r'https?://[^\s<>"\'\)\]]+')
                for url in _URL_RE.findall(out)[:8]:
                    _add_source(url.rstrip('.,'), '', sources, seen)
    except Exception:
        return sources
    return sources


def _groq_call(client, prefer=None, **kwargs):
    """Call Groq, moving down the list when a model has been retired.

    Only a missing model is retried. A bad key, a rate limit or a network
    failure is raised as it is, because trying four more models would turn one
    clear error into four confusing ones.

    `prefer` puts one model at the front for this turn -- how a fact-check gets
    the searching model without changing what ordinary chat runs on. It is a
    preference, not a requirement: a compound model that fails for any reason
    at all hands the turn back to the plain chat models, because an answer
    without citations still beats no answer.
    """
    pinned = getattr(settings, 'EDDIE_GROQ_MODEL', '')
    available = _groq_live_models(client)
    candidates = [pinned] if pinned else (
        ([_GROQ_WORKING] if _GROQ_WORKING in available else []) +
        [m for m in available if m != _GROQ_WORKING]
    )
    if prefer:
        candidates = [prefer] + [m for m in candidates if m != prefer]
    last = None
    for name in candidates:
        try:
            result = client.chat.completions.create(model=name, **kwargs)
        except Exception as exc:
            last = exc
            retry = _groq_is_missing_model(exc) or _groq_is_too_large(exc)
            # A searching model is an upgrade on the turn, never a dependency
            # of it, so any failure from one moves on rather than surfacing.
            if _is_search_model(name) and len(candidates) > 1:
                retry = True
            if retry and (not pinned or _is_search_model(name)):
                import logging
                logging.getLogger(__name__).warning(
                    'Groq model %s refused (%s), trying the next one', name,
                    'retired' if _groq_is_missing_model(exc) else
                    'request too large' if _groq_is_too_large(exc) else str(exc)[:80])
                # A retirement means the cached list is stale, so throw it away
                # and ask Groq again rather than walking a list of dead names.
                if _groq_is_missing_model(exc):
                    _GROQ_LIVE['at'] = 0.0
                continue
            raise
        # Only plain chat models are remembered. Sticking on a compound model
        # would quietly route every "hi" through a web search.
        if not _is_search_model(name):
            globals()['_GROQ_WORKING'] = name
        return result
    raise last if last else RuntimeError('no Groq model available')


# Appended when a search was promised and then could not be run. Without it
# the model still has "YOU CAN SEARCH THE WEB" above it and writes as though
# it did.
_SEARCH_LOST_NOTE = (
    "\n\nCORRECTION: the web search is not available on this turn after all. "
    "Ignore any instruction above saying you can search. Answer from what you "
    "already know, say plainly that you could not look it up, and never invent "
    "a source, a link or a quotation.")


def _groq_stream(spec, system, queue, emit, max_tokens):
    client = _groq_client()
    if client is None:
        emit('error', {'message': not_configured_message()})
        while queue:
            yield queue.pop(0)
        return

    # A question that needs the web gets the searching model when this key has
    # one. Everything else stays on the fast chat models it has always used.
    prefer = _groq_search_model(client) if spec.get('wants_search') else None
    if prefer:
        emit('searching', {'name': 'web_search'})
        while queue:
            yield queue.pop(0)

    # Two goes: the searching model, then a plain one.
    #
    # _groq_call() already drops a model that refuses the request, but that
    # only covers a failure raised while the call is being made. Groq answered
    # 413 "Request Entity Too Large" partway through, the exception came out of
    # the iteration below rather than out of the call, and the whole turn died
    # with the raw upstream wording on screen. A searching model is an upgrade
    # on the turn, never a dependency of it, so it gets dropped here too.
    #
    # Only before any text has been shown. Once words are on screen, starting
    # a second answer underneath the first is worse than the error.
    attempts = [prefer, None] if prefer else [None]
    for index, attempt in enumerate(attempts):
        last_attempt = index == len(attempts) - 1
        searching = attempt is not None
        # Falling back means the promise in the system prompt is no longer
        # true, so it goes with the model. Telling it that it can search when
        # it cannot is the whole family of bugs this keeps producing.
        this_system = ((spec.get('search_system') or system) if searching
                       else system + _SEARCH_LOST_NOTE)
        text_open = False
        sources, seen = [], set()
        try:
            stream = _groq_call(
                client,
                prefer=attempt,
                messages=_groq_messages(spec, this_system, searching=searching),
                max_tokens=min(max_tokens,
                               _GROQ_SEARCH_MAX_TOKENS if searching
                               else _GROQ_MAX_TOKENS),
                stream=True,
            )
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
                if searching:
                    # Groq reports the searches it ran on the delta on some
                    # responses and on a message block on others, so read both.
                    for holder in (delta, getattr(choices[0], 'message', None)):
                        for found in _groq_executed_sources(holder):
                            _add_source(found['url'], found['title'], sources, seen)
                while queue:
                    yield queue.pop(0)
        except Exception as exc:
            if text_open or last_attempt:
                raise
            import logging
            logging.getLogger(__name__).warning(
                'Groq search model failed mid-turn (%s), answering without it',
                str(exc)[:120])
            continue
        if sources:
            emit('sources', {'sources': sources[:8]})
        while queue:
            yield queue.pop(0)
        return


def _groq_once(spec, system, max_tokens):
    client = _groq_client()
    if client is None:
        return '', []
    prefer = _groq_search_model(client) if spec.get('wants_search') else None
    result = _groq_call(
        client,
        prefer=prefer,
        messages=_groq_messages(spec, system),
        max_tokens=min(max_tokens, _GROQ_MAX_TOKENS),
    )
    choices = getattr(result, 'choices', None) or []
    if not choices:
        return '', []
    message = choices[0].message
    sources = _groq_executed_sources(message) if prefer else []
    return ((getattr(message, 'content', '') or '').strip(), sources[:8])


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
