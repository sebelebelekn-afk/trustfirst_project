from django.conf import settings
from django.http import FileResponse
from django.shortcuts import render

def feed(request, **kwargs):
    """The whole app is this one page.

    Shared links (/post/<id>, /clip/<id>, /profile/<name>) route here too and
    capture an id in the path; the client reads location.pathname on boot to open
    what was shared. The captures are swallowed here rather than being handed to
    the template, which is why this takes **kwargs.
    """
    return render(request, 'core/feed.html')


def legal_page(request, page):
    """Privacy, terms and the rest as ordinary web pages.

    They used to be JavaScript strings inside feed.js, which meant they existed
    only inside the app: they could not be linked to, the Share button on them
    handed out trustfirst.app/privacy which was a 404, and Google Play needs a
    privacy policy at a real URL before it will take a listing. Now the app
    loads the same address anybody else would.
    """
    return render(request, 'core/legal/%s.html' % page)


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