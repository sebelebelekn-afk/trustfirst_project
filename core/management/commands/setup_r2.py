"""Point the R2 bucket at this site and check that uploads actually work.

Run once, after the R2 environment variables are set:

    python manage.py setup_r2 --origin https://trustfirst.app

Without a CORS policy the browser refuses to PUT to R2 and every upload
silently falls back to Supabase, which looks like R2 doing nothing at all. This
sets the policy and then proves the round trip rather than assuming it.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Configure the R2 bucket CORS policy and verify a presigned upload."

    def add_arguments(self, parser):
        parser.add_argument(
            '--origin', action='append', dest='origins', default=[],
            help='Site origin allowed to upload, e.g. https://trustfirst.app. '
                 'Repeat for more than one. Defaults to ALLOWED_HOSTS over https.',
        )
        parser.add_argument(
            '--check-only', action='store_true',
            help='Report the current policy without changing anything.',
        )

    def handle(self, *args, **opts):
        from core.api_views import _r2_client, _r2_ready

        missing = [n for n in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY',
                               'R2_BUCKET', 'R2_PUBLIC_BASE')
                   if not getattr(settings, n, '')]
        if missing:
            raise CommandError('Not configured. Missing: ' + ', '.join(missing))
        if not _r2_ready():
            raise CommandError('R2 settings are incomplete.')

        client = _r2_client()
        bucket = settings.R2_BUCKET

        origins = opts['origins'] or [
            'https://' + h for h in settings.ALLOWED_HOSTS
            if h not in ('*',) and not h.startswith('.')
        ]
        if not origins:
            raise CommandError('No origin to allow. Pass --origin https://your-site.')

        if opts['check_only']:
            try:
                current = client.get_bucket_cors(Bucket=bucket)
                self.stdout.write('Current CORS rules:')
                for rule in current.get('CORSRules', []):
                    self.stdout.write('  ' + str(rule))
            except Exception as exc:
                self.stdout.write(self.style.WARNING('No CORS policy set (%s)' % exc))
            return

        # The presigned URL signs Content-Type and Cache-Control, so the browser
        # sends both, so both have to be allowed or the preflight fails.
        rules = [{
            'AllowedOrigins': origins,
            'AllowedMethods': ['PUT', 'GET', 'HEAD'],
            'AllowedHeaders': ['Content-Type', 'Cache-Control'],
            'ExposeHeaders': ['ETag'],
            'MaxAgeSeconds': 3600,
        }]
        client.put_bucket_cors(Bucket=bucket, CORSConfiguration={'CORSRules': rules})
        self.stdout.write(self.style.SUCCESS(
            'CORS set on %s for: %s' % (bucket, ', '.join(origins))))

        # Prove it: sign an upload, use it, read the object back, then tidy up.
        import urllib.request
        key = '_healthcheck/setup.txt'
        body = b'trustfirst r2 ok'
        url = client.generate_presigned_url(
            'put_object',
            Params={'Bucket': bucket, 'Key': key, 'ContentType': 'text/plain'},
            ExpiresIn=300,
        )
        req = urllib.request.Request(url, data=body, method='PUT',
                                     headers={'Content-Type': 'text/plain'})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status not in (200, 204):
                    raise CommandError('Presigned upload returned %s' % resp.status)
        except Exception as exc:
            raise CommandError('Presigned upload failed: %s' % exc)
        self.stdout.write(self.style.SUCCESS('Presigned upload works.'))

        public = settings.R2_PUBLIC_BASE.rstrip('/') + '/' + key
        try:
            with urllib.request.urlopen(public, timeout=30) as resp:
                got = resp.read()
            if got == body:
                self.stdout.write(self.style.SUCCESS('Public read works: ' + public))
            else:
                self.stdout.write(self.style.WARNING('Public URL served unexpected content.'))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                'Public read failed (%s). Turn on public access for the bucket, or '
                'point R2_PUBLIC_BASE at a connected custom domain.' % exc))

        client.delete_object(Bucket=bucket, Key=key)
        self.stdout.write('Done.')
