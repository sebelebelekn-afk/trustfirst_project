from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.shortcuts import render

def feed(request, **kwargs):
    """The whole app is this one page.

    Shared links (/post/<id>, /clip/<id>, /profile/<name>) route here too and
    capture an id in the path; the client reads location.pathname on boot to open
    what was shared. The captures are swallowed here rather than being handed to
    the template, which is why this takes **kwargs.
    """
    return render(request, 'core/feed.html')


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