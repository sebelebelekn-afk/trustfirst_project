"""
core/tests_seo.py

What a shared link says about itself, and what it keeps to itself.

Supabase is stubbed at the one function that talks to it, so these test the
policy and the HTML and nothing about the network. The two properties that
matter most are checked directly: a broken lookup still serves the page, and
nothing private is ever described.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import seo

POST_ID = 'f8610cce-a5b9-4aea-93e4-c95c285b89c7'
CLIP_ID = 'feccc6ae-32b4-4f0a-a38d-1a3330370896'
USER_ID = '7a805c88-3781-492a-8ec1-51559bbea4eb'

USER = {
    'id': USER_ID, 'username': 'kgothi', 'display_name': 'Kgothatso Mashiane',
    'full_name': 'Kgothatso Mashiane', 'bio': 'Building TrustFirst.',
    'avatar_url': 'https://cdn.example/avatar.jpg', 'verified': True,
    'id_verified': False, 'is_banned': False, 'is_locked': False,
    'privacy_settings': {'private_account': False},
}
POST = {
    'id': POST_ID, 'user_id': USER_ID, 'text_content': 'Say hello to the new logo',
    'media_url': 'https://cdn.example/logo.jpg', 'media_urls': ['https://cdn.example/logo.jpg'],
    'media_type': 'image', 'thumbnail_url': None, 'video_url': None, 'is_hidden': False,
    'status': 'published', 'group_id': None, 'approved': None, 'visibility': None,
    'created_at': '2026-09-14T07:00:00+00:00', 'like_count': 3, 'comment_count': 1,
}
CLIP = {
    'id': CLIP_ID, 'user_id': USER_ID, 'caption': '#GTA #rockstar',
    'video_url': 'https://cdn.example/c.mp4', 'thumbnail_url': 'https://cdn.example/c.jpg',
    'audience': 'everyone', 'is_hidden': False, 'created_at': '2026-09-01T00:00:00+00:00',
    'view_count': 12, 'like_count': 2,
}


def _stub(rows):
    """A _select that answers from a dict of table -> row (or list of rows)."""
    def select(table, params):
        v = rows.get(table)
        if v is None:
            return []
        return v if isinstance(v, list) else [v]
    return select


class Base(SimpleTestCase):
    def setUp(self):
        seo._cache.clear()
        seo._sitemap.update({'at': 0.0, 'body': ''})

    def with_rows(self, rows):
        p = mock.patch.object(seo, '_select', side_effect=_stub(rows))
        p.start()
        self.addCleanup(p.stop)


@override_settings(APP_PUBLIC_URL='https://app.gettrustfirst.co.za',
                   SUPABASE_URL='https://x.supabase.co', SUPABASE_SERVICE_KEY='k')
class SharedLinkTests(Base):

    def test_a_post_link_describes_the_post(self):
        self.with_rows({'posts': POST, 'users': USER})
        r = self.client.get('/post/%s/' % POST_ID)
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('<title>Say hello to the new logo · TrustFirst</title>', html)
        self.assertIn('property="og:image" content="https://cdn.example/logo.jpg"', html)
        self.assertIn('property="og:url" content="https://app.gettrustfirst.co.za/post/%s/"' % POST_ID, html)
        self.assertIn('"@type":"SocialMediaPosting"', html)
        self.assertIn('Verified account', html)

    def test_a_post_is_noindex_until_it_opts_in(self):
        # Previewing follows a share; indexing is Google offering the page to
        # anyone. Posts were written into a closed community, so the second
        # needs an explicit choice the app does not yet offer.
        self.with_rows({'posts': POST, 'users': USER})
        html = self.client.get('/post/%s/' % POST_ID).content.decode()
        self.assertIn('<meta name="robots" content="noindex">', html)

        self.with_rows({'posts': dict(POST, visibility='public'), 'users': USER})
        seo._cache.clear()
        html = self.client.get('/post/%s/' % POST_ID).content.decode()
        self.assertNotIn('content="noindex"', html)

    def test_a_clip_link_describes_the_clip(self):
        self.with_rows({'trustclips': CLIP, 'users': USER})
        html = self.client.get('/clip/%s/' % CLIP_ID).content.decode()
        self.assertIn('<title>#GTA #rockstar · TrustFirst</title>', html)
        self.assertIn('property="og:video" content="https://cdn.example/c.mp4"', html)
        self.assertIn('"@type":"VideoObject"', html)
        self.assertNotIn('content="noindex"', html)

    def test_a_profile_link_describes_the_person(self):
        self.with_rows({'users': USER})
        html = self.client.get('/profile/kgothi/').content.decode()
        self.assertIn('<title>Kgothatso Mashiane (@kgothi) · TrustFirst</title>', html)
        self.assertIn('Building TrustFirst. · Verified on TrustFirst.', html)
        self.assertIn('name="twitter:card" content="summary"', html)
        self.assertIn('"@type":"ProfilePage"', html)

    def test_the_root_describes_the_app(self):
        self.with_rows({})
        html = self.client.get('/').content.decode()
        self.assertIn('<title>TrustFirst</title>', html)
        self.assertIn('property="og:image" content="%s"' % seo.DEFAULT_IMAGE, html)
        self.assertNotIn('content="noindex"', html)


@override_settings(APP_PUBLIC_URL='https://app.gettrustfirst.co.za',
                   SUPABASE_URL='https://x.supabase.co/', SUPABASE_SERVICE_KEY='k',
                   R2_PUBLIC_BASE='https://pub-abc.r2.dev/some/prefix')
class EarlyConnectionTests(Base):
    """The page names the hosts its photos and data come from, so a phone can
    open those connections while the script is still loading."""

    def test_the_page_asks_for_both_connections_early(self):
        self.with_rows({})
        html = self.client.get('/').content.decode()
        self.assertIn('<link rel="preconnect" href="https://pub-abc.r2.dev">', html)
        self.assertIn('<link rel="preconnect" href="https://x.supabase.co" crossorigin>', html)

    @override_settings(R2_PUBLIC_BASE='')
    def test_no_media_host_no_hint(self):
        self.with_rows({})
        html = self.client.get('/').content.decode()
        self.assertNotIn('r2.dev', html)


@override_settings(APP_PUBLIC_URL='https://app.gettrustfirst.co.za',
                   SUPABASE_URL='https://x.supabase.co', SUPABASE_SERVICE_KEY='k')
class NothingPrivateLeaksTests(Base):
    """Each of these must describe the app, not the thing, and say noindex."""

    def assert_generic(self, path):
        html = self.client.get(path).content.decode()
        self.assertIn('<title>TrustFirst</title>', html)
        self.assertIn('content="noindex"', html)
        self.assertNotIn('cdn.example', html)
        self.assertNotIn('Kgothatso', html)
        return html

    def test_hidden_post(self):
        self.with_rows({'posts': dict(POST, is_hidden=True), 'users': USER})
        self.assert_generic('/post/%s/' % POST_ID)

    def test_unpublished_post(self):
        self.with_rows({'posts': dict(POST, status='scheduled'), 'users': USER})
        self.assert_generic('/post/%s/' % POST_ID)

    def test_group_post(self):
        self.with_rows({'posts': dict(POST, group_id='g1'), 'users': USER})
        self.assert_generic('/post/%s/' % POST_ID)

    def test_followers_only_post(self):
        self.with_rows({'posts': dict(POST, visibility='followers'), 'users': USER})
        self.assert_generic('/post/%s/' % POST_ID)

    def test_post_by_private_account(self):
        priv = dict(USER, privacy_settings={'private_account': True})
        self.with_rows({'posts': POST, 'users': priv})
        self.assert_generic('/post/%s/' % POST_ID)

    def test_post_by_banned_account(self):
        self.with_rows({'posts': POST, 'users': dict(USER, is_banned=True)})
        self.assert_generic('/post/%s/' % POST_ID)

    def test_private_profile(self):
        self.with_rows({'users': dict(USER, privacy_settings={'private_account': True})})
        self.assert_generic('/profile/kgothi/')

    def test_hidden_clip_and_followers_clip(self):
        self.with_rows({'trustclips': dict(CLIP, is_hidden=True), 'users': USER})
        self.assert_generic('/clip/%s/' % CLIP_ID)
        seo._cache.clear()
        self.with_rows({'trustclips': dict(CLIP, audience='followers'), 'users': USER})
        self.assert_generic('/clip/%s/' % CLIP_ID)

    def test_missing_row(self):
        self.with_rows({})
        self.assert_generic('/post/%s/' % POST_ID)
        self.assert_generic('/profile/nobody/')

    def test_a_non_uuid_never_reaches_the_database(self):
        with mock.patch.object(seo, '_select') as sel:
            self.assert_generic('/post/not-a-uuid/')
            self.assert_generic("/clip/1 or 1=1/")
            sel.assert_not_called()


@override_settings(APP_PUBLIC_URL='https://app.gettrustfirst.co.za',
                   SUPABASE_URL='https://x.supabase.co', SUPABASE_SERVICE_KEY='k')
class NeverBreaksThePageTests(Base):

    def test_supabase_raising_still_serves_the_shell(self):
        with mock.patch.object(seo, '_select', side_effect=RuntimeError('down')):
            r = self.client.get('/post/%s/' % POST_ID)
        self.assertEqual(r.status_code, 200)
        self.assertIn('<title>TrustFirst</title>', r.content.decode())

    def test_a_loader_raising_still_serves_the_shell(self):
        with mock.patch.object(seo, '_post', side_effect=ValueError('bad row')):
            r = self.client.get('/post/%s/' % POST_ID)
        self.assertEqual(r.status_code, 200)

    @override_settings(SUPABASE_URL='', SUPABASE_SERVICE_KEY='')
    def test_no_credentials_is_not_an_error(self):
        r = self.client.get('/profile/kgothi/')
        self.assertEqual(r.status_code, 200)

    def test_the_lookup_is_cached(self):
        with mock.patch.object(seo, '_select', side_effect=_stub({'posts': POST, 'users': USER})) as sel:
            self.client.get('/post/%s/' % POST_ID)
            self.client.get('/post/%s/' % POST_ID)
        # One post read and one author read, not two of each.
        self.assertEqual(sel.call_count, 2)


@override_settings(APP_PUBLIC_URL='https://app.gettrustfirst.co.za',
                   SUPABASE_URL='https://x.supabase.co', SUPABASE_SERVICE_KEY='k')
class EscapingTests(Base):

    def test_html_in_a_post_cannot_break_out_of_the_tags(self):
        evil = '</title><script>alert(1)</script>"><img src=x onerror=alert(1)>'
        self.with_rows({'posts': dict(POST, text_content=evil), 'users': USER})
        html = self.client.get('/post/%s/' % POST_ID).content.decode()
        head = html.split('</head>')[0]
        # Every '<' the post supplied comes out as an entity: there is exactly
        # one real <title> and no <img> or <script> that the post wrote.
        self.assertNotIn('<script>alert', head)
        self.assertNotIn('<img src=x', head)
        self.assertEqual(head.count('<title>'), 1)
        self.assertEqual(head.count('</title>'), 1)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', head)
        # And the JSON-LD cannot close its own script tag early.
        ld_start = html.index('application/ld+json')
        ld = html[ld_start:html.index('</script>', ld_start)]
        self.assertNotIn('</', ld)

    def test_a_data_uri_avatar_is_not_offered_as_the_picture(self):
        # Eddie's avatar. A browser draws it; a link unfurler cannot fetch it.
        self.with_rows({'users': dict(USER, avatar_url='data:image/svg+xml;base64,AAAA')})
        html = self.client.get('/profile/kgothi/').content.decode()
        self.assertIn('property="og:image" content="%s"' % seo.DEFAULT_IMAGE, html)
        self.assertNotIn('data:image', html.split('</head>')[0].split('og:image')[1][:200])

    def test_long_text_is_cut_at_a_word(self):
        long = ' '.join(['word%d' % i for i in range(80)])
        self.with_rows({'posts': dict(POST, text_content=long), 'users': USER})
        html = self.client.get('/post/%s/' % POST_ID).content.decode()
        # 70 characters lands inside "word11"; the cut steps back to the
        # previous whole word and marks it.
        self.assertIn('<title>word0 word1 word2 word3 word4 word5 word6 word7 word8 word9 word10… · TrustFirst</title>', html)
        self.assertNotIn('word79', html.split('</head>')[0].split('ld+json')[0])


@override_settings(APP_PUBLIC_URL='https://app.gettrustfirst.co.za',
                   SUPABASE_URL='https://x.supabase.co', SUPABASE_SERVICE_KEY='k')
class CrawlerFilesTests(Base):

    def test_robots_points_at_the_sitemap_and_fences_the_api(self):
        r = self.client.get('/robots.txt')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('Disallow: /api/', body)
        self.assertIn('Sitemap: https://app.gettrustfirst.co.za/sitemap.xml', body)

    def test_sitemap_lists_only_what_a_stranger_may_see(self):
        priv = dict(USER, username='hidden', privacy_settings={'private_account': True})
        self.with_rows({
            'users': [USER, priv],
            'trustclips': [CLIP],
            'posts': [dict(POST, visibility='public')],
        })
        r = self.client.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('<loc>https://app.gettrustfirst.co.za/profile/kgothi/</loc>', body)
        self.assertNotIn('/profile/hidden/', body)
        self.assertIn('/clip/%s/' % CLIP_ID, body)
        self.assertIn('/post/%s/' % POST_ID, body)
        self.assertIn('xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"', body)

    def test_sitemap_survives_supabase_being_down(self):
        with mock.patch.object(seo, '_select', side_effect=RuntimeError('down')):
            r = self.client.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        self.assertIn('<urlset', r.content.decode())
