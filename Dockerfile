# The app as a container, so it runs the same anywhere.
#
# Render built this from a buildpack, which meant the platform decided the
# Python version and how it was started. In a container that is written down
# here instead, which is the point: the same image runs on Cloud Run, on a
# plain server, or on anything else, and moving host again later costs nothing.
#
# Python 3.12 rather than 3.13: Django 4.2 supports 3.12, and every wheel this
# project needs (cryptography, pillow, psycopg2) is published for it. Chasing a
# newer Python here buys nothing and risks a build that only fails in the cloud.
FROM python:3.12-slim

# Nothing is written to disk that needs to survive, so no .pyc clutter, and
# unbuffered output means logs appear when they happen rather than in bursts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, in their own layer. They change far less often than the
# code, so a normal edit rebuilds in seconds instead of reinstalling every wheel.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Static files are baked into the image, so the running container never needs to
# generate them and every instance serves exactly the same bytes. Whitenoise
# serves them, which settings.py switches on whenever DEBUG is false.
#
# collectstatic loads settings, and settings wants a secret key. This one exists
# only inside this build step and never reaches the running container, which
# takes the real one from the environment.
RUN DJANGO_SECRET_KEY=build-only-not-a-real-secret \
    DEBUG=False \
    python manage.py collectstatic --noinput

# Not root. If anything ever gets through, it should not land as the one user
# who can rewrite the image.
RUN useradd --create-home --shell /usr/sbin/nologin trustfirst \
    && chown -R trustfirst:trustfirst /app
USER trustfirst

# Cloud Run hands the port in as $PORT and expects the process to listen on it.
# 8080 is the default it uses, and the fallback keeps `docker run` working.
ENV PORT=8080
EXPOSE 8080

# One worker with threads, which is what a container that scales by instance
# count wants: the platform adds instances under load, so a second worker here
# would only double the memory for the same concurrency.
#
# --timeout 0 because Cloud Run does its own request timing out. Gunicorn
# killing a worker first would turn a slow upload into a fatal error.
CMD exec gunicorn core_project.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 8 \
    --timeout 0 \
    --access-logfile - \
    --error-logfile -
