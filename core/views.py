from django.conf import settings
from django.http import FileResponse
from django.shortcuts import render

def feed(request):
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