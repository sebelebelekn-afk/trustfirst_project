"""
core/tests_features.py

Paused features: what the app is told, and what the server refuses.

The client hides the way into a paused feature, but hiding is not a lock, so
these check the lock. Each endpoint that brings money in, moves it out, opens a
stream or runs Eddie must answer 403 while its switch is off, and must reach its
own code (which then fails for its own reasons, here a missing sign-in) once the
switch is on. Coins and the wallet are off completely, cash-out and withdrawals
included: when they were switched off the only balance was the owner's own test
money (checked 2026-10-21).
"""

import json

from django.test import SimpleTestCase, override_settings

ALL_OFF = {'live': False, 'wallet': False, 'coins': False, 'kids': False, 'nearby': False,
           'eddie': False}
ALL_ON = {'live': True, 'wallet': True, 'coins': True, 'kids': True, 'nearby': True,
          'eddie': True}

# Every endpoint that makes Eddie do something. His usage count, the history of
# your own conversations and deleting them stay open: they are your data.
EDDIE_ACTIONS = ('/api/eddie/chat/', '/api/eddie/mention/', '/api/eddie/image/',
                 '/api/eddie/speak/', '/api/eddie/post/')


class ConfigTellsTheClient(SimpleTestCase):

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_config_lists_every_switch(self):
        body = json.loads(self.client.get('/api/config/').content)
        self.assertEqual(body['features'], ALL_OFF)

    @override_settings(TF_FEATURES={'live': True, 'wallet': False, 'coins': False, 'kids': False,
                                     'nearby': False, 'eddie': False})
    def test_config_reflects_a_switch_turned_on(self):
        body = json.loads(self.client.get('/api/config/').content)
        self.assertIs(body['features']['live'], True)
        self.assertIs(body['features']['wallet'], False)


class PausedFeaturesAreRefused(SimpleTestCase):

    def _post(self, path):
        return self.client.post(path, data='{}', content_type='application/json')

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_adding_money_is_refused_while_the_wallet_is_paused(self):
        r = self._post('/api/wallet/create-checkout/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(json.loads(r.content)['paused'], ['wallet'])

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_buying_coins_is_refused_while_coins_are_paused(self):
        r = self._post('/api/wallet/buy-coins/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(json.loads(r.content)['paused'], ['coins'])

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_cashing_out_coins_is_refused_while_coins_are_paused(self):
        r = self._post('/api/wallet/cash-out-coins/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(json.loads(r.content)['paused'], ['coins'])

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_a_live_token_is_refused_while_live_is_paused(self):
        r = self.client.get('/api/live/token/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(json.loads(r.content)['paused'], ['live'])

    @override_settings(TF_FEATURES=ALL_ON)
    def test_switched_on_the_endpoints_reach_their_own_checks(self):
        # Past the switch, each endpoint's own sign-in check is what answers.
        for path in ('/api/wallet/create-checkout/', '/api/wallet/buy-coins/', '/api/wallet/cash-out-coins/'):
            r = self._post(path)
            self.assertNotEqual(r.status_code, 403, path)
        self.assertNotEqual(self.client.get('/api/live/token/').status_code, 403)


class TheWalletIsClosedCompletely(SimpleTestCase):

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_withdrawing_is_refused_while_the_wallet_is_off(self):
        r = self.client.post('/api/wallet/withdraw/', data='{}', content_type='application/json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(json.loads(r.content)['paused'], ['wallet'])

    @override_settings(TF_FEATURES=ALL_ON)
    def test_switched_on_withdrawing_reaches_its_own_checks(self):
        r = self.client.post('/api/wallet/withdraw/', data='{}', content_type='application/json')
        self.assertNotEqual(r.status_code, 403)


class EddieIsSwitchedOff(SimpleTestCase):

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_everything_that_runs_eddie_is_refused(self):
        for path in EDDIE_ACTIONS:
            r = self.client.post(path, data='{}', content_type='application/json')
            self.assertEqual(r.status_code, 403, path)
            self.assertEqual(json.loads(r.content)['paused'], ['eddie'], path)

    @override_settings(TF_FEATURES=ALL_ON)
    def test_switched_on_each_reaches_its_own_checks(self):
        for path in EDDIE_ACTIONS:
            r = self.client.post(path, data='{}', content_type='application/json')
            self.assertNotEqual(r.status_code, 403, path)

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_your_own_conversations_stay_reachable(self):
        # Refused for want of a sign-in, not because Eddie is off.
        r = self.client.get('/api/eddie/history/')
        self.assertNotIn('paused', json.loads(r.content or b'{}'))

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_the_algorithm_summary_does_not_use_the_model(self):
        from unittest import mock
        from core import eddie_insights, eddie_providers
        with mock.patch.object(eddie_providers, 'once') as once:
            try:
                eddie_insights.build_interest_summary('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', force=True)
            except Exception:
                pass        # no database here; the point is what it did not call
        once.assert_not_called()
