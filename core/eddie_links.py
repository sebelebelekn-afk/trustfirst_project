"""
core/eddie_links.py

What a link says about itself, before anybody opens it.

Eddie spots a scam the way a careful friend does, by reading the message, and
that works for almost everything except links. A model glances at
"absa-secure-login.co" or "fnb.co.za.verify-now.xyz", sees the bank's name and
moves on; the registered domain, the part that decides who owns the page, is
easy to miss and easy to fake. So links are taken apart here, by rules rather
than by a model, and Eddie is handed the facts: who actually owns each address,
and which of the usual warning signs it carries.

Nothing is fetched. This reads the text of the link and nothing else, and the
note it produces says so, along with the one thing it must never imply: that a
link with no warning signs is safe.
"""

import ipaddress
import re
from urllib.parse import urlsplit

# A link with a scheme or www., or a bare domain ending in something people
# actually paste ("absa-verify.com/login"). Bare domains need a known ending so
# that "e.g." or "Node.js" in a sentence are not mistaken for links.
_URL = re.compile(
    r'(?i)(?<![@\w])('
    r'(?:https?://|www\.)[^\s<>"\'()\[\]]+'
    r'|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+'
    r'(?:co\.za|org\.za|gov\.za|ac\.za|net\.za|web\.za|com|net|org|info|biz|xyz|top|click|online|'
    r'site|website|space|link|live|shop|store|support|app|io|ly|me|cc|co|tv|us|vip|win|loan|'
    r'tk|ml|ga|cf|gq|icu|buzz|cam|zip|mov)'
    # The ending must end there, so "co" never claims the start of ".com".
    r'(?![a-z0-9-])'
    r'(?:/[^\s<>"\'()\[\]]*)?'
    r')')

# Suffixes where the registrable name is one label further in.
_TWO_LEVEL = {
    'co.za', 'org.za', 'gov.za', 'ac.za', 'net.za', 'web.za', 'nom.za', 'mil.za',
    'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'com.au', 'co.nz', 'com.ng', 'co.ke', 'com.br',
}

_SHORTENERS = {
    'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'ow.ly', 'is.gd', 'cutt.ly', 'rb.gy',
    'shorturl.at', 'tiny.cc', 's.id', 'buff.ly', 'rebrand.ly', 't.ly', 'shorte.st',
    'lnkd.in', 'qrco.de', 'bl.ink', 'v.gd',
}

# Endings that cost next to nothing and turn up in scam campaigns far more than
# in ordinary use. A weak sign on its own, and worded as one.
_CHEAP_ENDINGS = {'xyz', 'top', 'click', 'icu', 'buzz', 'cam', 'zip', 'mov', 'tk', 'ml', 'ga', 'cf', 'gq'}

# Names scammers borrow, and the domains that really belong to them. Matched as
# whole words in the address (split on dots and dashes), so "mtn" does not fire
# on "mtnview.com" while "mtn-rewards.com" does.
BRANDS = {
    'absa': ('Absa', {'absa.co.za', 'absa.africa'}),
    'fnb': ('FNB', {'fnb.co.za'}),
    'standardbank': ('Standard Bank', {'standardbank.co.za', 'standardbank.com'}),
    'nedbank': ('Nedbank', {'nedbank.co.za'}),
    'capitec': ('Capitec', {'capitecbank.co.za'}),
    'capitecbank': ('Capitec', {'capitecbank.co.za'}),
    'tymebank': ('TymeBank', {'tymebank.co.za'}),
    'discovery': ('Discovery', {'discovery.co.za'}),
    'investec': ('Investec', {'investec.com', 'investec.co.za'}),
    'sars': ('SARS', {'sars.gov.za'}),
    'efiling': ('SARS eFiling', {'sars.gov.za'}),
    'sassa': ('SASSA', {'sassa.gov.za'}),
    'nsfas': ('NSFAS', {'nsfas.org.za'}),
    'postoffice': ('the Post Office', {'postoffice.co.za'}),
    'sapo': ('the Post Office', {'postoffice.co.za'}),
    'takealot': ('Takealot', {'takealot.com'}),
    'vodacom': ('Vodacom', {'vodacom.co.za'}),
    'mtn': ('MTN', {'mtn.co.za', 'mtn.com'}),
    'telkom': ('Telkom', {'telkom.co.za'}),
    'cellc': ('Cell C', {'cellc.co.za'}),
    'eskom': ('Eskom', {'eskom.co.za'}),
    'paypal': ('PayPal', {'paypal.com'}),
    'whatsapp': ('WhatsApp', {'whatsapp.com', 'whatsapp.net'}),
    'facebook': ('Facebook', {'facebook.com', 'fb.com'}),
    'instagram': ('Instagram', {'instagram.com'}),
    'netflix': ('Netflix', {'netflix.com'}),
    'apple': ('Apple', {'apple.com', 'icloud.com'}),
    'icloud': ('Apple', {'apple.com', 'icloud.com'}),
    'microsoft': ('Microsoft', {'microsoft.com', 'live.com', 'outlook.com'}),
    'google': ('Google', {'google.com', 'google.co.za'}),
    'trustfirst': ('TrustFirst', {'gettrustfirst.co.za'}),
}

MAX_LINKS = 5


def find_links(text):
    """The links in a piece of text, in order, without duplicates."""
    seen, out = set(), []
    for m in _URL.finditer(text or ''):
        raw = m.group(1).rstrip('.,;:!?\'"')
        if raw.lower() not in seen:
            seen.add(raw.lower())
            out.append(raw)
    return out


def registered_domain(host):
    """The part of a host name that somebody registered: absa.co.za for
    online.absa.co.za, verify-now.xyz for fnb.co.za.verify-now.xyz."""
    labels = [l for l in (host or '').lower().strip('.').split('.') if l]
    if len(labels) >= 3 and '.'.join(labels[-2:]) in _TWO_LEVEL:
        return '.'.join(labels[-3:])
    return '.'.join(labels[-2:])


def check(raw):
    """Take one link apart. Returns {'link', 'host', 'domain', 'signs',
    'brand_ok'}, where signs are plain-English warning signs."""
    url = raw if re.match(r'(?i)^https?://', raw) else 'http://' + raw
    explicit_http = raw.lower().startswith('http://')
    try:
        parts = urlsplit(url)
        host = (parts.hostname or '').lower()
        netloc = parts.netloc
        port = parts.port
    except ValueError:
        return {'link': raw, 'host': '', 'domain': '', 'signs': ['is not a well-formed address'], 'brand_ok': None}

    signs = []
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if is_ip:
        signs.append('points at a bare IP address instead of a name, which real companies almost never do')
    domain = host if is_ip else registered_domain(host)

    if '@' in netloc:
        signs.append('has an @ sign in the address, an old trick to hide where it really goes')
    if 'xn--' in host:
        signs.append('uses look-alike characters from other alphabets in its name')
    if domain in _SHORTENERS:
        signs.append('is a link shortener, so the real destination is hidden')
    if explicit_http:
        signs.append('is not encrypted (http, not https)')
    if port and port not in (80, 443):
        signs.append('uses an unusual port number')
    ending = domain.rsplit('.', 1)[-1] if domain and not is_ip else ''
    if ending in _CHEAP_ENDINGS:
        signs.append('ends in .%s, a cheap ending scams use a lot (not proof on its own)' % ending)
    if not is_ip and host.count('.') >= 4:
        signs.append('has an unusually long chain of names before the real domain')

    brand_ok = None
    words = set(re.split(r'[.\-]', host)) if not is_ip else set()
    for word, (name, official) in BRANDS.items():
        if word in words:
            if domain in official:
                brand_ok = 'This is %s\'s own domain.' % name
            else:
                signs.append('uses the name %s but is not %s\'s website (%s)'
                             % (name, name, ', '.join(sorted(official))))
            break

    return {'link': raw, 'host': host, 'domain': domain, 'signs': signs, 'brand_ok': brand_ok}


def note(text):
    """The block handed to Eddie, or '' when the text has no links."""
    links = find_links(text)[:MAX_LINKS]
    if not links:
        return ''
    lines = ['LINK CHECKS (worked out from the text of each link by rules, not by a model;'
             ' nothing was opened)']
    for raw in links:
        c = check(raw)
        shown = raw if len(raw) <= 120 else raw[:117] + '...'
        line = '- %s: registered domain %s.' % (shown, c['domain'] or 'unknown')
        if c['brand_ok']:
            line += ' ' + c['brand_ok']
        if c['signs']:
            line += ' Warning signs: it ' + '; it '.join(c['signs']) + '.'
        else:
            line += ' No automatic warning signs.'
        lines.append(line)
    lines.append('No warning sign is not proof that a link is safe: these checks cannot see who'
                 ' runs the page, and a real domain can still be used to mislead.')
    return '\n'.join(lines)
