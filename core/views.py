from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import render

from . import seo


def feed(request, target_id=None, username=None):
    """The whole app is this one page.

    Shared links (/post/<id>, /clip/<id>, /profile/<name>) route here too and
    capture an id in the path; the client reads location.pathname on boot to
    open what was shared.

    The captures used to be swallowed. They are now the one thing this view
    does with any care: a link pasted into WhatsApp or X is read by a crawler
    that runs no JavaScript, and what it found here was <title>TrustFirst</title>
    and nothing else, so every shared post arrived as a bare grey URL. The
    <head> now describes what the link points at -- see core/seo.py for what
    is shown and, as importantly, what is not.
    """
    name = getattr(getattr(request, 'resolver_match', None), 'url_name', '') or ''
    kind = {'post_permalink': 'post', 'clip_permalink': 'clip',
            'profile_permalink': 'profile'}.get(name)
    if kind:
        tags = seo.describe(kind, target_id or username)
    else:
        tags = seo.default('/')
    return render(request, 'core/feed.html', {
        'seo': tags,
        'seo_ld': seo.ld_json(tags.get('ld')),
    })


def robots_txt(request):
    """There was none, so every crawler asked, got a 404 and guessed."""
    resp = HttpResponse(seo.robots_txt(), content_type='text/plain; charset=utf-8')
    resp['Cache-Control'] = 'public, max-age=3600'
    return resp


def sitemap_xml(request):
    """Only what the app would show a stranger. See core/seo.py."""
    try:
        body = seo.sitemap_xml()
    except Exception:   # a sitemap that 500s teaches Google to stop asking
        body = seo.last_sitemap() or (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>')
    resp = HttpResponse(body, content_type='application/xml; charset=utf-8')
    resp['Cache-Control'] = 'public, max-age=600'
    return resp


def _apk_url():
    return (getattr(settings, 'ANDROID_APK_URL', '') or '').strip()


def download_android(request):
    """A permanent address for the Android build.

    The file itself lives in R2 and its name changes with every build. Without
    this, the download link on the marketing site would have to be edited by
    hand after each one, and every link anybody had already shared would rot.
    Point people here forever; point ANDROID_APK_URL at the current file.
    """
    from django.http import HttpResponseRedirect
    url = _apk_url()
    if url:
        return HttpResponseRedirect(url)
    return render(request, 'core/legal/no_download.html', status=404)


def download_status(request):
    """Whether a build exists, for the marketing site to ask.

    The site is served from a different origin, so this one endpoint allows any
    reader. It exposes a single boolean and a URL that is public anyway, and
    nothing about anybody using the app.
    """
    url = _apk_url()
    resp = JsonResponse({'android': bool(url), 'url': url or None})
    resp['Access-Control-Allow-Origin'] = '*'
    resp['Cache-Control'] = 'public, max-age=300'
    return resp


def legal_page(request, page):
    """Privacy, terms and the rest as ordinary web pages.

    They used to be JavaScript strings inside feed.js, which meant they existed
    only inside the app: they could not be linked to, the Share button on them
    handed out trustfirst.app/privacy which was a 404, and Google Play needs a
    privacy policy at a real URL before it will take a listing. Now the app
    loads the same address anybody else would.

    company_reg is the CIPC registration number, empty until there is one. The
    Terms read differently either way, so that the day the company is formed is a
    setting on the server rather than an edit to this repository.
    """
    return render(request, 'core/legal/%s.html' % page, {
        'company_reg': settings.COMPANY_REG_NUMBER,
    })


def service_worker(request):
    """Serve the service worker from the site root so it controls the whole origin scope."""
    path = settings.BASE_DIR / 'core' / 'static' / 'core' / 'js' / 'sw.js'
    response = FileResponse(open(path, 'rb'), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


def manifest(request):
    """Serve the PWA manifest from the site root."""
    path = settings.BASE_DIR / 'core' / 'static' / 'manifest.json'
    return FileResponse(open(path, 'rb'), content_type='application/manifest+json')


def healthz(request):
    """Alive, in as few cycles as possible.

    Two jobs, and deliberately nothing else. Cloud Run wants a cheap way to see
    that a container came up, and something has to be pinged on a schedule to
    keep one instance alive so nobody pays for a cold start with their time.

    No database, no session, no template. A ping that touched Postgres would
    hold a connection open every few minutes for no reason, and a ping that
    failed when the database blinked would look like the app was down when it
    was not.
    """
    resp = JsonResponse({'ok': True})
    # Never let a CDN or the browser answer this on the server's behalf. A
    # cached ping keeps nothing warm, which is the one thing it is for.
    resp['Cache-Control'] = 'no-store'
    return resp


def ratelimited(request, exception):
    """What a caller sees when they have gone too fast.

    django-ratelimit raises Ratelimited, and Django turns an unhandled one into
    403 Forbidden with an HTML error page. Both halves of that are wrong here.
    403 tells a client it is not allowed to do this at all, when the truth is
    "not this often" — the one status that says so, and that every HTTP client
    already knows to back off on, is 429. And an HTML body reaches a caller that
    asked for JSON and only ever parses JSON, so the app would fall back to a
    generic "could not" message instead of the real reason.
    """
    return JsonResponse(
        {'error': 'Too many requests. Wait a moment and try again.'},
        status=429,
    )
