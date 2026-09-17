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

    def __init__(self, served, failures=None, stream_fail=None,
                 emit_before_fail=False):
        self.served = served
        self.failures = failures or {}
        # Raised while the stream is being consumed rather than when the call
        # is made -- the case that reached a user.
        self.stream_fail = stream_fail or {}
        self.emit_before_fail = emit_before_fail
        # executed_tools to hand back, so a real search can be simulated.
        self.tool_results = None
        self.sent = []
        self.tried = []
        self.models = type('M', (), {'list': self._list})()
        self.chat = type('C', (), {'completions': self})()

    def _list(self):
        rows = [type('R', (), {'id': i, 'active': True})() for i in self.served]
        return type('L', (), {'data': rows})()

    def create(self, model=None, **kwargs):
        self.tried.append(model)
        self.sent.append(kwargs)
        failure = self.failures.get(model)
        if failure:
            raise failure
        if kwargs.get('stream'):
            return self._stream(model)
        # A searching turn is not streamed, so its failures land here too.
        boom = self.stream_fail.get(model)
        if boom:
            raise boom
        message = type('M', (), {
            'content': 'answer from %s' % model,
            'executed_tools': (self.tool_results or {}).get(model),
        })()
        choice = type('C', (), {'message': message, 'finish_reason': 'stop'})()
        return type('R', (), {'choices': [choice], 'model': model, 'usage': None})()

    def _stream(self, model):
        def chunk(text, tools=None):
            delta = type('D', (), {'content': text, 'type': 'text',
                                   'executed_tools': tools})()
            choice = type('C', (), {'delta': delta, 'message': None})()
            return type('K', (), {'choices': [choice]})()

        if self.tool_results and model in self.tool_results:
            yield chunk(None, self.tool_results[model])

        boom = self.stream_fail.get(model)
        if boom and self.emit_before_fail:
            yield chunk('partial ')
        if boom:
            raise boom
        yield chunk('answer from %s' % model)


SERVED = ['llama-3.1-8b-instant', 'groq/compound', 'groq/compound-mini',
          'llama-3.3-70b-versatile', 'whisper-large-v3']


class GroqSearchModelTests(SimpleTestCase):

    def setUp(self):
        self._reset()
        self.addCleanup(self._reset)

    def _reset(self):
        eddie_providers._GROQ_LIVE.update({'at': 0.0, 'names': [], 'search': []})
        eddie_providers._GROQ_WORKING = None
        # A 413 in one test pauses search process-wide; do not leak that.
        eddie_providers._GROQ_SEARCH_OFF_UNTIL = 0.0
        eddie_providers._GROQ_LAST_SEARCH_ERROR = None

    def test_compound_models_are_kept_out_of_ordinary_chat(self):
        # They run a web search before answering, which is right for a claim
        # and wrong for "hi".
        names = eddie_providers._groq_live_models(_FakeGroq(SERVED))
        self.assertFalse([n for n in names if 'compound' in n], names)
        self.assertEqual(eddie_providers._GROQ_LIVE['search'],
                         ['groq/compound', 'groq/compound-mini'])

    def test_chat_stays_off_the_model_compound_runs_on(self):
        # Groq's token budget is per model and compound has no budget of its
        # own: it spends openai/gpt-oss-120b's, which is 8,000 a minute free.
        # That model was also first for ordinary chat, so every plain answer --
        # including every fallback from a failed search -- spent what the next
        # search needed. Search fails, fall back, next search fails.
        names = eddie_providers._groq_live_models(_FakeGroq([
            'openai/gpt-oss-120b', 'allam-2-7b', 'openai/gpt-oss-20b',
            'groq/compound']))
        self.assertEqual(names[-1], 'openai/gpt-oss-120b',
                         'chat would still be starving the search: %r' % (names,))
        self.assertGreater(len(names), 1, 'nothing left to chat on')

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
        # A 413 in one test pauses search process-wide; do not leak that.
        eddie_providers._GROQ_SEARCH_OFF_UNTIL = 0.0
        eddie_providers._GROQ_LAST_SEARCH_ERROR = None

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
        eddie_providers._groq_call(client, prefer='groq/compound', messages=[])
        self.assertNotIn('compound', client.tried[-1])
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
        # A 413 in one test pauses search process-wide; do not leak that.
        eddie_providers._GROQ_SEARCH_OFF_UNTIL = 0.0
        eddie_providers._GROQ_LAST_SEARCH_ERROR = None
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


class SearchFallbackTests(SimpleTestCase):
    """A searching model is an upgrade on the turn, never a dependency of it."""

    def setUp(self):
        eddie_providers._GROQ_LIVE.update({'at': 0.0, 'names': [], 'search': []})
        eddie_providers._GROQ_WORKING = None
        # A 413 in one test pauses search process-wide; do not leak that.
        eddie_providers._GROQ_SEARCH_OFF_UNTIL = 0.0
        eddie_providers._GROQ_LAST_SEARCH_ERROR = None
        self._real = eddie_providers._groq_client
        self.addCleanup(setattr, eddie_providers, '_groq_client', self._real)
        import logging
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

    def _client(self, **kw):
        c = _FakeGroq(SERVED, **kw)
        eddie_providers._groq_client = lambda: c
        return c

    def _run(self, client):
        queue, events = [], []

        def emit(kind, data):
            events.append((kind, data))
            queue.append('frame')

        list(eddie_providers._groq_stream(
            {'history': [], 'prompt': 'when is the iPhone out',
             'wants_search': True}, 'SYSTEM', queue, emit, 2000))
        return events

    def test_a_413_while_streaming_still_answers(self):
        # This is the one that reached a user: the search model failed partway
        # through, the exception came out of the iteration rather than the
        # call, and the turn died showing "Request Entity Too Large".
        client = self._client(stream_fail={
            'groq/compound': RuntimeError('Request Entity Too Large'),
            'groq/compound-mini': RuntimeError('Request Entity Too Large')})
        events = self._run(client)
        kinds = [k for k, _ in events]
        self.assertIn('text', kinds, 'the turn produced no answer at all')
        self.assertIn('groq/compound', client.tried)
        self.assertGreater(len(client.tried), 1, 'never fell back')

    def test_the_fallback_is_told_it_can_no_longer_search(self):
        # Otherwise "YOU CAN SEARCH THE WEB" is still above it and it writes
        # as though it did.
        client = self._client(stream_fail={
            'groq/compound': RuntimeError('413'),
            'groq/compound-mini': RuntimeError('413')})
        self._run(client)
        second = client.sent[-1]
        system = second['messages'][0]['content']
        self.assertIn('CORRECTION', system)
        self.assertIn('could not look it up', system)

    def test_a_searching_turn_sends_less_history(self):
        client = self._client()
        queue = []
        history = [{'role': 'user', 'text': 'x' * 2000} for _ in range(20)]
        list(eddie_providers._groq_stream(
            {'history': history, 'prompt': 'q', 'wants_search': True},
            'SYSTEM', queue, lambda k, d: queue.append('f'), 2000))
        sent = client.sent[0]['messages']
        self.assertLessEqual(len(sent), 1 + eddie_providers._GROQ_SEARCH_HISTORY + 1)
        for m in sent[1:]:
            self.assertLessEqual(
                len(m['content']),
                eddie_providers._GROQ_SEARCH_TURN_CHARS + 10)

    def test_a_failure_on_the_last_attempt_surfaces(self):
        # The searching attempt is not streamed, so half an answer followed by
        # a failure can only happen on the plain one -- which is the last, and
        # has nothing left to fall back to.
        client = self._client(
            stream_fail={'groq/compound': RuntimeError('413'),
                         'groq/compound-mini': RuntimeError('413'),
                         'llama-3.3-70b-versatile': RuntimeError('boom'),
                         'llama-3.1-8b-instant': RuntimeError('boom'),
                         'openai/gpt-oss-120b': RuntimeError('boom')},
            emit_before_fail=True)
        with self.assertRaises(Exception):
            self._run(client)

    def test_a_search_turn_sends_the_short_prompt_not_the_whole_rulebook(self):
        # Groq charges the declared tokens against a per-minute budget that
        # the search shares with the pages it reads. Eddie's full prompt is
        # ~2,400 tokens of app features and coaching rules that cannot help
        # answer a question about the world, and sending it is most of what
        # came back "Request Entity Too Large".
        client = self._client()
        queue = []
        list(eddie_providers._groq_stream(
            {'history': [], 'prompt': 'q', 'wants_search': True,
             'search_system': eddie_search.SEARCH_SYSTEM},
            'X' * 9000, queue, lambda k, d: queue.append('f'), 2000))
        sent = client.sent[0]
        system = sent['messages'][0]['content']
        self.assertEqual(system, eddie_search.SEARCH_SYSTEM)
        self.assertLess(len(system), 2500)
        self.assertLessEqual(sent['max_completion_tokens'],
                             eddie_providers._GROQ_SEARCH_MAX_TOKENS)

    def test_a_plain_turn_still_gets_the_full_prompt(self):
        client = self._client()
        queue = []
        list(eddie_providers._groq_stream(
            {'history': [], 'prompt': 'hi'}, 'FULL PROMPT',
            queue, lambda k, d: queue.append('f'), 2000))
        self.assertEqual(client.sent[0]['messages'][0]['content'], 'FULL PROMPT')

    def test_searching_is_only_claimed_once_a_search_has_happened(self):
        # It used to be announced on the strength of having *picked* a
        # searching model. The model then answered with executed_tools: 0,
        # having searched nothing, under a status line saying it had.
        client = self._client()
        kinds = [k for k, _ in self._run(client)]
        self.assertIn('working', kinds)
        self.assertNotIn('searching', kinds)

    def test_searching_is_claimed_as_soon_as_a_search_has(self):
        client = self._client()
        client.tool_results = {'groq/compound': [
            {'type': 'search', 'output': {'results': [
                {'url': 'https://reuters.com/x', 'title': 'Reuters'}]}}]}
        kinds = [k for k, _ in self._run(client)]
        self.assertIn('searching', kinds)
        # And it arrives before the answer, so it is a status and not a report.
        self.assertLess(kinds.index('searching'), kinds.index('text'))

    def test_a_searching_turn_makes_at_most_one_call_per_search_model(self):
        # Each compound call is six to ten seconds. A retry loop on top of two
        # models was four of them in one web request, and gunicorn gives up at
        # thirty seconds -- which is a 500, not a slow answer.
        client = self._client(stream_fail={
            'groq/compound': RuntimeError('413'),
            'groq/compound-mini': RuntimeError('413')})
        self._run(client)
        searches = [m for m in client.tried if 'compound' in m]
        self.assertEqual(sorted(searches),
                         ['groq/compound', 'groq/compound-mini'])

    def test_a_413_pauses_search_instead_of_asking_again(self):
        # Groq says "Request Entity Too Large" both when a request really is
        # oversized and when it simply does not fit in what is left of the
        # per-minute budget. In the second case asking again spends time and
        # keeps the budget empty.
        client = self._client(stream_fail={
            'groq/compound': RuntimeError('Error code: 413 - request_too_large'),
            'groq/compound-mini': RuntimeError('Error code: 413 - request_too_large')})
        self._run(client)
        self.assertTrue(eddie_providers._groq_search_paused())

        # The turn after it does not touch a search model at all.
        nxt = self._client()
        self._run(nxt)
        self.assertEqual([m for m in nxt.tried if 'compound' in m], [])
        self.assertIn('paused', eddie_providers._GROQ_LAST_SEARCH_ERROR)

    def test_rate_limit_headers_are_kept_with_the_failure(self):
        # They are the only thing that says whether to cut the request or wait.
        class Boom(RuntimeError):
            response = type('R', (), {'headers': {
                'x-ratelimit-remaining-tokens': '0',
                'x-ratelimit-reset-tokens': '42s'}})()

        client = self._client(stream_fail={
            'groq/compound': Boom('413 request_too_large'),
            'groq/compound-mini': Boom('413 request_too_large')})
        self._run(client)
        recorded = eddie_providers._GROQ_LAST_SEARCH_ERROR
        self.assertIn('x-ratelimit-remaining-tokens', recorded)
        self.assertIn('42s', recorded)

    def test_mini_gets_a_go_before_search_is_abandoned(self):
        # compound coming back empty is not a reason to stop searching when
        # compound-mini is sitting right there on the same key.
        client = self._client(stream_fail={'groq/compound': RuntimeError('413')})
        self._run(client)
        self.assertIn('groq/compound-mini', client.tried)
        self.assertLess(client.tried.index('groq/compound-mini'),
                        len(client.tried),
                        'mini never got a go')
        self.assertNotIn('openai/gpt-oss-120b', client.tried,
                         'fell through to a plain model while mini could answer')

    def test_compound_is_told_to_actually_use_its_tools(self):
        # Left to itself it answered a question about today's news with
        # executed_tools: 0, no sources, and an invented headline. The tools
        # have to be named explicitly.
        client = self._client()
        queue = []
        list(eddie_providers._groq_stream(
            {'history': [], 'prompt': 'q', 'wants_search': True},
            'SYSTEM', queue, lambda k, d: queue.append('f'), 2000))
        sent = client.sent[0]
        tools = sent['extra_body']['compound_custom']['tools']['enabled_tools']
        self.assertEqual(tools, ['web_search'])
        # visit_website drags the whole page into the request, which is what
        # came back 413 request_too_large on both compound models.
        self.assertNotIn('visit_website', tools)
        self.assertEqual(sent['extra_headers']['Groq-Model-Version'], 'latest')

    def test_a_plain_model_is_not_sent_compound_settings(self):
        # compound_custom on a model that has no such tools is a bad request.
        client = self._client()
        queue = []
        list(eddie_providers._groq_stream(
            {'history': [], 'prompt': 'hi'}, 'SYSTEM',
            queue, lambda k, d: queue.append('f'), 2000))
        self.assertNotIn('extra_body', client.sent[0])
        self.assertNotIn('extra_headers', client.sent[0])

    def test_the_fallback_after_a_search_failure_is_also_clean(self):
        client = self._client(stream_fail={
            'groq/compound': RuntimeError('413'),
            'groq/compound-mini': RuntimeError('413')})
        self._run(client)
        self.assertIn('extra_body', client.sent[0])       # the compound attempt
        self.assertNotIn('extra_body', client.sent[-1])   # the plain fallback

    def test_groq_wording_for_413_is_recognised(self):
        for text in ('Request Entity Too Large', 'Error code: 413',
                     'payload too large', 'request too large'):
            self.assertTrue(
                eddie_providers._groq_is_too_large(Exception(text)), text)
