"""
core/tests_account_delete.py

Closing an account: the order of the steps and what each refusal leaves alone.

Nothing here touches a real database, storage bucket or sign-in record; every
outside call is replaced. The SQL function itself is tested separately, on a
copy of the live table structure (see supabase/account_deletion.sql).
"""

import json
import time
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

USER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
URL = '/api/account/delete/'


def _resp(status=200, body=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = body if body is not None else {}
    r.text = json.dumps(body or {})
    return r


class FakeR2:
    """Two files under one prefix, nothing anywhere else."""

    def __init__(self):
        self.listed, self.deleted = [], []

    def list_objects_v2(self, **kw):
        self.listed.append(kw['Prefix'])
        if kw['Prefix'] == 'images/%s/' % USER:
            return {'Contents': [{'Key': 'images/%s/1.jpg' % USER}, {'Key': 'images/%s/2.jpg' % USER}],
                    'IsTruncated': False}
        return {'IsTruncated': False}

    def delete_objects(self, **kw):
        self.deleted.extend(o['Key'] for o in kw['Delete']['Objects'])
        return {}


@override_settings(RATELIMIT_ENABLE=False, SUPABASE_URL='https://example.supabase.co',
                   SUPABASE_SERVICE_KEY='service', CONTACT_EMAIL='help@example.org')
class AccountDelete(SimpleTestCase):

    def setUp(self):
        cache.clear()
        self.r2 = FakeR2()
        patches = [
            mock.patch('core.api_views._verify_supabase_jwt',
                       return_value={'sub': USER, 'iat': int(time.time()) - 30}),
            mock.patch('core.api_views._yoco_rpc', return_value=_resp(200, {
                'ok': True, 'files': [{'bucket': 'avatars', 'name': USER + '/a.jpg'},
                                      {'bucket': 'images', 'name': USER + '/p.jpg'},
                                      {'bucket': 'images', 'name': USER + '/q.jpg'}]})),
            mock.patch('core.api_views.httpx.request', return_value=_resp(200, [])),
            mock.patch('core.api_views.httpx.delete', return_value=_resp(200, {})),
            mock.patch('core.api_views._r2_ready', return_value=True),
            mock.patch('core.api_views._r2_client', return_value=self.r2),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.jwt, self.rpc, self.storage, self.auth_delete = self.mocks[:4]

    def _post(self):
        return self.client.post(URL, data='{}', content_type='application/json')

    def test_everything_goes_in_order(self):
        res = self._post()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.content), {'ok': True, 'files_left': 0, 'signin_removed': True})
        self.rpc.assert_called_once_with('tf_delete_account', {'p_user': USER})
        # One storage call per bucket, with exactly that bucket's files.
        calls = {c.args[1].rsplit('/', 1)[1]: c.kwargs['json']['prefixes'] for c in self.storage.call_args_list}
        self.assertEqual(calls, {'avatars': [USER + '/a.jpg'], 'images': [USER + '/p.jpg', USER + '/q.jpg']})
        # Every R2 folder of the account is looked in, and what is there is removed.
        self.assertEqual(sorted(self.r2.listed),
                         sorted('%s/%s/' % (p, USER) for p in ('images', 'videos', 'avatars', 'stories', 'clips')))
        self.assertEqual(self.r2.deleted, ['images/%s/1.jpg' % USER, 'images/%s/2.jpg' % USER])
        # The sign-in record last.
        self.assertTrue(self.auth_delete.call_args.args[0].endswith('/auth/v1/admin/users/' + USER))

    def test_not_signed_in(self):
        self.jwt.side_effect = ValueError('missing')
        res = self._post()
        self.assertEqual(res.status_code, 401)
        self.rpc.assert_not_called()

    def test_an_old_session_must_sign_in_again(self):
        self.jwt.return_value = {'sub': USER, 'iat': int(time.time()) - 3600}
        res = self._post()
        self.assertEqual(res.status_code, 401)
        self.assertTrue(json.loads(res.content)['reauth'])
        self.rpc.assert_not_called()

    def test_payment_records_are_refused_and_nothing_is_removed(self):
        self.rpc.return_value = _resp(200, {'ok': False, 'reason': 'payment_records'})
        res = self._post()
        self.assertEqual(res.status_code, 409)
        self.assertIn('help@example.org', json.loads(res.content)['error'])
        self.storage.assert_not_called()
        self.assertEqual(self.r2.listed, [])
        self.auth_delete.assert_not_called()

    def test_a_database_failure_removes_nothing(self):
        self.rpc.return_value = _resp(500, {'message': 'boom'})
        res = self._post()
        self.assertEqual(res.status_code, 502)
        self.assertIn('Nothing was removed', json.loads(res.content)['error'])
        self.storage.assert_not_called()
        self.auth_delete.assert_not_called()

    def test_a_storage_failure_is_counted_not_hidden(self):
        self.storage.return_value = _resp(500, {'message': 'nope'})
        res = self._post()
        body = json.loads(res.content)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(body['files_left'], 3)
        # The sign-in record is still removed: the profile is already gone.
        self.auth_delete.assert_called_once()
        self.assertTrue(body['signin_removed'])

    def test_an_already_missing_signin_record_counts_as_removed(self):
        self.auth_delete.return_value = _resp(404, {})
        body = json.loads(self._post().content)
        self.assertTrue(body['signin_removed'])
