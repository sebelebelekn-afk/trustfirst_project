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