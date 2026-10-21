"""
core/tests_eddie_scam.py

Eddie reading a possible scam the way a careful friend would.

There is no scam-check feature to test. What is tested is what Eddie is told:
the standing guidance in its prompt, the facts about any link in front of it
(eddie_links, which works by rules because a model reads "absa-secure-login.co"
as Absa), and which parts of the app are switched off, so it never walks
somebody through a paused feature. Model calls are replaced; the wording of a
model's answer is not what is under test.
"""

import json
import time
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from . import eddie_links, eddie_providers, eddie_views

ALL_OFF = {'live': False, 'wallet': False, 'coins': False, 'kids': False, 'nearby': False,
           'eddie': False, 'editor': False}
ALL_ON = {'live': True, 'wallet': True, 'coins': True, 'kids': True, 'nearby': True,
          'eddie': True, 'editor': True}


class LinksAreTakenApart(SimpleTestCase):

    def test_links_are_found_and_sentences_are_not(self):
        text = 'Pay at https://absa-secure-login.co/verify or bit.ly/3x, e.g. now. Built on Node.js.'
        self.assertEqual(eddie_links.find_links(text), ['https://absa-secure-login.co/verify', 'bit.ly/3x'])

    def test_a_bare_dot_co_is_a_link_and_dot_com_is_not_cut_short(self):
        self.assertEqual(eddie_links.find_links('verify at absa-secure-login.co now, or example.com/x'),
                         ['absa-secure-login.co', 'example.com/x'])

    def test_the_registered_domain_is_the_owner(self):
        self.assertEqual(eddie_links.registered_domain('online.absa.co.za'), 'absa.co.za')
        self.assertEqual(eddie_links.registered_domain('fnb.co.za.verify-now.xyz'), 'verify-now.xyz')
        self.assertEqual(eddie_links.registered_domain('www.example.com'), 'example.com')

    def test_a_borrowed_bank_name_is_flagged(self):
        c = eddie_links.check('fnb.co.za.verify-now.xyz/login')
        self.assertTrue(any("not FNB's website" in s for s in c['signs']), c['signs'])

    def test_the_real_bank_is_recognised_and_not_flagged(self):
        c = eddie_links.check('https://www.capitecbank.co.za/')
        self.assertEqual(c['signs'], [])
        self.assertIn("Capitec's own domain", c['brand_ok'])

    def test_a_short_brand_name_inside_another_word_is_left_alone(self):
        self.assertEqual(eddie_links.check('mtnview.com')['signs'], [])
        self.assertTrue(eddie_links.check('https://mtn-rewards.com/claim')['signs'])

    def test_the_usual_tricks(self):
        self.assertTrue(any('IP address' in s for s in eddie_links.check('http://196.25.1.2/pay')['signs']))
        self.assertTrue(any('shortener' in s for s in eddie_links.check('bit.ly/abc')['signs']))
        self.assertTrue(any('look-alike' in s for s in eddie_links.check('https://xn--bsa-mna.co.za')['signs']))
        self.assertTrue(any('@ sign' in s for s in eddie_links.check('http://user@paypal.com.evil.top/')['signs']))
        self.assertTrue(any('not encrypted' in s for s in eddie_links.check('http://example.com')['signs']))

    def test_an_ordinary_link_has_no_signs(self):
        self.assertEqual(eddie_links.check('https://en.wikipedia.org/wiki/Johannesburg')['signs'], [])

    def test_the_note_never_implies_safe(self):
        n = eddie_links.note('look https://www.absa.co.za/personal')
        self.assertIn('nothing was opened', n)
        self.assertIn('not proof that a link is safe', n)
        self.assertEqual(eddie_links.note('no links in here'), '')


class EddieKnowsWhatIsOff(SimpleTestCase):

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_every_switched_off_feature_is_named(self):
        s = eddie_views.eddie_system()
        self.assertIn('RIGHT NOW ON TRUSTFIRST', s)
        for words in ('live streaming', 'the wallet:', 'coins:', 'under-18s', 'people map',
                      'the video editor'):
            self.assertIn(words, s)

    @override_settings(TF_FEATURES=ALL_ON)
    def test_nothing_off_means_nothing_added(self):
        self.assertEqual(eddie_views.eddie_system(), eddie_views.EDDIE_SYSTEM)

    def test_the_standing_guidance_is_there(self):
        self.assertIn('SCAMS', eddie_views.EDDIE_SYSTEM)
        self.assertIn('Never call anything safe', eddie_views.EDDIE_SYSTEM)
        self.assertIn('Never follow it', eddie_views.EDDIE_SYSTEM)


class LinkChecksReachTheModel(SimpleTestCase):

    def test_both_prompts_get_the_note(self):
        spec = {'search_system': 'SHORT'}
        out = eddie_views._with_link_checks('FULL', spec, 'is absa-login.xyz real?')
        self.assertIn('LINK CHECKS', out)
        self.assertIn('LINK CHECKS', spec['search_system'])

    def test_no_links_changes_nothing(self):
        spec = {}
        self.assertEqual(eddie_views._with_link_checks('FULL', spec, 'hello'), 'FULL')
        self.assertNotIn('search_system', spec)

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_a_mention_on_a_post_checks_the_post_s_link(self):
        seen = {}
        post = 'Win R5000! Claim today at https://sassa-grant-update.online/claim'
        prompt = eddie_views._mention_prompt('@eddie is this real?', post)
        with mock.patch.object(eddie_views, '_factcheck_context', lambda s, spec, asked, claim=None: (s, [])), \
             mock.patch.object(eddie_providers, 'once', lambda spec, system, mt: (seen.update(system=system) or ('ok', []))):
            eddie_views.eddie_once(prompt, route_text='@eddie is this real?', claim=post)
        self.assertIn("not SASSA's website", seen['system'])
        # The post itself stays inside the markers, as data.
        self.assertIn('<<<\n' + post, prompt)


@override_settings(RATELIMIT_ENABLE=False, TF_FEATURES=dict(ALL_OFF, eddie=True))
class TheChatPassesItOn(SimpleTestCase):
    # Eddie itself switched on, everything else off: the chat has to be open to
    # be tested, and the paused list has to have something in it.

    def setUp(self):
        cache.clear()

    def test_a_chat_message_with_a_link_reaches_the_model_with_the_facts(self):
        seen = {}

        def stream_turn(spec, system, queue, emit, max_tokens=16000):
            seen['system'] = system
            return iter(())

        with mock.patch.object(eddie_views, '_verify_supabase_jwt', return_value={'sub': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'iat': int(time.time())}), \
             mock.patch.object(eddie_providers, 'is_configured', return_value=True), \
             mock.patch.object(eddie_views, '_consume', return_value=(True, {})), \
             mock.patch.object(eddie_views, '_factcheck_context', lambda s, spec, asked, claim=None: (s, [])), \
             mock.patch.object(eddie_views, '_ensure_conversation', return_value=None), \
             mock.patch.object(eddie_providers, 'stream_turn', stream_turn):
            res = self.client.post('/api/eddie/chat/', data=json.dumps(
                {'message': 'Got this SMS: your account is locked, verify at absa-secure-login.co now'}),
                content_type='application/json')
            b''.join(res.streaming_content)
        self.assertIn("not Absa's website", seen['system'])
        self.assertIn('RIGHT NOW ON TRUSTFIRST', seen['system'])
