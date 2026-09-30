"""
core/seo.py

What a shared link says about itself before anybody opens it.

The app is one page. /post/<id>, /clip/<id> and /profile/<name> all serve the
same shell and the client opens the right thing after it boots. That is fine
for a person and useless for everything that reads a link without running
JavaScript: WhatsApp, X, Facebook, iMessage, Google. Every one of them read the
same six words -- <title>TrustFirst</title> -- and showed a bare grey URL with
no picture, no text and no author. Every share anyone ever made was wasted at
the moment it landed in a chat.

This module looks up what the link points at and hands the template enough to
describe it: a title, a line of text, a picture, and structured data saying
what kind of thing it is. The client still boots and opens the real post; none
of this is for people, it is for the machines that stand between people.

Two rules that are not negotiable, and are tested:

  It never breaks the page. A missing row, a private account, Supabase down,
  a timeout -- every one of them falls back to describing the app, with a 200.
  The shell has to load for the person tapping the link whatever the crawler
  would have seen.

  It never says more than the app would. A hidden post, an unpublished one, a
  private or banned account, a group post: all of these describe the app and
  not the thing. A preview is a copy of the content that lives in other
  people's chat history, so the bar is what the app shows a stranger, not what
  the database holds.

Indexing is a separate question from previewing, and stricter. A preview
follows a share somebody chose to make; an index entry is Google offering the
page to anyone. Posts were written into what people understood to be a closed,
verified community, so a post is marked noindex unless its visibility is
explicitly 'public'. Nothing in the app sets that yet -- the column exists and
is null on every row -- which is deliberate: the day a composer control sets
it, the server already honours it, and nothing here needs to change. A clip is
indexable when its audience is 'everyone', because that is a choice the person
made in the composer. A profile is indexable unless the account is private.
"""

import json
import logging
import time

import requests
from django.conf import settings

log = logging.getLogger(__name__)

# The picture a link shows when the thing itself has none, or cannot be shown.
# On the marketing site, which is static, always up, and served from the edge.
DEFAULT_IMAGE = 'https://gettrustfirst.co.za/og.jpg'
DEFAULT_TITLE = 'TrustFirst'
DEFAULT_DESCRIPTION = ('A social app that knows who is real. Verified accounts, '
                       'encrypted messages, and creators keep 80% of every gift.')

# A crawler will not wait long, and a preview that arrives after the chat app
# gave up is the same as no preview. Three seconds for Supabase, which answers
# a primary-key lookup in well under one.
TIMEOUT = 3.0

# Rows are cached in-process for a short while. A link pasted into a group
# chat is fetched once per member who has it unfurled, within seconds of each
# other, and there is no reason to ask Supabase the same question thirty times.
_TTL = 120
_cache = {}


def _select(table, params):
    """One PostgREST read with the service key, or None. Never raises."""
    base = getattr(settings, 'SUPABASE_URL', '')
    key = getattr(settings, 'SUPABASE_SERVICE_KEY', '')
    if not base or not key:
        return None
    try:
        r = requests.get(
            base.rstrip('/') + '/rest/v1/' + table,
            params=params,
            headers={'apikey': key, 'Authorization': 'Bearer ' + key,
                     'Accept': 'application/json'},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as exc:
        log.info('seo lookup failed for %s: %s', table, exc)
        return None


def _one(table, params):
    rows = _select(table, dict(params, limit=1))
    if rows and isinstance(rows, list):
        return rows[0]
    return None


def _cached(kind, key, loader):
    now = time.time()
    hit = _cache.get((kind, key))
    if hit and now - hit[0] < _TTL:
        return hit[1]
    value = loader()
    _cache[(kind, key)] = (now, value)
    # Keep the dict from growing without bound on a long-lived worker.
    if len(_cache) > 2000:
        for k in [k for k, v in _cache.items() if now - v[0] >= _TTL]:
            _cache.pop(k, None)
    return value


# ---- what may be shown -------------------------------------------------------

def _looks_like_uuid(s):
    import re
    return bool(re.match(r'^[0-9a-fA-F-]{32,36}$', s or ''))


def _author(user_id):
    if not user_id:
        return None
    return _one('users', {
        'id': 'eq.' + user_id,
        'select': 'id,username,display_name,full_name,avatar_url,bio,verified,'
                  'id_verified,is_banned,is_locked,privacy_settings',
    })


def _account_public(u):
    """Whether this account is one the app shows to a stranger at all."""
    if not u or u.get('is_banned') or u.get('is_locked'):
        return False
    ps = u.get('privacy_settings') or {}
    if isinstance(ps, str):
        try:
            ps = json.loads(ps)
        except ValueError:
            ps = {}
    return not bool(ps.get('private_account'))


def _post_public(p):
    if not p or p.get('is_hidden'):
        return False
    if (p.get('status') or 'published') != 'published':
        return False
    if p.get('group_id'):
        return False
    if p.get('approved') is False:
        return False
    vis = (p.get('visibility') or 'public').lower()
    return vis in ('public', 'everyone')


def _clip_public(c):
    if not c or c.get('is_hidden'):
        return False
    return (c.get('audience') or 'everyone').lower() in ('everyone', 'public')


def _http_image(url):
    """An image URL a crawler can fetch, or None.

    Eddie's avatar is a data: URI, which is a picture to a browser and a
    thousand characters of nothing to a link unfurler.
    """
    url = (url or '').strip()
    if url.startswith('https://') or url.startswith('http://'):
        return url
    return None


def _name(u):
    return (u.get('display_name') or u.get('full_name') or u.get('username')
            or 'Someone on TrustFirst')


def _handle(u):
    un = u.get('username')
    return '@' + un if un else ''


def _verified(u):
    return bool(u.get('verified') or u.get('id_verified'))


def _snippet(text, limit=160):
    text = ' '.join((text or '').split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0]
    return cut + '…'


# ---- building the description ------------------------------------------------

def _public_url(path):
    base = getattr(settings, 'APP_PUBLIC_URL', '') or 'https://app.gettrustfirst.co.za'
    return base.rstrip('/') + path


def default(path='/'):
    return {
        'title': DEFAULT_TITLE,
        'description': DEFAULT_DESCRIPTION,
        'image': DEFAULT_IMAGE,
        'url': _public_url(path),
        'type': 'website',
        'card': 'summary_large_image',
        'noindex': False,
        'video': None,
        'ld': None,
    }


def _post(post_id):
    if not _looks_like_uuid(post_id):
        return None
    p = _one('posts', {
        'id': 'eq.' + post_id,
        'select': 'id,user_id,text_content,media_url,media_urls,media_type,'
                  'thumbnail_url,video_url,post_type,is_hidden,status,group_id,'
                  'approved,visibility,created_at,like_count,comment_count',
    })
    if not _post_public(p):
        return None
    u = _author(p.get('user_id'))
    if not _account_public(u):
        return None

    text = (p.get('text_content') or '').strip()
    urls = p.get('media_urls') or []
    image = _http_image((urls[0] if urls else None) or p.get('media_url')
                        or p.get('thumbnail_url'))
    # A video's media_url is the video, not a picture of it.
    if (p.get('media_type') or '') == 'video' and not p.get('thumbnail_url'):
        image = None
    video = _http_image(p.get('video_url')) if (p.get('media_type') == 'video') else None

    name = _name(u)
    who = name + (' ' + _handle(u) if _handle(u) else '')
    title = (_snippet(text, 70) if text else '%s posted on TrustFirst' % name)
    desc = _snippet(text, 200) if text else 'A post by %s on TrustFirst.' % who
    if _verified(u):
        desc = (desc + ' · Verified account') if text else (desc.rstrip('.') + ', a verified account.')

    ld = {
        '@context': 'https://schema.org',
        '@type': 'SocialMediaPosting',
        'url': _public_url('/post/%s/' % p['id']),
        'headline': _snippet(text, 110) or title,
        'articleBody': text[:2000] if text else None,
        'datePublished': p.get('created_at'),
        'author': {'@type': 'Person', 'name': name,
                   'url': _public_url('/profile/%s/' % u['username']) if u.get('username') else None},
        'image': image,
        'interactionStatistic': [
            {'@type': 'InteractionCounter', 'interactionType': 'https://schema.org/LikeAction',
             'userInteractionCount': p.get('like_count') or 0},
            {'@type': 'InteractionCounter', 'interactionType': 'https://schema.org/CommentAction',
             'userInteractionCount': p.get('comment_count') or 0},
        ],
    }
    out = default('/post/%s/' % p['id'])
    out.update({
        'title': title + ' · TrustFirst',
        'description': desc,
        'image': image or DEFAULT_IMAGE,
        'card': 'summary_large_image' if image else 'summary',
        'type': 'article',
        'video': video,
        # Explicit opt-in only. See the module docstring.
        'noindex': (p.get('visibility') or '').lower() not in ('public', 'everyone'),
        'ld': _strip(ld),
    })
    return out


def _clip(clip_id):
    if not _looks_like_uuid(clip_id):
        return None
    c = _one('trustclips', {
        'id': 'eq.' + clip_id,
        'select': 'id,user_id,caption,video_url,thumbnail_url,audience,is_hidden,'
                  'created_at,view_count,like_count',
    })
    if not _clip_public(c):
        return None
    u = _author(c.get('user_id'))
    if not _account_public(u):
        return None

    caption = (c.get('caption') or '').strip()
    image = _http_image(c.get('thumbnail_url'))
    video = _http_image(c.get('video_url'))
    name = _name(u)
    title = _snippet(caption, 70) if caption else '%s on TrustClips' % name
    desc = ('%s · a TrustClip by %s' % (_snippet(caption, 150), name)) if caption \
        else 'A TrustClip by %s on TrustFirst.' % name

    ld = {
        '@context': 'https://schema.org',
        '@type': 'VideoObject',
        'name': title,
        'description': desc,
        'thumbnailUrl': image,
        'contentUrl': video,
        'uploadDate': c.get('created_at'),
        'url': _public_url('/clip/%s/' % c['id']),
        'author': {'@type': 'Person', 'name': name},
        'interactionStatistic': {
            '@type': 'InteractionCounter',
            'interactionType': 'https://schema.org/WatchAction',
            'userInteractionCount': c.get('view_count') or 0,
        },
    }
    out = default('/clip/%s/' % c['id'])
    out.update({
        'title': title + ' · TrustFirst',
        'description': desc,
        'image': image or DEFAULT_IMAGE,
        'card': 'summary_large_image' if image else 'summary',
        'type': 'video.other',
        'video': video,
        'noindex': False,
        'ld': _strip(ld),
    })
    return out


def _profile(username):
    username = (username or '').strip().lstrip('@')
    if not username or len(username) > 64:
        return None
    # ilike, not eq: usernames are stored in the case they were typed and a
    # link is typed in whatever case the person remembers.
    u = _one('users', {
        'username': 'ilike.' + username.replace('%', '').replace('_', r'\_'),
        'select': 'id,username,display_name,full_name,avatar_url,bio,verified,'
                  'id_verified,is_banned,is_locked,privacy_settings,followers_count,'
                  'follower_count,post_count,created_at',
    })
    if not _account_public(u):
        return None

    name = _name(u)
    handle = _handle(u)
    bio = _snippet(u.get('bio') or '', 160)
    image = _http_image(u.get('avatar_url'))
    tail = 'Verified on TrustFirst.' if _verified(u) else 'On TrustFirst.'
    desc = (bio + ' · ' + tail) if bio else ('%s %s · %s' % (name, handle, tail)).strip()
    followers = u.get('followers_count') or u.get('follower_count') or 0

    ld = {
        '@context': 'https://schema.org',
        '@type': 'ProfilePage',
        'url': _public_url('/profile/%s/' % u['username']),
        'mainEntity': _strip({
            '@type': 'Person',
            'name': name,
            'alternateName': handle or None,
            'description': bio or None,
            'image': image,
            'identifier': u.get('username'),
            'interactionStatistic': {
                '@type': 'InteractionCounter',
                'interactionType': 'https://schema.org/FollowAction',
                'userInteractionCount': followers,
            },
        }),
    }
    out = default('/profile/%s/' % u['username'])
    out.update({
        'title': ('%s (%s) · TrustFirst' % (name, handle)) if handle else name + ' · TrustFirst',
        'description': desc,
        'image': image or DEFAULT_IMAGE,
        # An avatar is square; the big card crops it badly.
        'card': 'summary',
        'type': 'profile',
        'noindex': False,
        'ld': _strip(ld),
    })
    return out


def _strip(d):
    """Drop None values so the JSON-LD does not assert 'image: null'."""
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [_strip(v) for v in d if v is not None]
    return d


def describe(kind, key):
    """The tags for one shared link. Always returns a dict; never raises."""
    loaders = {'post': _post, 'clip': _clip, 'profile': _profile}
    loader = loaders.get(kind)
    fallback_path = {'post': '/post/%s/', 'clip': '/clip/%s/', 'profile': '/profile/%s/'}
    path = fallback_path.get(kind, '/%s/') % (key or '')
    if not loader or not key:
        return default('/')
    try:
        found = _cached(kind, key, lambda: loader(key))
    except Exception as exc:   # anything at all: the page still has to load
        log.warning('seo describe %s %s failed: %s', kind, key, exc)
        found = None
    if found:
        return found
    out = default(path)
    # A link to something that is not shown to strangers should not be
    # indexed under that address either.
    out['noindex'] = True
    return out


def ld_json(ld):
    """JSON safe to inline inside a <script>: no way to close the tag early."""
    if not ld:
        return ''
    s = json.dumps(ld, ensure_ascii=False, separators=(',', ':'))
    return s.replace('<', '\\u003C').replace('>', '\\u003E').replace('&', '\\u0026')


# ---- what Google may list -----------------------------------------------------

_SITEMAP_TTL = 600
_sitemap = {'at': 0.0, 'body': ''}


def sitemap_xml():
    """Every address Google is welcome to, with when it changed."""
    now = time.time()
    if _sitemap['body'] and now - _sitemap['at'] < _SITEMAP_TTL:
        return _sitemap['body']

    urls = [(_public_url('/'), None, 'daily', '1.0')]
    for page in ('privacy', 'terms', 'cookies', 'accessibility', 'help'):
        urls.append((_public_url('/%s/' % page), None, 'monthly', '0.3'))

    users = _select('users', {
        'select': 'username,updated_at,created_at,is_banned,is_locked,privacy_settings',
        'is_banned': 'eq.false', 'is_locked': 'eq.false',
        'order': 'created_at.desc', 'limit': 1000,
    }) or []
    for u in users:
        if u.get('username') and _account_public(u):
            urls.append((_public_url('/profile/%s/' % u['username']),
                         u.get('updated_at') or u.get('created_at'), 'weekly', '0.6'))

    clips = _select('trustclips', {
        'select': 'id,created_at,audience,is_hidden',
        'is_hidden': 'eq.false', 'audience': 'eq.everyone',
        'order': 'created_at.desc', 'limit': 1000,
    }) or []
    for c in clips:
        urls.append((_public_url('/clip/%s/' % c['id']), c.get('created_at'), 'monthly', '0.7'))

    posts = _select('posts', {
        'select': 'id,created_at,visibility,is_hidden,status',
        'is_hidden': 'eq.false', 'status': 'eq.published', 'visibility': 'eq.public',
        'order': 'created_at.desc', 'limit': 1000,
    }) or []
    for p in posts:
        urls.append((_public_url('/post/%s/' % p['id']), p.get('created_at'), 'monthly', '0.7'))

    from xml.sax.saxutils import escape
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, mod, freq, pri in urls:
        parts.append('<url><loc>%s</loc>%s<changefreq>%s</changefreq><priority>%s</priority></url>' % (
            escape(loc),
            ('<lastmod>%s</lastmod>' % escape(str(mod)[:10])) if mod else '',
            freq, pri))
    parts.append('</urlset>')
    body = '\n'.join(parts)
    _sitemap.update({'at': now, 'body': body})
    return body


def last_sitemap():
    """The last sitemap built, for when building a new one fails."""
    return _sitemap.get('body') or ''


def robots_txt():
    return '\n'.join([
        '# Shared posts, clips and profiles are welcome. The API is not a page.',
        'User-agent: *',
        'Allow: /',
        'Disallow: /api/',
        'Disallow: /healthz',
        'Disallow: /sw.js',
        '',
        'Sitemap: ' + _public_url('/sitemap.xml'),
        '',
    ])
