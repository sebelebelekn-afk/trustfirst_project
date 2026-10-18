"""
core/tests_features.py

Paused features: what the app is told, and what the server refuses.

The client hides the way into a paused feature, but hiding is not a lock, so
these check the lock. Each endpoint that brings money in or opens a stream must
answer 403 while its switch is off, and must reach its own code (which then
fails for its own reasons, here a missing sign-in) once the switch is on. The
ways out, withdrawing a balance and cashing out coins, must never be paused,
because the Terms promise people can leave with what they hold.
"""

import json

from django.test import SimpleTestCase, override_settings

ALL_OFF = {'live': False, 'wallet': False, 'coins': False, 'kids': False}
ALL_ON = {'live': True, 'wallet': True, 'coins': True, 'kids': True}


class ConfigTellsTheClient(SimpleTestCase):

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_config_lists_every_switch(self):
        body = json.loads(self.client.get('/api/config/').content)
        self.assertEqual(body['features'], ALL_OFF)

    @override_settings(TF_FEATURES={'live': True, 'wallet': False, 'coins': False, 'kids': False})
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
    def test_a_live_token_is_refused_while_live_is_paused(self):
        r = self.client.get('/api/live/token/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(json.loads(r.content)['paused'], ['live'])

    @override_settings(TF_FEATURES=ALL_ON)
    def test_switched_on_the_endpoints_reach_their_own_checks(self):
        # Past the switch, each endpoint's own sign-in check is what answers.
        for path in ('/api/wallet/create-checkout/', '/api/wallet/buy-coins/'):
            r = self._post(path)
            self.assertNotEqual(r.status_code, 403, path)
        self.assertNotEqual(self.client.get('/api/live/token/').status_code, 403)


class TheWayOutIsNeverPaused(SimpleTestCase):

    @override_settings(TF_FEATURES=ALL_OFF)
    def test_withdrawing_and_cashing_out_are_not_switched_off(self):
        for path in ('/api/wallet/withdraw/', '/api/wallet/cash-out-coins/'):
            r = self.client.post(path, data='{}', content_type='application/json')
            if r.status_code == 403:
                self.assertNotIn('paused', json.loads(r.content), path)
