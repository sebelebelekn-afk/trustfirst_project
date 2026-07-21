"""
core/eddie_insights.py

Creator-growth context for Eddie: real numbers, never guesses.

When someone asks Eddie for content ideas or how they are doing, Eddie needs to
answer from that person's actual account rather than inventing plausible
statistics. This module builds a compact, factual brief -- reach, engagement,
posting rhythm, apparent niche, and what is currently performing on TrustFirst
-- which gets appended to Eddie's system prompt for that turn only.

Two deliberate limits:

  * It is only built when the question is actually about growth. Every message
    would otherwise pay for several database round trips.
  * Platform trends are anonymous aggregates: keyword and format counts across
    public posts, never "user X posted Y". Eddie is a growth coach, not a way
    to inspect other people's accounts.

TrustFirst is new, so most of these numbers are small or zero. That is stated
plainly in the brief so Eddie coaches honestly instead of pretending a fresh
account has data behind it.
"""

import datetime
import re
import time
from collections import Counter

import requests
from django.conf import settings

from .eddie_views import _sb_get, _sb_headers


# Questions that deserve the analytics round trip.
_GROWTH_HINTS = (
    'content idea', 'contentidea', 'ideas', 'idea for', 'what should i post',
    'what to post', 'post about', 'grow', 'growth', 'analytic', 'performance',
    'performing', 'my stats', 'statistics', 'engagement', 'niche', 'trend',
    'trending', 'followers', 'reach', 'views', 'audience', 'algorithm',
    'more likes', 'go viral', 'viral', 'best time to post', 'improve my',
    'how am i doing', 'my account', 'my posts',
)

# Words that carry no signal about what someone posts about.
_STOP = set("""
a about above after again against all am an and any are aren as at be because been
before being below between both but by can cant cannot could couldnt did didnt do
does doesnt doing dont down during each few for from further had hadnt has hasnt
have havent having he her here hers herself him himself his how i im ive id if in
into is isnt it its itself just lets me more most mustnt my myself no nor not of
off on once only or other ought our ours ourselves out over own same shant she
should shouldnt so some such than that thats the their theirs them themselves then
there theres these they theyre this those through to too under until up very was
wasnt we were werent what whats when where which while who whos whom why with wont
would wouldnt you youre youve your yours yourself yourselves get got go going one
two really much many lot new like love good great best today day time now still
even also back come came make made take took thing things people want need know
see look going guys really actually literally
think thinks thought haha hahaha lol lmao yeah yea nah okay ok hey hi hello
nice cool wow omg please thanks thank sorry maybe sure right well yes yep
create created creating worst best better worse bruh man dude gonna wanna
""".split())


def wants_growth_help(text):
    """True when the message is asking about content, performance or growth."""
    t = (text or '').lower()
    return any(h in t for h in _GROWTH_HINTS)


def _sb_count(table, params):
    """Row count via PostgREST's exact-count header. Returns 0 on failure."""
    try:
        headers = dict(_sb_headers())
        headers['Prefer'] = 'count=exact'
        headers['Range'] = '0-0'
        r = requests.get(
            settings.SUPABASE_URL + '/rest/v1/' + table,
            headers=headers, params=dict(params, select='id'), timeout=8,
        )
        rng = r.headers.get('Content-Range', '')
        if '/' in rng:
            total = rng.split('/')[-1]
            return int(total) if total.isdigit() else 0
    except Exception:
        pass
    return 0


def _keywords(texts, limit=8):
    """Most repeated meaningful words and hashtags across some post text."""
    words, tags = Counter(), Counter()
    for t in texts:
        for tag in re.findall(r'#(\w{2,30})', t or ''):
            tags[tag.lower()] += 1
        for w in re.findall(r"[a-zA-Z']{3,20}", (t or '').lower()):
            w = w.strip("'")
            if w and w not in _STOP:
                words[w] += 1
    top_tags = [('#' + k, n) for k, n in tags.most_common(limit)]
    top_words = [(k, n) for k, n in words.most_common(limit)]
    return top_tags, top_words


def _fmt_when(rows):
    """Which day and hour this person actually posts, from their own history."""
    days, hours = Counter(), Counter()
    for r in rows:
        raw = (r.get('created_at') or '')[:19].replace('T', ' ')
        try:
            dt = datetime.datetime.strptime(raw, '%Y-%m-%d %H:%M:%S')
        except Exception:
            continue
        days[dt.strftime('%A')] += 1
        hours[dt.hour] += 1
    day = days.most_common(1)[0][0] if days else None
    hour = hours.most_common(1)[0][0] if hours else None
    return day, hour


def _platform_trends():
    """Anonymous view of what is working on TrustFirst in the last 14 days.

    Keyword and format counts only. No usernames, no attributed content: this
    exists to ground ideas in what performs here, not to expose accounts.
    """
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=14)).isoformat() + 'Z'
    rows = _sb_get('posts', {
        'is_hidden': 'eq.false',
        'created_at': 'gte.' + since,
        'select': 'text_content,post_type,media_type,like_count,comment_count,view_count',
        'order': 'like_count.desc',
        'limit': '60',
    })
    if not rows:
        return None
    tags, words = _keywords([r.get('text_content') or '' for r in rows], limit=6)
    formats = Counter()
    for r in rows:
        f = r.get('media_type') or r.get('post_type') or 'text'
        formats[f] += 1
    engaged = [r for r in rows if (r.get('like_count') or 0) > 0]
    return {
        'sample': len(rows),
        'tags': tags,
        'words': words,
        'formats': formats.most_common(4),
        'with_engagement': len(engaged),
    }


def build_creator_context(user_id):
    """A factual brief on this creator, or None if it cannot be built.

    Everything here is measured. Eddie is told explicitly not to invent numbers
    beyond it, and told when a figure is too small to draw conclusions from.
    """
    if not user_id:
        return None

    posts = _sb_get('posts', {
        'user_id': 'eq.' + user_id,
        'is_hidden': 'eq.false',
        'select': 'id,text_content,post_type,media_type,like_count,comment_count,'
                  'view_count,share_count,tags,created_at',
        'order': 'created_at.desc',
        'limit': '100',
    })
    users = _sb_get('users', {'id': 'eq.' + user_id, 'select': 'username,full_name,bio'})
    me = users[0] if users else {}

    followers = _sb_count('follows', {'following_id': 'eq.' + user_id})
    following = _sb_count('follows', {'follower_id': 'eq.' + user_id})

    n = len(posts)
    likes = sum((p.get('like_count') or 0) for p in posts)
    comments = sum((p.get('comment_count') or 0) for p in posts)
    views = sum((p.get('view_count') or 0) for p in posts)

    lines = ["=== THIS CREATOR'S REAL NUMBERS (measured, do not invent others) ==="]
    who = me.get('username') or me.get('full_name') or 'this user'
    lines.append('Handle: @%s' % who)
    if me.get('bio'):
        lines.append('Bio: %s' % me['bio'][:200])
    lines.append('Followers: %d | Following: %d | Public posts: %d' % (followers, following, n))

    if n:
        lines.append('Totals across those posts: %d likes, %d comments, %d views'
                     % (likes, comments, views))
        lines.append('Averages per post: %.1f likes, %.1f comments, %.1f views'
                     % (likes / n, comments / n, views / n))

        best = max(posts, key=lambda p: (p.get('like_count') or 0) + (p.get('comment_count') or 0))
        btext = (best.get('text_content') or '').strip().replace('\n', ' ')
        if btext:
            lines.append('Best performing post (%d likes, %d comments): "%s"'
                         % (best.get('like_count') or 0, best.get('comment_count') or 0,
                            btext[:160]))

        # Posting rhythm, from their own timestamps.
        recent = 0
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        for p in posts:
            raw = (p.get('created_at') or '')[:19].replace('T', ' ')
            try:
                if datetime.datetime.strptime(raw, '%Y-%m-%d %H:%M:%S') >= cutoff:
                    recent += 1
            except Exception:
                pass
        lines.append('Posted %d time(s) in the last 30 days.' % recent)
        day, hour = _fmt_when(posts)
        if day is not None:
            lines.append('They usually post on %s, around %02d:00 UTC.' % (day, hour))

        formats = Counter((p.get('media_type') or p.get('post_type') or 'text') for p in posts)
        lines.append('Formats they use: ' + ', '.join('%s x%d' % (k, v) for k, v in formats.most_common(4)))

        # Niche, inferred from what they actually write about. Their own handle
        # and display name are dropped: self-mentions are not a topic.
        own_tags, own_words = _keywords(
            [(p.get('text_content') or '') for p in posts] + [me.get('bio') or ''], limit=10)
        self_words = set()
        for part in ((me.get('username') or '') + ' ' + (me.get('full_name') or '')).lower().split():
            if part:
                self_words.add(part)
        own_tags = [(t, c) for t, c in own_tags if t.lstrip('#') not in self_words]
        own_words = [(w, c) for w, c in own_words if w not in self_words]
        niche_bits = [t for t, _ in own_tags[:6]] + [w for w, _ in own_words[:6]]
        if niche_bits:
            lines.append('Recurring topics in their own posts: ' + ', '.join(niche_bits))
        else:
            lines.append('No clear recurring topic yet: too little text to infer a niche.')

        if n < 5 or likes < 10:
            lines.append('NOTE: this sample is very small. Say so, and avoid '
                         'confident claims about what "works" for them.')
    else:
        lines.append('They have not posted publicly yet, so there is no '
                     'performance data. Do not invent any. Help them start.')

    trends = _platform_trends()
    lines.append('')
    lines.append('=== WHAT IS PERFORMING ON TRUSTFIRST (last 14 days, anonymous) ===')
    if not trends or trends['sample'] < 8:
        lines.append('TrustFirst is brand new, so there is not enough platform '
                     'activity to call any trend yet. Say that honestly rather '
                     'than inventing trends, and coach from first principles.')
    else:
        lines.append('Sampled %d recent public posts; %d had any engagement.'
                     % (trends['sample'], trends['with_engagement']))
        if trends['tags']:
            lines.append('Common hashtags: ' + ', '.join('%s (%d)' % (t, c) for t, c in trends['tags']))
        if trends['words']:
            lines.append('Common topics: ' + ', '.join('%s (%d)' % (w, c) for w, c in trends['words']))
        if trends['formats']:
            lines.append('Formats in use: ' + ', '.join('%s x%d' % (f, c) for f, c in trends['formats']))

    return '\n'.join(lines)


def _recent_activity_post_ids(user_id, limit=40):
    """Posts this person recently watched, liked, saved or replied to.

    Ordered newest-first per source so "lately" really means lately. post_views
    is read too, though nothing writes to it yet, so it simply contributes
    nothing until it is wired up.
    """
    ids, seen = [], set()
    sources = [
        ('watch_history', 'user_id',   'watched_at'),
        ('likes',         'user_id',   'created_at'),
        ('bookmarks',     'user_id',   'created_at'),
        ('comments',      'user_id',   'created_at'),
        ('post_views',    'viewer_id', 'viewed_at'),
    ]
    for table, ucol, tcol in sources:
        rows = _sb_get(table, {
            ucol: 'eq.' + user_id, 'select': 'post_id',
            'order': tcol + '.desc', 'limit': '30',
        })
        for r in (rows or []):
            pid = r.get('post_id')
            if pid and pid not in seen:
                seen.add(pid)
                ids.append(pid)
    return ids[:limit]


# Writing the summary costs a model call and several queries, and "lately" does
# not change minute to minute, so each person's line is held for a few hours.
# Only the first open in that window pays for it.
_SUMMARY_CACHE = {}
_SUMMARY_TTL = 6 * 60 * 60


def build_interest_summary(user_id, force=False):
    """What this person has actually been into lately.

    Returns {'summary': str, 'topics': [str], 'sample': int}. The summary is
    written by the model from real viewing history, never from a canned list;
    when there is nothing to go on it says so instead of inventing interests.
    """
    empty = {'summary': '', 'topics': [], 'sample': 0}
    if not user_id:
        return empty

    now = time.time()
    hit = _SUMMARY_CACHE.get(user_id)
    if hit and not force and (now - hit[0]) < _SUMMARY_TTL:
        return hit[1]

    ids = _recent_activity_post_ids(user_id)
    if not ids:
        return empty

    posts = _sb_get('posts', {
        'id': 'in.(' + ','.join(ids) + ')',
        'select': 'text_content,tags,post_type,media_type',
        'limit': '40',
    })
    if not posts:
        return empty

    texts = [(p.get('text_content') or '') for p in posts]
    tags, words = _keywords(texts, limit=12)

    # Hashtags first (explicit), then repeated words (implicit).
    topics = [t for t, _ in tags] + [w.title() for w, _ in words]
    topics = [t for i, t in enumerate(topics) if t not in topics[:i]][:12]
    if not topics:
        return empty

    material = ' | '.join(t.strip().replace('\n', ' ')[:120] for t in texts if t.strip())[:1800]

    # Asking for the topic names as well as the sentence produces real subjects
    # ("Formula 1", "Car interiors") instead of the raw repeated words a keyword
    # count gives you ("think", "haha").
    prompt = (
        "Below is what one person has been watching, liking and saving on a "
        "social app recently.\n\n"
        "Reply in exactly this shape and nothing else:\n"
        "SUMMARY: <one sentence, max 22 words, starting exactly with "
        "\"Lately you've been\", specific and concrete, the way a friend would "
        "describe it. No hashtags, quotes or emoji.>\n"
        "TOPICS: <3 to 8 short topic names, comma separated, each 1-3 words, "
        "properly capitalised, e.g. Formula 1, Car interiors, Linux>\n\n"
        "Only use subjects that actually appear below. Invent nothing.\n\n"
        "Recurring words: " + ', '.join(topics[:8]) + "\n\n"
        "The posts themselves:\n<<<\n" + (material or '(no text)') + "\n>>>"
    )

    summary, ai_topics = '', []
    try:
        from . import eddie_providers
        spec = {'history': [], 'prompt': prompt, 'attachments': [],
                'route_text': 'summarise interests'}
        text, _ = eddie_providers.once(
            spec,
            "You summarise what someone has been interested in, in a warm and "
            "specific one-liner. You never invent interests that are not in the "
            "material you were given, and you follow the requested format exactly.",
            300)
        for line in (text or '').splitlines():
            low = line.strip()
            if low.upper().startswith('SUMMARY:'):
                summary = ' '.join(low[8:].split()).strip().strip('"')
            elif low.upper().startswith('TOPICS:'):
                ai_topics = [t.strip().strip('.#"') for t in low[7:].split(',')]
                ai_topics = [t for t in ai_topics if 1 <= len(t) <= 30][:8]
    except Exception:
        pass

    if not summary:
        # The model is optional. A plain, honest sentence from the real topics
        # beats showing nothing.
        nice = [t.lstrip('#').title() for t in topics[:3]]
        summary = ("Lately you've been into " +
                   (', '.join(nice[:-1]) + ' and ' + nice[-1] if len(nice) > 1 else nice[0]) + '.')

    final_topics = ai_topics or [t.lstrip('#').title() for t in topics[:8]]

    # Their own handle and name are not interests, however often they appear in
    # mentions of them.
    me = (_sb_get('users', {'id': 'eq.' + user_id, 'select': 'username,full_name'}) or [{}])[0]
    self_words = set()
    for part in ((me.get('username') or '') + ' ' + (me.get('full_name') or '')).lower().split():
        if part:
            self_words.add(part)
    final_topics = [t for t in final_topics if t.lower().strip('#') not in self_words]

    result = {'summary': summary, 'topics': final_topics, 'sample': len(posts)}
    _SUMMARY_CACHE[user_id] = (now, result)
    return result


# What Eddie is told about being a growth coach. Appended to the system prompt
# only on growth questions, so ordinary chat is unaffected.
GROWTH_BRIEF = """
YOU ARE ALSO THIS PERSON'S GROWTH COACH
When someone asks for content ideas, how they are performing, what their niche
is, or how to grow, help immediately and concretely. Never stall, never ask them
to go and look at their own analytics, and never reply with a generic listicle
that ignores what is in front of you.

Use the real numbers block above as your only source of facts about them:
- Quote their actual figures when relevant. Do not round them up flatteringly.
- If the numbers are tiny or zero, say so kindly and coach accordingly. A new
  account needs a starting plan, not engagement optimisation.
- Never invent a statistic, a follower count, a growth percentage, or a trend.
  If you do not have it, say you do not have it.

Content ideas should be specific enough to film or write today: give the hook,
the format, and why it suits this person's topics, not "post more consistently".
Offer around five, and tie them to what they already post about.

On trends: you can only speak to what the numbers block actually shows about
TrustFirst. You cannot browse the live web right now, so do not claim to know
what is trending on other platforms this week. If they ask, say plainly that you
cannot check live trends at the moment, then help with what does not expire:
their own performance, their niche, formats, hooks and posting rhythm.
"""
