"""
Report what Eddie can actually do on this deploy.

Written after an afternoon of guessing. Whether Eddie can search the web
depends on whether the Groq key can reach a compound model, and there was no
way to find that out except to ask Eddie a question and read the tea leaves in
its answer. Run this on the server instead:

    python manage.py eddie_status
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Show which Eddie backends are configured and whether web search works"

    def add_arguments(self, parser):
        parser.add_argument(
            '--test', action='store_true',
            help='Actually run a search through the model and print what '
                 'comes back, or the exact error if it fails.')

    def handle(self, *args, **options):
        from django.conf import settings
        from core import eddie_providers, eddie_image, eddie_search

        def line(label, value, good=None):
            if good is True:
                value = self.style.SUCCESS(str(value))
            elif good is False:
                value = self.style.WARNING(str(value))
            self.stdout.write('  %-26s %s' % (label + ':', value))

        self.stdout.write(self.style.MIGRATE_HEADING('\nKeys'))
        for name in ('GROQ_API_KEY', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY',
                     'CLOUDFLARE_API_TOKEN', 'OPENAI_API_KEY',
                     'POLLINATIONS_TOKEN'):
            have = bool(getattr(settings, name, ''))
            line(name, 'set' if have else 'not set', have)

        self.stdout.write(self.style.MIGRATE_HEADING('\nChat'))
        line('active engine', eddie_providers.active() or 'NONE CONFIGURED',
             eddie_providers.is_configured())
        line('EDDIE_PROVIDER', getattr(settings, 'EDDIE_PROVIDER', '') or '(auto)')

        self.stdout.write(self.style.MIGRATE_HEADING('\nWeb search'))
        client = eddie_providers._groq_client()
        if client is None:
            line('live search', 'NO - no usable Groq key', False)
        else:
            try:
                names = eddie_providers._groq_live_models(client)
            except Exception as exc:
                names = []
                line('groq model list', 'failed: %s' % str(exc)[:80], False)
            found = eddie_providers._GROQ_LIVE.get('search') or []
            line('search-capable models', ', '.join(found) or 'none served to this key',
                 bool(found))
            line('live search', 'YES via %s' % found[0] if found
                 else 'NO - falls back to reference lookup', bool(found))
            if names:
                line('chat models available', len(names))

        wiki = 'on' if eddie_search._enabled() else 'off (EDDIE_FACTCHECK)'
        line('reference fallback', wiki, eddie_search._enabled())

        self.stdout.write(self.style.MIGRATE_HEADING('\nImages'))
        provider = eddie_image._provider()
        line('provider', provider, provider != 'pollinations')
        if provider == 'pollinations' and not getattr(settings, 'POLLINATIONS_TOKEN', ''):
            self.stdout.write(self.style.WARNING(
                '  Anonymous Pollinations: small model, 768px cap, their watermark.\n'
                '  Set CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN for FLUX and no mark.'))
        line('prompt rewriting',
             getattr(settings, 'EDDIE_IMAGE_REWRITE', 'on'))
        line('Eddie AI mark',
             getattr(settings, 'EDDIE_IMAGE_WATERMARK', 'on')
             + ('' if provider != 'pollinations' else ' (not applied: backend brands its own)'))

        if options.get('test'):
            self._live_test(eddie_providers, eddie_search)
        self.stdout.write('')

    def _live_test(self, eddie_providers, eddie_search):
        """Make a real searching call. The point is the error when it fails.

        Everything above reports what is configured. This reports what
        actually happens, which is the only thing that settles an argument
        about whether search works.
        """
        self.stdout.write(self.style.MIGRATE_HEADING('\nLive search test'))
        client = eddie_providers._groq_client()
        model = eddie_providers._groq_search_model(client) if client else None
        if not model:
            self.stdout.write(self.style.WARNING(
                '  Skipped: no search-capable model available.'))
            return

        spec = {'history': [], 'attachments': [],
                'prompt': 'In one sentence, what is the date today and one '
                          'thing in the news right now?',
                'wants_search': True,
                'search_system': eddie_search.SEARCH_SYSTEM}
        self.stdout.write('  model: %s' % model)
        try:
            text, sources = eddie_providers._groq_once(
                spec, eddie_search.SEARCH_SYSTEM, 1500)
        except Exception as exc:
            self.stdout.write(self.style.ERROR('  FAILED: %s' % exc))
            self.stdout.write(
                '  ^ this is the exact upstream error. 413/"too large" means '
                'the request plus the\n    declared max_tokens exceeded the '
                'per-minute budget.')
            return
        self.stdout.write(self.style.SUCCESS('  OK'))
        self.stdout.write('  answer : %s' % (text or '(empty)')[:300])
        self.stdout.write('  sources: %s' % (
            ', '.join(s['url'] for s in sources[:4]) or 'none reported'))
