"""
core/tests_eddie_factcheck.py

Tests for Eddie's fact-checking, which is mostly a question of what Eddie is
told about its own abilities on a given turn.

The bug these exist to prevent is specific. Eddie's system prompt told it to
"search the web" on a deploy where search was off, and a model told it has
sources does not hedge -- it writes as though it looked something up. So the
assertions here are less about retrieval than about honesty: ordinary chat is
left alone entirely, a claim gets either real evidence or an explicit "you
could not check this", and no path ever leaves Eddie thinking it searched when
it did not.

Network calls are stubbed. Wikipedia's own behaviour is not what is under test
here, and a suite that fails because someone else's API is throttling is a
suite people learn to ignore.
"""

import time

from django.test import SimpleTestCase, override_settings

from . import eddie_providers, eddie_search, eddie_views


PAGES = {'query': {'pages': [
    {'index': 1,
     'title': 'Ten-percent-of-the-brain myth',
     'fullurl': 'https://en.wikipedia.org/wiki/Ten-percent-of-the-brain_myth',
     'extract': 'The ten-percent-of-the-brain myth states that humans '
                'generally use only one-tenth of their brains.'},
    {'index': 2,
     'title': 'Human brain',
     'fullurl': 'https://en.wikipedia.org/wiki/Human_brain',
     'extract': 'The human brain is the central organ of the nervous system.'},
]}}

CLAIM = 'is it true you only use 10% of your brain?'


class _Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


class _SearchTestCase(SimpleTestCase):
    """Base: stubs the network and resets the module's process-wide state."""

    def setUp(self):
        self.calls = []
        self._real_get = eddie_search.requests.get
        eddie_search.requests.get = self._fake_get
        self.addCleanup(setattr, eddie_search.requests, 'get', self._real_get)
        self._reset()
        self.addCleanup(self._reset)

    def _reset(self):
        eddie_search._CACHE.clear()
        eddie_search._BLOCKED_UNTIL = 0.0
        eddie_search._BLOCK_NEXT = eddie_search._BLOCK_FOR

    def _fake_get(self, url, **kwargs):
        query = (kwargs.get('params') or {}).get('gsrsearch', '')
        self.calls.append(query)
        if 'throttle' in query:
            return _Response(429)
        if 'blorptangle' in query:
            return _Response(200, {'query': {}})
        return _Response(200, PAGES)


class IntentTests(SimpleTestCase):
    """Which messages count as asking Eddie to check something."""

    def test_asking_for_a_check_is_recognised(self):
        for text in ('@eddie is this true?',
                     'Eddie fact check this please',
                     'is that real or fake',
                     'did he really say that',
                     'any proof of this?',
                     'is this legit?',
                     'eddie can you verify this',
                     'is there any truth to this',
                     'debunk this',
                     'Is this accurate?',
                     'source?'):
            self.assertTrue(eddie_search.looks_like_check(text), text)

    def test_ordinary_questions_are_not_checks(self):
        # These matter more than the ones above. A false positive puts a
        # lookup and a pile of Wikipedia text in front of a question that
        # never needed one, and makes Eddie answer "how do I post a clip"
        # like a fact-checker.
        for text in ('what year did the berlin wall fall',
                     'hey eddie how do I post a clip',
                     "what's your favourite colour",
                     'make me an image of a cat',
                     'true story, I laughed',
                     'how do I verify my account',
                     ''):
            self.assertFalse(eddie_search.looks_like_check(text), text)


class SearchByDefaultTests(SimpleTestCase):
    """With a working search, answering from memory is the exception."""

    def test_questions_about_the_world_search(self):
        for text in ('who is the president of South Africa',
                     'what did Trump say about AI',
                     'how much is bitcoin worth',
                     'what happened in the election',
                     'tell me about Anthropic',
                     'Go online'):
            self.assertTrue(eddie_search.should_search(text), text)

    def test_things_the_web_cannot_help_with_do_not(self):
        for text in ('hey eddie how do I post a clip',
                     'how do I verify my account',
                     'my account is locked',
                     "what's your favourite colour",
                     'what do you think of my post',
                     'draw me a cat',
                     'write me a poem',
                     'hi',
                     'tell me a joke'):
            self.assertFalse(eddie_search.should_search(text), text)

    def test_an_explicit_ask_beats_the_exceptions(self):
        # "is this true" about a TrustFirst claim is still a claim to check.
        self.assertTrue(
            eddie_search.should_search('is it true that TrustFirst was hacked?'))

    def test_nothing_to_search_is_not_searched(self):
        self.assertFalse(eddie_search.should_search(''))
        self.assertFalse(eddie_search.should_search('   '))


class LookupIntentTests(SimpleTestCase):
    """Asking Eddie to find something out, as opposed to check a claim."""

    def test_requests_to_go_and_look(self):
        for text in ('Go online', 'No search for recent news',
                     'search the web for me', 'look it up', 'google it',
                     'browse the web', 'what is the latest news on AI',
                     "what's the latest on load shedding",
                     'any news about the election'):
            self.assertTrue(eddie_search.wants_lookup(text), text)

    def test_asking_what_a_person_said(self):
        # The shape that goes most badly wrong: asked what a named person
        # said, a model will produce a fluent quotation with a date on it
        # whether or not it has anything real to draw on.
        for text in ('what did Trump say about AI',
                     'who said AI could wipe out the human race',
                     'did Musk say that',
                     'what did she announce yesterday'):
            self.assertTrue(eddie_search.wants_lookup(text), text)

    def test_ordinary_chat_is_still_left_alone(self):
        for text in ('hey eddie how do I post a clip',
                     "what's your favourite colour",
                     'draw me a cat',
                     'how do I verify my account',
                     'what is the capital of France',
                     'tell me a joke',
                     'say something nice'):
            self.assertFalse(eddie_search.needs_evidence(text), text)


class QueryTests(SimpleTestCase):
    """Turning what somebody typed into something a search index can match."""

    def test_framing_is_stripped_down_to_the_claim(self):
        self.assertEqual(
            eddie_search._query('@eddie is this true? The Great Wall of '
                                'China is visible from space'),
            'Great Wall China visible space')

    def test_links_and_handles_do_not_reach_the_query(self):
        q = eddie_search._query('is this true https://example.com/a/b @someone '
                                'Mandela became president in 1994')
        self.assertNotIn('http', q)
        self.assertIn('Mandela', q)

    def test_a_claim_that_is_all_framing_still_searches_something(self):
        # Stripping stopwords out of "is this real?" leaves nothing. Searching
        # for an empty string would be worse than searching the sentence.
        self.assertTrue(eddie_search._query('is this real?'))

    def test_nothing_to_search_yields_nothing(self):
        self.assertEqual(eddie_search._query(''), '')
        self.assertEqual(eddie_search._query('https://example.com'), '')


class EvidenceTests(_SearchTestCase):
    """What comes back from a lookup, and what happens when it doesn't."""

    def test_passages_and_sources_come_back_together(self):
        addition, sources = eddie_search.brief(CLAIM)
        self.assertIn('Ten-percent-of-the-brain myth', addition)
        self.assertIn('EVIDENCE YOU JUST LOOKED UP', addition)
        self.assertEqual([s['title'] for s in sources],
                         ['Ten-percent-of-the-brain myth', 'Human brain'])

    def test_the_model_is_told_not_to_cite_beyond_the_list(self):
        addition, _ = eddie_search.brief(CLAIM)
        self.assertIn('Never cite an article that is not in this list', addition)
        self.assertIn('not a live web search', addition)

    def test_a_repeat_claim_is_served_from_cache(self):
        eddie_search.brief(CLAIM)
        eddie_search.brief(CLAIM)
        self.assertEqual(len(self.calls), 1)

    def test_no_results_is_not_an_error(self):
        self.assertEqual(eddie_search.brief('is this true? blorptangle'),
                         ('', []))

    def test_a_broken_lookup_returns_nothing_rather_than_raising(self):
        def boom(*a, **k):
            raise RuntimeError('network on fire')
        eddie_search.requests.get = boom
        self.assertEqual(eddie_search.find_evidence(CLAIM), [])

    def test_malformed_json_returns_nothing(self):
        eddie_search.requests.get = lambda *a, **k: _Response(200, None)
        self.assertEqual(eddie_search.find_evidence(CLAIM), [])

    @override_settings(EDDIE_FACTCHECK='off')
    def test_the_setting_switches_lookups_off(self):
        self.assertEqual(eddie_search.find_evidence(CLAIM), [])
        self.assertEqual(self.calls, [])


class ThrottleTests(_SearchTestCase):
    """Wikimedia answers 429 rather than slowing down; do not push through it."""

    def test_a_429_pauses_lookups(self):
        eddie_search._wikipedia('throttle me')
        self.assertTrue(eddie_search._blocked())
        self.assertEqual(eddie_search.find_evidence(CLAIM), [])

    def test_the_pause_doubles_while_it_keeps_happening(self):
        eddie_search._wikipedia('throttle me')
        first = eddie_search._BLOCKED_UNTIL - time.time()
        eddie_search._BLOCKED_UNTIL = 0.0
        eddie_search._wikipedia('throttle me again')
        second = eddie_search._BLOCKED_UNTIL - time.time()
        self.assertAlmostEqual(first, 60, delta=5)
        self.assertAlmostEqual(second, 120, delta=5)

    def test_the_pause_is_capped(self):
        for _ in range(20):
            eddie_search._BLOCKED_UNTIL = 0.0
            eddie_search._wikipedia('throttle me')
        self.assertLessEqual(eddie_search._BLOCK_NEXT, eddie_search._BLOCK_MAX)

    def test_one_success_resets_the_pause(self):
        eddie_search._wikipedia('throttle me')
        eddie_search._BLOCKED_UNTIL = 0.0
        eddie_search._wikipedia('a call that works')
        self.assertEqual(eddie_search._BLOCK_NEXT, eddie_search._BLOCK_FOR)


class ContextTests(_SearchTestCase):
    """The branch that decides what Eddie is told about its own abilities."""

    def setUp(self):
        super().setUp()
        self._real_live = eddie_providers.can_search_live
        self.addCleanup(setattr, eddie_providers, 'can_search_live',
                        self._real_live)

    def _live(self, value):
        eddie_providers.can_search_live = lambda: value

    def _run(self, asked, claim=None, live=False):
        self._live(live)
        spec = {'prompt': asked, 'route_text': asked}
        system, sources = eddie_views._factcheck_context(
            'BASE', spec, asked, claim=claim)
        return system, sources, spec

    def test_ordinary_chat_is_left_completely_alone(self):
        for text in ('hey eddie how do I post a clip', 'draw me a cat'):
            system, sources, spec = self._run(text)
            self.assertEqual(system, 'BASE')
            self.assertEqual(sources, [])
            self.assertNotIn('wants_search', spec)
        self.assertEqual(self.calls, [], 'ordinary chat must not do a lookup')

    def test_a_claim_gets_wikipedia_evidence_when_there_is_no_live_search(self):
        system, sources, spec = self._run(CLAIM)
        self.assertIn('EVIDENCE YOU JUST LOOKED UP', system)
        self.assertTrue(sources)
        self.assertNotIn('wants_search', spec)

    def test_a_mention_searches_the_post_not_the_question(self):
        # "is this true?" is not a searchable string; the post above it is.
        self._run('is this true?', claim='You only use 10% of your brain')
        self.assertIn('brain', self.calls[0])
        self.assertNotIn('true', self.calls[0])

    def test_a_live_search_deploy_lets_the_model_do_the_looking(self):
        system, sources, spec = self._run(CLAIM, live=True)
        self.assertIn('YOU CAN SEARCH THE WEB', system)
        self.assertNotIn('EVIDENCE YOU JUST LOOKED UP', system)
        self.assertTrue(spec['wants_search'])
        self.assertEqual(sources, [])
        self.assertEqual(self.calls, [], 'no lookup when the model can search')

    def test_finding_nothing_tells_eddie_to_say_so(self):
        system, sources, _ = self._run('is this true? blorptangle frobnicator')
        self.assertIn('not a fresh check', system)
        self.assertIn('cannot browse the live web', system)
        self.assertIn('Never invent a citation', system)
        self.assertEqual(sources, [])

    def test_finding_nothing_still_says_what_eddie_can_do(self):
        # "I don't have the ability to browse the web" is true and useless.
        # Somebody who asked Eddie to go online wants to know what happens
        # next; a bare no reads as a broken feature rather than a limit.
        system, _, _ = self._run('go online and find blorptangle frobnicator')
        self.assertIn('can check reference material', system)
        self.assertIn('not a flat refusal', system)

    def test_being_asked_to_look_something_up_fetches_evidence(self):
        # This is what was missing. "What did so-and-so say about AI" matched
        # nothing, so no lookup ran, and the answer came out of the model's
        # memory as a quotation with a year attached.
        for asked in ('go online and check the news',
                      'what did Musk say about AI',
                      'search the web for the latest on this',
                      "what's the latest on this"):
            self.calls = []
            system, _, _ = self._run(asked)
            self.assertNotEqual(system, 'BASE', asked)
            self.assertTrue(self.calls, 'no lookup ran for: ' + asked)

    def test_a_failure_anywhere_costs_the_citations_not_the_answer(self):
        def boom():
            raise RuntimeError('provider is down')
        eddie_providers.can_search_live = boom
        spec = {'prompt': CLAIM}
        system, sources = eddie_views._factcheck_context('BASE', spec, CLAIM)
        self.assertEqual(system, 'BASE')
        self.assertEqual(sources, [])


# ---- the Groq side --------------------------------------------------------

class _FakeGroq:
    """Just enough of the OpenAI client for the routing logic."""

    def __init__(self, served, failures=None):
        self.served = served
        self.failures = failures or {}
        self.tried = []
        self.models = type('M', (), {'list': self._list})()
        self.chat = type('C', (), {'completions': self})()

    def _list(self):
        rows = [type('R', (), {'id': i, 'active': True})() for i in self.served]
        return type('L', (), {'data': rows})()

    def create(self, model=None, **kwargs):
        self.tried.append(model)
        failure = self.failures.get(model)
        if failure:
            raise failure
        return 'answer from %s' % model


SERVED = ['llama-3.1-8b-instant', 'groq/compound', 'groq/compound-mini',
          'llama-3.3-70b-versatile', 'whisper-large-v3']


class GroqSearchModelTests(SimpleTestCase):

    def setUp(self):
        self._reset()
        self.addCleanup(self._reset)

    def _reset(self):
        eddie_providers._GROQ_LIVE.update({'at': 0.0, 'names': [], 'search': []})
        eddie_providers._GROQ_WORKING = None

    def test_compound_models_are_kept_out_of_ordinary_chat(self):
        # They run a web search before answering, which is right for a claim
        # and wrong for "hi".
        names = eddie_providers._groq_live_models(_FakeGroq(SERVED))
        self.assertFalse([n for n in names if 'compound' in n], names)
        self.assertEqual(eddie_providers._GROQ_LIVE['search'],
                         ['groq/compound', 'groq/compound-mini'])

    def test_the_best_available_search_model_is_chosen(self):
        self.assertEqual(
            eddie_providers._groq_search_model(_FakeGroq(SERVED)),
            'groq/compound')
        self._reset()
        self.assertEqual(
            eddie_providers._groq_search_model(
                _FakeGroq(['llama-3.1-8b-instant', 'groq/compound-mini'])),
            'groq/compound-mini')

    def test_a_key_without_one_reports_no_live_search(self):
        self._reset()
        self.assertIsNone(
            eddie_providers._groq_search_model(_FakeGroq(['llama-3.1-8b-instant'])))

    @override_settings(GROQ_API_KEY='')
    def test_no_key_at_all_is_not_an_error(self):
        self.assertFalse(eddie_providers.can_search_live())


class GroqCallTests(SimpleTestCase):

    def setUp(self):
        eddie_providers._GROQ_LIVE.update({'at': 0.0, 'names': [], 'search': []})
        eddie_providers._GROQ_WORKING = None

    def test_prefer_puts_the_search_model_first(self):
        client = _FakeGroq(SERVED)
        eddie_providers._groq_call(client, prefer='groq/compound', messages=[])
        self.assertEqual(client.tried[0], 'groq/compound')

    def test_a_search_model_never_becomes_the_sticky_chat_model(self):
        # Otherwise one fact-check routes every later "hi" through a search.
        client = _FakeGroq(SERVED)
        eddie_providers._groq_call(client, prefer='groq/compound', messages=[])
        self.assertIsNone(eddie_providers._GROQ_WORKING)

    def test_a_failing_search_model_hands_the_turn_back(self):
        client = _FakeGroq(SERVED,
                           failures={'groq/compound': RuntimeError('500 upstream')})
        answer = eddie_providers._groq_call(client, prefer='groq/compound',
                                            messages=[])
        self.assertNotIn('compound', answer)
        self.assertGreater(len(client.tried), 1)

    def test_ordinary_chat_still_picks_a_plain_model_and_sticks_to_it(self):
        client = _FakeGroq(SERVED)
        eddie_providers._groq_call(client, messages=[])
        self.assertNotIn('compound', client.tried[0])
        self.assertEqual(eddie_providers._GROQ_WORKING, client.tried[0])


class GroqCitationTests(SimpleTestCase):
    """executed_tools has had more than one shape; read them all, trust none."""

    def _message(self, tools):
        return type('M', (), {'executed_tools': tools})()

    def test_structured_results(self):
        got = eddie_providers._groq_executed_sources(self._message([
            {'type': 'search', 'output': {'results': [
                {'url': 'https://who.int/a', 'title': 'WHO'},
                {'url': 'https://cdc.gov/b', 'title': 'CDC'}]}}]))
        self.assertEqual([g['url'] for g in got],
                         ['https://who.int/a', 'https://cdc.gov/b'])

    def test_links_pulled_out_of_a_text_blob(self):
        got = eddie_providers._groq_executed_sources(self._message([
            {'type': 'search',
             'output': 'Result 1 https://reuters.com/x and https://bbc.co.uk/y.'}]))
        urls = [g['url'] for g in got]
        self.assertIn('https://reuters.com/x', urls)
        self.assertIn('https://bbc.co.uk/y', urls)

    def test_a_shape_nobody_expected_yields_nothing(self):
        for junk in (None, self._message('not a list'), self._message([None])):
            self.assertEqual(eddie_providers._groq_executed_sources(junk), [])


class RoutingTests(SimpleTestCase):

    def setUp(self):
        eddie_providers._GROQ_LIVE.update({'at': 0.0, 'names': [], 'search': []})
        eddie_providers._GROQ_WORKING = None
        self._real = eddie_providers._groq_client
        eddie_providers._groq_client = lambda: _FakeGroq(SERVED)
        self.addCleanup(setattr, eddie_providers, '_groq_client', self._real)

    @override_settings(EDDIE_PROVIDER='', GROQ_API_KEY='k', GEMINI_API_KEY='g')
    def test_a_claim_goes_to_the_engine_that_can_look_it_up(self):
        # Without this, _needs_depth() reads "is it true" as a deep question
        # and sends it to Gemini, whose search is the billed one Eddie cannot
        # reach -- so the one turn that needs search gets the engine without it.
        self.assertEqual(
            eddie_providers._route({'prompt': 'is this true',
                                    'wants_search': True}), 'groq')

    @override_settings(EDDIE_PROVIDER='', GROQ_API_KEY='k', GEMINI_API_KEY='g')
    def test_ordinary_routing_is_unchanged(self):
        self.assertEqual(
            eddie_providers._route({'prompt': 'explain this in detail',
                                    'route_text': 'explain this in detail'}),
            'gemini')
        self.assertEqual(
            eddie_providers._route({'prompt': 'hi', 'route_text': 'hi'}),
            'groq')
