"""
core/eddie_search.py

Evidence for Eddie's fact-checks, on a budget of nothing.

Eddie's system prompt has always told it to "search the web" when somebody
tags it under a post asking whether a claim is true. It could not. Every
search backend Eddie can reach through a model -- Gemini's Search grounding,
Anthropic's web_search tool -- is billed, so on a free key the instruction was
a promise the code could not keep, and the worst possible failure mode: a
model told it has sources will write as though it has them.

So this module gets Eddie real evidence without a key and without a card.

WHAT IT USES

Wikipedia's action API. Not a fallback chosen for being free -- it is the only
general-purpose lookup this app can make that is both keyless and allowed. The
alternatives were measured, not assumed:

  * DuckDuckGo's Instant Answer API   keyless, but returns an empty envelope
                                      for any real question. Useless here.
  * lite.duckduckgo.com               keyless and it does return results, but
                                      it is scraping, it breaks their terms,
                                      and a server IP doing it all day gets
                                      blocked. Not shipping that.
  * Google News RSS                   works, and the feed's own copyright
                                      notice restricts it to personal feed
                                      readers. Not ours to use.
  * public SearXNG instances          none of the reachable ones still serve
                                      format=json; they return the HTML page.
  * Marginalia's public API           did not respond at all.

Wikipedia is weakest on the last few hours of news and strongest on exactly
what people actually argue about under a post: health claims, science myths,
history, geography, companies, public figures, past events. That is the trade,
and Eddie is told about it in plain words rather than left to guess.

WHAT IT DOES NOT DO

It does not decide anything. It hands the model passages and the URLs they
came from, and the prompt in eddie_views.py tells the model to say which parts
of its answer rest on them and which do not. A lookup that finds nothing is
not an error: Eddie simply answers from what it knows and says so.

Nothing here may cost the user their answer. Every failure -- no network, a
429, a slow response, malformed JSON -- returns no evidence and lets the turn
carry on.
"""

import re
import threading
import time

import requests
from django.conf import settings


API = 'https://en.wikipedia.org/w/api.php'

# Wikimedia asks every client to identify itself and give them a way to get in
# touch before they block you. An anonymous default User-Agent is how you end
# up rate-limited with no warning.
UA = ('TrustFirstEddie/1.0 (https://gettrustfirst.co.za; '
      'support@gettrustfirst.co.za) python-requests')

# The whole lookup sits in front of a user waiting for a reply, so it gets a
# hard ceiling rather than requests' default of "however long it takes".
TIMEOUT = 6.0

# Enough to triangulate a claim, few enough to stay inside the prompt budget.
PAGES = 4
EXTRACT_CHARS = 1200


# ---- staying welcome ------------------------------------------------------
#
# Wikimedia throttles anonymous traffic per IP, and it answers 429 rather than
# slowing you down. Hammering through a throttle is how an IP gets blocked
# outright, so a 429 stops all lookups for a while instead of turning every
# message into another refused request.
#
# The pause doubles each time and resets on the first success, because the two
# things that go wrong here are opposite. One 429 is usually a burst clearing
# in under a minute, and sitting out a quarter of an hour for it means every
# fact-check in that window silently loses its evidence. Being throttled over
# and over is the other thing entirely, and deserves to be waited out.

_BLOCKED_UNTIL = 0.0
_BLOCK_FOR = 60
_BLOCK_MAX = 900
_BLOCK_NEXT = _BLOCK_FOR

_CACHE = {}
_CACHE_TTL = 1800
_CACHE_MAX = 256
_LOCK = threading.Lock()


def _enabled():
    """EDDIE_FACTCHECK=off turns the lookups off without a deploy."""
    mode = (getattr(settings, 'EDDIE_FACTCHECK', '') or 'on').strip().lower()
    return mode not in ('off', 'false', '0', 'no')


def _blocked():
    return time.time() < _BLOCKED_UNTIL


def _block():
    global _BLOCKED_UNTIL, _BLOCK_NEXT
    _BLOCKED_UNTIL = time.time() + _BLOCK_NEXT
    _BLOCK_NEXT = min(_BLOCK_NEXT * 2, _BLOCK_MAX)


def _unblock():
    """A call got through, so forget how long the last pause was."""
    global _BLOCK_NEXT
    _BLOCK_NEXT = _BLOCK_FOR


def _cache_get(key):
    with _LOCK:
        hit = _CACHE.get(key)
        if not hit:
            return None
        at, value = hit
        if time.time() - at > _CACHE_TTL:
            _CACHE.pop(key, None)
            return None
        return value


def _cache_put(key, value):
    with _LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            # Oldest first. The map is small enough that sorting it is cheaper
            # than maintaining an ordering alongside it.
            for old, _ in sorted(_CACHE.items(), key=lambda kv: kv[1][0])[:_CACHE_MAX // 4]:
                _CACHE.pop(old, None)
        _CACHE[key] = (time.time(), value)


# ---- is this a fact-check? ------------------------------------------------

# Deliberately about *checking a claim*, not about facts in general. "What year
# did the Berlin Wall fall" is a question Eddie answers from memory perfectly
# well; "is this true" is somebody asking it to go and look.
_CHECK = re.compile(r"""
      \bis\s+(this|that|it|he|she|they|any\s+of\s+this)\s+
        (really\s+|actually\s+)?(true|real|fake|accurate|correct|right|legit|a\s+scam)\b
    | \b(true|real|fake|accurate|legit)\s*\?
    | \bfact[\s-]?check
    | \bdebunk
    | \b(is|are)\s+(this|that|these|those)\s+(claims?|facts?|numbers?|stats?|statistics)\b
    | \bany\s+(proof|truth|evidence|source)\b
    | \b(proof|source|sources|citation)\s*\?
    | \bverify\s+(this|that|it)\b
    | \bdid\s+(this|that|it|he|she|they)\s+(really|actually)\b
    | \bdid\s+\w+\s+(really|actually)\s+\w+
    | \breally\s+(happen|true|say\s+that)\b
    | \b(misinformation|disinformation|hoax)\b
    | \bis\s+there\s+any\s+truth\b
""", re.I | re.X)


def looks_like_check(text):
    """Whether this message is asking Eddie to check a claim, not answer one."""
    return bool(text) and bool(_CHECK.search(str(text)))


# Asking Eddie to go and find something out, rather than to check a claim.
# Different question, same need: it must not answer from memory and present
# the result as though it looked it up.
#
# "What did so-and-so say" is in here because that is the shape of the answer
# that goes most badly wrong. Asked what a named person said about something,
# a model will produce a fluent quotation, in quotation marks, with a date --
# and if it has nothing real to draw on it will assemble one out of what
# people like that tend to say. That is not a hedge-worthy inaccuracy, it is
# words in a real person's mouth.
_LOOKUP = re.compile(r"""
      \b(go\s+online|browse\s+(the\s+)?web|get\s+online)\b
    | \bsearch\s+(the\s+web|online|google|for\s+me|it)\b
    | \b(look|read)\s+(it|this|that|them)\s+up\b
    | \bgoogle\s+(it|this|that)\b
    | \b(latest|recent|current|newest|breaking|up[\s-]?to[\s-]?date)\s+
        (news|updates?|information|info|figures?|numbers?|prices?|scores?|results?|stats?)\b
    | \bnews\s+(about|on|for|regarding)\b
    | \b(latest|newest|current)\s+(on|about|with|from)\b
    | \bwhat(?:'s|\s+is|\s+are)\s+(happening|going\s+on|new|the\s+latest)\b
    | \bwhat\s+did\s+[\w.'-]+\s+(say|said|tell|claim|announce)\b
    | \b(who|when)\s+said\b
    | \bdid\s+[\w.'-]+\s+(ever\s+)?(say|claim|announce|tweet)\b
    | \bquote\s+(from|by)\b
""", re.I | re.X)


def wants_lookup(text):
    """Whether this message is asking Eddie to find something out."""
    return bool(text) and bool(_LOOKUP.search(str(text)))


def needs_evidence(text):
    """Either kind: check this claim, or go and find this out."""
    return looks_like_check(text) or wants_lookup(text)


# Questions that have nothing to do with the world outside this app: using
# TrustFirst, asking Eddie to make something, asking what it reckons, or
# saying hello. These are the exception; everything else gets searched when
# there is a search to run.
_NO_SEARCH = re.compile(r"""
      \btrustfirst\b
    | \b(my|this)\s+(account|profile|password|post|clip|story|feed|wallet|coins|settings)\b
    | \bhow\s+(do|can)\s+i\s+\w*\s*(post|upload|delete|change|turn|switch|find|get\s+to|verify|log)\b
    | \b(draw|generate|create|make|write|compose)\s+(me\s+)?(an?|some|a\s+few)\b
    | \bwrite\s+(me\s+)?(a|an|some)\b
    | \b(your|you)\s+(favourite|favorite|opinion|think|reckon|feel)\b
    | \bwhat\s+do\s+you\s+(think|reckon|prefer)\b
    | ^\s*(hi|hey|hello|yo|sup|thanks|thank\s+you|ok(ay)?|lol|haha)\b
    | \b(tell|say)\s+(me\s+)?(a\s+)?(joke|something\s+funny|story)\b
""", re.I | re.X)


def should_search(text):
    """Whether a live web search is worth running for this message.

    The default is yes. Eddie was answering questions about the world out of
    its own memory and presenting the result as fact, which is how it produced
    a quotation from a public figure who never said it. If there is a search
    available, the honest default is to use it and answer from what comes
    back.

    The exceptions are the things the web cannot help with: how to use this
    app, asking Eddie to make or write something, asking its opinion, and
    saying hello. Those are answered as before.
    """
    text = (text or '').strip()
    if not text:
        return False
    # An explicit ask always wins, even if it also looks like app help.
    if needs_evidence(text):
        return True
    return not _NO_SEARCH.search(text)


# ---- turning a claim into a query -----------------------------------------

# Words that carry no signal in a search index. Question words are in here on
# purpose: "who" and "when" tell Wikipedia nothing, the nouns beside them do.
_STOP = frozenset("""
a an and are as at be been being but by can could did do does doing for from
had has have he her hers him his how i if in into is it its me my of on or our
ours she should so than that the their theirs them then there these they this
those to too was we were what when where which who whom why will with would you
your yours am not no nor just really actually very please guys anyone someone
eddie true false fake real legit accurate correct check fact facts claim claims
proof source sources verify tell know think say said seen heard
""".split())

_FRAMING = re.compile(
    r'^\s*(hey\s+|ok(ay)?[,\s]+|so\s+|but\s+|wait[,\s]+|@?eddie[,:\s]+)+', re.I)


def _query(claim):
    """The search string for a claim, or '' when there is nothing to search.

    Strips the framing ("@eddie is this true?") down to the words that
    actually name the thing being claimed, because that is what a search index
    matches on. If stripping leaves too little to go on, the cleaned sentence
    is used as-is rather than searching for nothing.
    """
    text = str(claim or '')
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'[@#](\w+)', r'\1', text)
    text = _FRAMING.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text)
    kept = [w for w in words if w.lower() not in _STOP]
    # Two content words is the floor for a query that means anything. Below
    # that the claim was mostly framing, so search what they actually wrote.
    if len(kept) < 2:
        kept = words
    return ' '.join(kept[:14])


# ---- the lookup -----------------------------------------------------------

def _wikipedia(query):
    """Top pages for a query with their intros, as [{url, title, text}].

    One round trip, not two: generator=search feeds the matched titles
    straight into prop=extracts, so the search and the article text come back
    together. Never raises.
    """
    try:
        r = requests.get(API, params={
            'action': 'query',
            'format': 'json',
            'formatversion': '2',
            'generator': 'search',
            'gsrsearch': query,
            'gsrlimit': str(PAGES),
            'gsrnamespace': '0',          # articles only, no talk or user pages
            'prop': 'extracts|info',
            'exintro': '1',               # the lead section, which states the claim
            'explaintext': '1',           # no wiki markup for the model to parse
            'exlimit': 'max',
            'inprop': 'url',
            'redirects': '1',
        }, headers={'User-Agent': UA, 'Accept': 'application/json'},
            timeout=TIMEOUT)
    except Exception:
        return []

    if r.status_code == 429:
        _block()
        return []
    if r.status_code != 200:
        return []
    _unblock()

    try:
        pages = (r.json().get('query') or {}).get('pages') or []
    except Exception:
        return []

    out = []
    # 'index' is the search rank. Without sorting on it the pages come back in
    # page-id order, which is arbitrary, and the best match can end up last.
    for page in sorted(pages, key=lambda p: p.get('index', 99)):
        extract = (page.get('extract') or '').strip()
        title = (page.get('title') or '').strip()
        url = page.get('fullurl') or ''
        if not extract or not title or not url:
            continue
        if len(extract) > EXTRACT_CHARS:
            extract = extract[:EXTRACT_CHARS].rsplit(' ', 1)[0] + '...'
        out.append({'url': url, 'title': title, 'text': extract})
    return out


def find_evidence(claim):
    """Passages bearing on a claim, as [{url, title, text}]. Never raises."""
    if not _enabled() or _blocked():
        return []
    query = _query(claim)
    if not query:
        return []

    key = query.lower()
    hit = _cache_get(key)
    if hit is not None:
        return hit

    try:
        found = _wikipedia(query)
    except Exception:
        found = []
    _cache_put(key, found)
    return found


# ---- handing it to the model ----------------------------------------------

_HEADER = """
EVIDENCE YOU JUST LOOKED UP
Somebody is asking you to check a claim, so you searched Wikipedia and these
are the article openings that came back. They are real and they were fetched
seconds ago. Work from them.

"""

_RULES = """
How to use these:
- Read them before you answer. If they settle the claim, say so and name the
  article you got it from, in plain words - "Wikipedia's article on X says..."
  - rather than a bare link.
- If they do not cover the claim, say that outright and answer from what you
  already know, making clear which is which. Never stretch a passage to cover
  something it does not say.
- Never cite an article that is not in this list, and never invent a URL.
- This was a Wikipedia lookup, not a live web search. For something that
  happened in the last day or two, say plainly that you cannot check it yet.
"""


def brief(claim):
    """(prompt_addition, sources) for a claim, or ('', []) when nothing helps.

    sources is in the same shape the rest of Eddie already emits and stores,
    so the chat bubble renders these citations exactly like the paid search
    backends' ones.
    """
    found = find_evidence(claim)
    if not found:
        return '', []

    lines = [_HEADER]
    for i, item in enumerate(found, 1):
        lines.append('[%d] %s\n    %s\n    %s\n' % (
            i, item['title'], item['url'], item['text']))
    lines.append(_RULES)
    sources = [{'url': i['url'], 'title': i['title']} for i in found]
    return ''.join(lines), sources


def no_evidence_note():
    """What to tell the model when a lookup was asked for and nothing came back.

    Without this the model falls back on the system prompt's old assumption
    that it can search, and writes as though it did.

    It also has to say what Eddie *can* do. "I don't have the ability to browse
    the web" is true and useless: somebody who asked Eddie to go online wants
    to know what happens next, and a bare no reads as a broken feature rather
    than a limit.
    """
    return (
        "\n\nLOOKING THIS UP\nYou tried and found nothing usable. You can check "
        "reference material, but you cannot browse the live web, so anything "
        "from the last day or two, or behind a login, is out of reach.\n"
        "Answer from what you already know and be plain that it is not a fresh "
        "check. Say in one short sentence what you could not reach and why, "
        "then give them what you do know - not a flat refusal and nothing "
        "else.\nNever invent a citation, a link, or a quotation, and never "
        "describe yourself as having looked something up when you did not.")


LIVE_NOTE = """

YOU CAN SEARCH THE WEB
You have a working web search on this turn. Use it.

Search before you answer anything about the world - people, companies, events,
numbers, dates, what somebody said - rather than answering from memory and
hoping. If somebody asks you to go online, to check, or for the latest on
something, that is exactly what this is for: do it, do not tell them you
cannot. Then:
- Lead with the verdict, and name the sources you actually read.
- Cite only pages you genuinely retrieved on this turn. If the search came back
  with nothing useful, say so and answer from what you know, making clear that
  is what you are doing.
- Never invent a link, a study or a statistic.
"""
