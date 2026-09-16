"""
core/tests_eddie_image.py

Tests for the keyless image backend's failure handling.

Image generation went down and the only evidence anybody had was Eddie saying
"The image service could not make that one" -- one sentence covering a refusal,
a throttle, a timeout and an HTML error page alike, with nothing written to the
log. These tests exist so the difference between those is kept.

The retry is the substantive part. Pollinations rations anonymous traffic per
IP and every request from this app leaves on the same one, so a busy minute is
indistinguishable from a broken backend unless you try twice.
"""

import logging

from django.test import SimpleTestCase, override_settings

from . import eddie_image


JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 64
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


class _Resp:
    def __init__(self, status, content=b'', text='', headers=None):
        self.status_code = status
        self.content = content
        self.text = text
        self.headers = headers or {}


class PollinationsTests(SimpleTestCase):

    def setUp(self):
        self.calls = []
        self._real_get = eddie_image.requests.get
        self.addCleanup(setattr, eddie_image.requests, 'get', self._real_get)
        # The retry sleeps; tests should not. Put the real backoff back after,
        # so one test cannot quietly disable it for the rest of the suite.
        self.addCleanup(setattr, eddie_image, '_POLL_RETRY_AFTER',
                        eddie_image._POLL_RETRY_AFTER)
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def _serve(self, *responses):
        """Answer successive calls with these responses."""
        queue = list(responses)

        def fake_get(url, **kwargs):
            self.calls.append({'url': url, 'headers': kwargs.get('headers') or {}})
            return queue.pop(0) if queue else _Resp(500, text='no more')

        eddie_image.requests.get = fake_get
        eddie_image._POLL_RETRY_AFTER = 0      # no real waiting in tests

    def test_a_good_image_comes_straight_back(self):
        self._serve(_Resp(200, JPEG))
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(err)
        self.assertEqual(raw, JPEG)
        self.assertEqual(len(self.calls), 1)

    def test_png_is_accepted_too(self):
        self._serve(_Resp(200, PNG))
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(err)
        self.assertEqual(raw, PNG)

    def test_the_app_identifies_itself(self):
        # Pollinations asks callers to say who they are; unidentified traffic
        # gets the tightest rationing, which is what this backend kept hitting.
        self._serve(_Resp(200, JPEG))
        eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIn('referrer=', self.calls[0]['url'])
        self.assertIn('Referer', self.calls[0]['headers'])

    def test_the_prompt_is_encoded_not_trusted(self):
        self._serve(_Resp(200, JPEG))
        eddie_image._pollinations_generate('a banana?&x=1 #2', '512x512')
        url = self.calls[0]['url']
        prompt_part = url.split('/prompt/')[1].split('?')[0]
        for raw_char in ('?', '&', '#', ' '):
            self.assertNotIn(raw_char, prompt_part)

    def test_a_throttle_is_retried_once_and_then_succeeds(self):
        self._serve(_Resp(429, text='rate limited'), _Resp(200, JPEG))
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(err)
        self.assertEqual(raw, JPEG)
        self.assertEqual(len(self.calls), 2)

    def test_a_server_error_is_retried_once_and_then_succeeds(self):
        self._serve(_Resp(503, text='upstream'), _Resp(200, JPEG))
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(err)
        self.assertEqual(len(self.calls), 2)

    def test_a_persistent_throttle_says_busy_not_broken(self):
        # "Could not make that one" reads as "your prompt was rejected".
        # A throttle is neither the user's fault nor permanent, and the
        # message should say which of the two it is.
        self._serve(_Resp(429, text='rate limited'), _Resp(429, text='rate limited'))
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(raw)
        self.assertIn('busy', err.lower())
        self.assertEqual(len(self.calls), 2)

    def test_a_refusal_is_not_retried(self):
        # A 400 will be a 400 again; trying twice just doubles the wait.
        self._serve(_Resp(400, text='bad prompt'), _Resp(200, JPEG))
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(raw)
        self.assertEqual(len(self.calls), 1)

    def test_an_html_error_page_is_not_mistaken_for_an_image(self):
        self._serve(_Resp(200, b'<!doctype html><h1>502</h1>',
                          headers={'content-type': 'text/html'}))
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(raw)
        self.assertIn('not an image', err)

    def test_a_network_failure_is_retried_then_reported(self):
        calls = []

        def boom(url, **kwargs):
            calls.append(url)
            raise OSError('connection reset')

        eddie_image.requests.get = boom
        eddie_image._POLL_RETRY_AFTER = 0
        raw, err = eddie_image._pollinations_generate('a banana', '512x512')
        self.assertIsNone(raw)
        self.assertIn('did not respond', err)
        self.assertEqual(len(calls), 2)

    def test_a_nonsense_size_falls_back_rather_than_raising(self):
        self._serve(_Resp(200, JPEG))
        raw, err = eddie_image._pollinations_generate('a banana', 'not-a-size')
        self.assertIsNone(err)
        self.assertIn('width=1024', self.calls[0]['url'])


class PromptTests(SimpleTestCase):
    """What somebody types is a request; the model needs a described scene."""

    def test_the_asking_part_is_dropped(self):
        cases = {
            'Can you generate an image of a banana': 'a banana',
            'eddie please draw me a picture of a red bicycle at night':
                'a red bicycle at night',
            'generate: a cat wearing sunglasses': 'a cat wearing sunglasses',
            # The article belongs to the subject when no "picture of" follows.
            'draw me a banana': 'a banana',
            'paint a sunset over the ocean': 'a sunset over the ocean',
        }
        for asked, want in cases.items():
            self.assertEqual(eddie_image._strip_framing(asked), want, asked)

    def test_words_that_describe_the_picture_are_kept(self):
        # "drawing" here is what is in the picture, not a request to draw.
        for text in ('a painting of a man drawing a bicycle',
                     'sunset over Cape Town',
                     'generated images are cool'):
            self.assertEqual(eddie_image._strip_framing(text), text)

    def test_stripping_never_empties_the_prompt(self):
        # If the request WAS the subject, keep it rather than sending nothing.
        self.assertTrue(eddie_image._strip_framing('draw me a picture'))
        self.assertTrue(eddie_image._strip_framing('make an image'))

    @override_settings(GROQ_API_KEY='', GEMINI_API_KEY='', ANTHROPIC_API_KEY='')
    def test_with_no_model_the_rewrite_falls_back_rather_than_failing(self):
        self.assertEqual(
            eddie_image._rewrite_prompt('Can you generate an image of a banana'),
            'a banana')

    @override_settings(EDDIE_IMAGE_REWRITE='off')
    def test_the_rewrite_can_be_switched_off(self):
        self.assertEqual(
            eddie_image._rewrite_prompt('Can you generate an image of a banana'),
            'a banana')

    def test_a_model_that_ignores_the_instruction_is_not_used(self):
        # A conversational reply or an empty one is worse than what they typed.
        import core.eddie_providers as providers
        real = providers.once
        self.addCleanup(setattr, providers, 'once', real)
        for reply in ("Sure! Here's a prompt for you:", 'ok', '', 'x' * 2000,
                      'I cannot create that image.',
                      'Here is your prompt:', 'As an AI, I can help with that'):
            providers.once = lambda *a, **k: (reply, [])
            with override_settings(GROQ_API_KEY='k'):
                self.assertEqual(
                    eddie_image._rewrite_prompt('draw me a banana'), 'a banana',
                    reply[:30])


class ShapeTests(SimpleTestCase):
    """A cityscape in a square crops off the city."""

    def test_scenes_are_landscape(self):
        self.assertEqual(
            eddie_image._dimensions('a man looking over a futuristic city at sunset'),
            (1344, 768))

    def test_portraits_and_wallpapers_are_tall(self):
        for text in ('a full-body portrait of a woman',
                     'a phone wallpaper of mountains',
                     'a vertical poster'):
            w, h = eddie_image._dimensions(text)
            self.assertGreater(h, w, text)

    def test_avatars_and_logos_are_square(self):
        for text in ('a profile picture of a lion', 'a logo for a coffee shop',
                     'an app icon', 'a sticker of a frog'):
            self.assertEqual(eddie_image._dimensions(text), (1024, 1024), text)

    def test_openai_only_ever_gets_a_size_it_accepts(self):
        allowed = {'1024x1024', '1024x1536', '1536x1024'}
        for text in ('a city at sunset', 'a portrait of a man', 'an app icon'):
            w, h = eddie_image._dimensions(text)
            self.assertIn(eddie_image._openai_size(w, h), allowed, text)


class SeedAndTokenTests(SimpleTestCase):

    def setUp(self):
        self.urls, self.headers = [], []
        real = eddie_image.requests.get
        self.addCleanup(setattr, eddie_image.requests, 'get', real)

        def fake_get(url, **kwargs):
            self.urls.append(url)
            self.headers.append(kwargs.get('headers') or {})
            return _Resp(200, JPEG)

        eddie_image.requests.get = fake_get

    def test_every_request_gets_its_own_seed(self):
        # Pollinations defaults to seed 42, so without this the same words
        # always came back as the same picture and Try again was a no-op.
        for _ in range(6):
            eddie_image._pollinations_generate('a banana', '1024x1024')
        seeds = {u.split('seed=')[1].split('&')[0] for u in self.urls}
        self.assertGreater(len(seeds), 1)

    @override_settings(POLLINATIONS_TOKEN='')
    def test_without_a_token_no_authorization_is_sent(self):
        eddie_image._pollinations_generate('a banana', '1024x1024')
        self.assertNotIn('Authorization', self.headers[0])

    @override_settings(POLLINATIONS_TOKEN='tok_abc')
    def test_a_token_is_sent_when_there_is_one(self):
        # The anonymous tier forces every request onto a small model and
        # stamps its own watermark on whatever nologo says.
        eddie_image._pollinations_generate('a banana', '1024x1024')
        self.assertEqual(self.headers[0]['Authorization'], 'Bearer tok_abc')


class WatermarkTests(SimpleTestCase):

    def _png(self, colour, size=(400, 300)):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', size, colour).save(buf, 'PNG')
        return buf.getvalue()

    def test_a_backend_that_brands_its_own_output_is_left_alone(self):
        # Painting over pollinations.ai would be taking their attribution off
        # their free service and putting ours on their work.
        raw = self._png((30, 30, 30))
        self.assertIs(eddie_image._watermark(raw, 'pollinations'), raw)

    def test_eddies_own_output_is_signed(self):
        raw = self._png((30, 30, 30))
        for provider in ('cloudflare', 'openai'):
            self.assertNotEqual(eddie_image._watermark(raw, provider), raw, provider)

    def test_the_mark_reads_against_both_light_and_dark(self):
        from PIL import Image
        import io
        for colour in ((240, 238, 230), (12, 12, 16)):
            out = eddie_image._watermark(self._png(colour), 'cloudflare')
            im = Image.open(io.BytesIO(out)).convert('L')
            w, h = im.size
            corner = list(im.crop((w - 160, h - 50, w, h)).getdata())
            # Whatever the background, the text has to differ from it.
            self.assertGreater(max(corner) - min(corner), 60, colour)

    @override_settings(EDDIE_IMAGE_WATERMARK='off')
    def test_it_can_be_switched_off(self):
        raw = self._png((30, 30, 30))
        self.assertIs(eddie_image._watermark(raw, 'cloudflare'), raw)

    def test_bytes_that_are_not_an_image_survive_untouched(self):
        self.assertEqual(eddie_image._watermark(b'not an image', 'cloudflare'),
                         b'not an image')
        self.assertEqual(eddie_image._watermark(b'', 'cloudflare'), b'')


    def test_a_preamble_above_the_real_prompt_keeps_the_prompt(self):
        import core.eddie_providers as providers
        real = providers.once
        self.addCleanup(setattr, providers, 'once', real)
        providers.once = lambda *a, **k: (
            "Here is your prompt:\nA ripe yellow banana on a white studio "
            "backdrop, soft diffused light, shallow depth of field, "
            "photorealistic close-up", [])
        with override_settings(GROQ_API_KEY='k'):
            out = eddie_image._rewrite_prompt('draw me a banana')
        self.assertTrue(out.startswith('A ripe yellow banana'), out)
        self.assertNotIn('Here is your prompt', out)
