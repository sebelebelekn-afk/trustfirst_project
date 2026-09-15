"""Send people who arrive on the old hosting address to the app's own name."""

from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponseRedirect


class CanonicalHostRedirectMiddleware:
    """Move browsers from any other hostname onto APP_PUBLIC_URL.

    The app used to answer on the hosting provider's address, and links to it
    are in messages, bookmarks and whatever anyone pasted anywhere. Those still
    work, because Render keeps its own hostname in ALLOWED_HOSTS, so without
    this they would go on quietly showing onrender.com in the address bar
    forever.

    Three things it deliberately does not touch.

    GET and HEAD only. A webhook is a POST, and a redirect on a POST is the
    kind of thing senders either refuse to follow or follow without the body:
    Yoco posts payment confirmations to /api/wallet/yoco-webhook/ against
    whatever address it was registered with, and a payment that does not credit
    a wallet is the worst possible way to find that out.

    Nothing under /api/. Same reason, plus anything already talking to the API
    on the old address keeps working rather than being handed a redirect it was
    not written to expect.

    Not /healthz. It is what the keep-warm ping and any uptime check ask for,
    and the useful answer to "is the app up" is the app answering, not a
    redirect to somewhere else that might be.

    Temporary, not permanent, on purpose. A 301 is cached by browsers more or
    less forever and is genuinely hard to take back; the old address is still a
    working way in if DNS ever goes wrong, and keeping that escape hatch open
    is worth more than the small canonicalisation win. Nothing here is indexed
    for search anyway - the marketing site is a different host.
    """

    SAFE_METHODS = frozenset({'GET', 'HEAD'})
    SKIP_PREFIXES = ('/api/', '/healthz')

    def __init__(self, get_response):
        self.get_response = get_response
        self.canonical_host = ''
        public = (getattr(settings, 'APP_PUBLIC_URL', '') or '').strip()
        if public:
            self.canonical_host = (urlsplit(public).hostname or '').lower()

    def __call__(self, request):
        host = self.canonical_host
        if not host:
            return self.get_response(request)
        if request.method not in self.SAFE_METHODS:
            return self.get_response(request)
        if request.path.startswith(self.SKIP_PREFIXES):
            return self.get_response(request)
        # request.get_host() can carry a port; compare on the hostname alone so
        # a local run on a different port is not redirected to itself.
        current = (request.get_host() or '').split(':')[0].lower()
        if not current or current == host:
            return self.get_response(request)
        # Local development must never be redirected out to production.
        if current in ('localhost', '127.0.0.1', '[::1]', 'testserver'):
            return self.get_response(request)
        target = 'https://%s%s' % (host, request.get_full_path())
        return HttpResponseRedirect(target)
