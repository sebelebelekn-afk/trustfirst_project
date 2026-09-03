// ==========================================================================
// THE LAPTOP LAYOUT
//
// Loaded after feed.js and deliberately additive: nothing in here changes a
// function the mobile app uses. It reads the same nav functions the pill reads
// (navHome, navGoTo) so there is one source of truth for what a tab does, and
// every screen the sidebar reaches is the screen the phone already reaches.
//
// Everything is gated on TF_DESKTOP. On a phone this file defines a few
// functions, does nothing with them, and exits.
// ==========================================================================

var TF_DESKTOP_MIN = 1000;

function tfIsDesktop() {
    return window.matchMedia('(min-width: ' + TF_DESKTOP_MIN + 'px)').matches;
}

// The signed-in user, from wherever it really lives.
//
// feed.js holds it in `let currentUser`, and a top-level let is not a property
// of window, so window.currentUser is permanently undefined. Reading that was
// silently wrong: it fails in exactly the case that matters, when somebody is
// actually signed in. The bare binding is reachable from here because top-level
// lets share one global lexical scope across classic scripts.
function tfMe() {
    try {
        if (typeof currentUser !== 'undefined' && currentUser) return currentUser;
    } catch (e) { /* not declared yet */ }
    return (window && window.currentUser) || null;
}

// ---------------------------------------------------------------- sidebar --

// Which tab is lit. The pill tracks this itself; the sidebar has to be told,
// because the app was never built to have two navigations.
function tfDeskSetActive(key) {
    var items = document.querySelectorAll('#tfSideNav .tf-nav-item');
    for (var i = 0; i < items.length; i++) {
        items[i].classList.toggle('tf-active', items[i].getAttribute('data-tab') === key);
    }
}

// Where each row goes. The four the pill already owns are handed straight to
// it, so the phone and the laptop can never disagree about what a tab does.
// The rest call the same functions the burger menu and settings rows call.
// Every one was checked to exist before it was put here.
var TF_DESK_ROUTES = {
    explore:   'tfDeskExplore',
    live:      'openLiveStreamFeed',
    channels:  'openChannels',
    groups:    'loadGroups',
    saved:     'openSavedLibrary',
    analytics: 'openCreatorAnalytics',
    settings:  'tfDeskOpenSettings',
};

// Opens the real settings screen, then splits it. Wrapping rather than
// patching openSettings keeps the phone's path untouched.
function tfDeskOpenSettings() {
    if (typeof openSettings === 'function') openSettings();
    setTimeout(tfDeskSplitSettings, 60);
    // Whether the account is an admin is decided after the screen is drawn,
    // so the categories are checked again once that has had time to arrive.
    setTimeout(tfDeskSettingsPrune, 900);
    setTimeout(tfDeskSettingsPrune, 2500);
}

// Everything that can cover the column. Most share .white-overlay; the rest
// are listed because they do not, or because they are built at runtime and are
// not in the page until something opens them.
var TF_DESK_LOOSE_OVERLAYS = [
    'reel-overlay', 'live-overlay', 'user-profile-overlay',
    'trustAnalyticsOverlay', 'liveSettingsPage', 'soundHubPage',
    'adminDashOverlay',
    // Built fresh each time it is opened rather than shown and hidden, so it
    // is not a .white-overlay and nothing else was closing it. Live left its
    // page sitting in the column after moving to another tab.
    'liveStreamFeedPage',
    // Explore's own page. It deliberately does not reuse #discovery-page,
    // because the search results element hides and rebuilds itself as you
    // type and would take Explore with it.
    'tfExplorePage',
    'tfMsgEmpty',
];

// Close whatever is open before opening the next thing.
//
// navHome does this for the home button and nothing did it for the rest, which
// is why Live, Channels and Groups stacked on top of each other.
function tfDeskCloseAll() {
    document.querySelectorAll('.white-overlay').forEach(function (el) {
        el.style.display = 'none';
    });
    document.querySelectorAll('.settings-sub-overlay').forEach(function (el) {
        el.style.display = 'none';
    });
    TF_DESK_LOOSE_OVERLAYS.forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
}

function tfDeskGo(key) {
    tfDeskSetActive(key);
    // home goes through navHome, which closes things itself.
    if (key !== 'home') tfDeskCloseAll();
    try {
        if (key === 'home') {
            if (typeof navHome === 'function') navHome();
            return;
        }
        var fn = TF_DESK_ROUTES[key];
        if (fn) {
            if (typeof window[fn] === 'function') {
                window[fn]();
            } else {
                console.warn('[desktop] no handler for', key);
            }
            return;
        }
        if (typeof navGoTo === 'function') navGoTo(key);
    } catch (e) {
        console.warn('[desktop] nav', key, e && e.message);
    }
}

// The badges the pill already maintains, mirrored onto the sidebar. Read from
// the same elements rather than re-querying the database, so the two can never
// disagree about how many unread things there are.
function tfDeskSyncBadges() {
    if (!tfIsDesktop()) return;
    var pairs = [
        ['notif-badge', 'tf-dot-notifications'],
        ['msgs-badge', 'tf-dot-messages'],
        ['msgs-badge', 'tf-dot-dockmsgs'],
    ];
    for (var i = 0; i < pairs.length; i++) {
        var src = document.getElementById(pairs[i][0]);
        var dot = document.getElementById(pairs[i][1]);
        if (!dot) continue;
        var has = !!(src && (src.textContent || '').trim() &&
                     (src.textContent || '').trim() !== '0');
        dot.classList.toggle('on', has);
    }
}

// Who is signed in, at the foot of the sidebar.
function tfDeskFillMe() {
    var u = tfMe();
    if (!tfIsDesktop() || !u) return;
    var img = document.getElementById('tfNavMeAvatar');
    var name = document.getElementById('tfNavMeName');
    var handle = document.getElementById('tfNavMeHandle');
    if (img) {
        img.src = u.avatar_url || (typeof tfAvatarFor === 'function'
            ? tfAvatarFor(u.username || 'you', '007AFF') : '');
    }
    // Your name, not the word "You". A sidebar that calls you "You" while
    // sitting next to your own avatar is a placeholder nobody replaced.
    if (name) name.textContent = u.full_name || u.display_name || u.username || '';
    if (handle) handle.textContent = u.username ? '@' + u.username : '';
}

// Ids that must not appear in a suggestion list: you, and everyone you have
// already followed. Kept in one place so the rail and Explore cannot disagree.
async function tfDeskExcludeIds() {
    var me = tfMe();
    var out = [];
    if (!me || !me.id) return out;
    out.push(me.id);
    try {
        var f = await sb.from('follows')
            .select('following_id')
            .eq('follower_id', me.id)
            .limit(500);
        (f.data || []).forEach(function (r) {
            if (r.following_id) out.push(r.following_id);
        });
    } catch (e) { /* suggesting a few extra people beats suggesting none */ }
    return out;
}

// Ask for more than is shown, because the exclusions are applied after the
// query as well and a page of four could otherwise come back with two.
function tfDeskFilterPeople(rows, exclude, limit) {
    var blocked = {};
    exclude.forEach(function (id) { blocked[id] = true; });
    return (rows || []).filter(function (u) { return u && u.id && !blocked[u.id]; })
                       .slice(0, limit);
}

// ------------------------------------------------------------- right rail --

// Real rows or an honest empty state. Nothing invented: an empty app should
// look empty rather than busy with people who do not exist.
async function tfDeskLoadRail() {
    if (!document.getElementById('tfRightRail')) return;
    if (!window.matchMedia('(min-width: 1300px)').matches) return;
    if (!window.sb) return;

    // --- who to follow ---
    var who = document.getElementById('tfRailPeople');
    if (who) {
        try {
            var exclude = await tfDeskExcludeIds();
            var q = sb.from('users')
                .select('id,username,full_name,avatar_url,verified')
                .neq('is_banned', true)
                .limit(20);
            if (exclude.length) q = q.not('id', 'in', '(' + exclude.join(',') + ')');
            var r = await q;
            // Filtered again here: a suggestion list that shows you your own
            // account is the one result it must never produce, so it does not
            // depend on the query alone.
            var rows = tfDeskFilterPeople(r.data, exclude, 4);
            who.innerHTML = rows.length ? rows.map(function (u) {
                var av = u.avatar_url || (typeof tfAvatarFor === 'function'
                    ? tfAvatarFor(u.username || 'user', '007AFF') : '');
                return '<div class="tf-rail-row" onclick="tfDeskOpenProfile(\'' + u.id + '\')">' +
                    '<img src="' + escapeHtml(av) + '" alt="">' +
                    '<div style="flex:1;min-width:0;">' +
                        '<div class="tf-rail-name">' + escapeHtml(u.full_name || u.username || 'User') + '</div>' +
                        '<div class="tf-rail-sub">@' + escapeHtml(u.username || 'user') + '</div>' +
                    '</div>' +
                '</div>';
            }).join('') : '<div class="tf-rail-empty">Nobody to suggest yet.</div>';
        } catch (e) {
            who.innerHTML = '<div class="tf-rail-empty">Could not load suggestions.</div>';
        }
    }

    // --- trending tags ---
    var tags = document.getElementById('tfRailTags');
    if (tags) {
        try {
            var t = await sb.from('posts')
                .select('text_content')
                .not('text_content', 'is', null)
                .order('created_at', { ascending: false })
                .limit(120);
            var counts = {};
            (t.data || []).forEach(function (p) {
                var found = (p.text_content || '').match(/#[\w]+/g) || [];
                found.forEach(function (h) {
                    var k = h.toLowerCase();
                    counts[k] = (counts[k] || 0) + 1;
                });
            });
            var top = Object.keys(counts)
                .sort(function (a, b) { return counts[b] - counts[a]; })
                .slice(0, 5);
            tags.innerHTML = top.length ? top.map(function (h) {
                return '<div class="tf-rail-row" onclick="tfDeskSearch(\'' + escapeHtml(h) + '\')">' +
                    '<div style="flex:1;min-width:0;">' +
                        '<div class="tf-rail-name">' + escapeHtml(h) + '</div>' +
                        '<div class="tf-rail-sub">' + counts[h] + ' post' + (counts[h] === 1 ? '' : 's') + '</div>' +
                    '</div>' +
                '</div>';
            }).join('') : '<div class="tf-rail-empty">No hashtags yet.</div>';
        } catch (e) {
            tags.innerHTML = '<div class="tf-rail-empty">Could not load trends.</div>';
        }
    }

    // --- who is live ---
    var live = document.getElementById('tfRailLive');
    if (live) {
        try {
            var l = await sb.from('live_sessions')
                .select('id,room,username,avatar_url,title,viewer_count')
                .eq('is_live', true)
                .order('viewer_count', { ascending: false })
                .limit(3);
            var ls = (l.data || []);
            live.innerHTML = ls.length ? ls.map(function (s) {
                var av = s.avatar_url || (typeof tfAvatarFor === 'function'
                    ? tfAvatarFor(s.username || 'user', 'FF3B30') : '');
                return '<div class="tf-rail-row" onclick="tfDeskGo(\'reels\')">' +
                    '<img src="' + escapeHtml(av) + '" alt="">' +
                    '<div style="flex:1;min-width:0;">' +
                        '<div class="tf-rail-name">' + escapeHtml(s.username || 'Someone') + '</div>' +
                        '<div class="tf-rail-sub">' + escapeHtml(s.title || 'Live now') + '</div>' +
                    '</div>' +
                    '<div class="tf-live-dot"></div>' +
                '</div>';
            }).join('') : '<div class="tf-rail-empty">Nobody is live right now.</div>';
        } catch (e) {
            live.innerHTML = '<div class="tf-rail-empty">Could not load.</div>';
        }
    }
}

function tfDeskOpenProfile(id) {
    tfDeskCloseAll();
    // viewUserProfile is the one that exists. It already sends you to your own
    // page when the id is yours, so there is nothing to special-case here.
    if (typeof viewUserProfile === 'function') { viewUserProfile(id); return; }
    console.warn('[desktop] cannot open profile, viewUserProfile missing');
}

// Search goes through handleNavSearch and nothing else.
//
// executeNavSearch, which the pill's Enter key calls, opens a page called
// search-overlay that does not exist and then calls performSearch, which is
// not defined anywhere. Routing the laptop through it would inherit a dead
// path. handleNavSearch is the one that works: it fills #discovery-page with
// real results, and because that page lives inside .app it lands in the middle
// column on a laptop without anything else being moved.
function tfDeskSearch(term) {
    var box = document.getElementById('tfDeskSearchInput');
    if (box) box.value = term;
    tfDeskSearchInput(term);
}

// Typing suggests as you go, which is the same behaviour the phone has.
function tfDeskSearchInput(value) {
    try {
        if (typeof handleNavSearch === 'function') handleNavSearch(value);
    } catch (e) {
        console.warn('[desktop] search', e && e.message);
    }
    // handleNavSearch hides the results page below two characters. If Explore
    // is what is underneath, it should be visible again at that point rather
    // than leaving an empty column.
    var ex = document.getElementById('tfExplorePage');
    if (ex && ex.style.display === 'none' && (!value || value.length < 2)) {
        ex.style.display = 'flex';
    }
}

// Enter just commits what is already on screen. There is no separate results
// page to go to, because the results are already there.
function tfDeskSearchGo() {
    var box = document.getElementById('tfDeskSearchInput');
    tfDeskSearchInput(box ? box.value : '');
    if (box) box.blur();
}

// ------------------------------------------------------------------ explore --

// Explore with nothing typed yet.
//
// #discovery-page hides itself below two characters, so opening it cold would
// show a blank column. It gets a starting state instead: what people are
// tagging and who they could follow, from the same queries the rail uses. The
// moment anything is typed, handleNavSearch takes the page over and this is
// replaced by real results.
async function tfDeskExplore() {
    var app = document.getElementById('app');
    if (!app) return;

    var page = document.getElementById('tfExplorePage');
    if (!page) {
        page = document.createElement('div');
        page.id = 'tfExplorePage';
        app.appendChild(page);
    }
    // Below #discovery-page, which is z-index 3500, so search results cover
    // this rather than fighting it.
    page.style.cssText = 'display:flex;flex-direction:column;position:absolute;' +
        'top:0;left:0;width:100%;height:100%;z-index:3400;' +
        'background:var(--bg-primary,#fff);overflow:hidden;';

    page.innerHTML =
        '<div style="display:flex;align-items:center;gap:10px;padding:18px 16px 12px;flex-shrink:0;">' +
            '<b style="font-size:20px;color:var(--text-primary,#000);flex:1;">Explore</b>' +
        '</div>' +
        '<div class="tf-desk-search" style="display:flex;margin:0 16px 14px;flex:none;">' +
            '<i class="fa-solid fa-magnifying-glass"></i>' +
            '<input id="tfExploreInput" type="text" placeholder="Search TrustFirst"' +
                   ' aria-label="Search TrustFirst" autocomplete="off"' +
                   ' oninput="tfDeskSearchInput(this.value)"' +
                   ' onkeydown="if(event.key===\'Enter\')tfDeskSearchInput(this.value)">' +
        '</div>' +
        '<div id="tfExploreBody" style="flex:1;overflow-y:auto;padding:0 16px 90px;">' +
            '<div class="tf-rail-empty">Loading\u2026</div>' +
        '</div>';

    var input = document.getElementById('tfExploreInput');
    if (input) setTimeout(function () { input.focus(); }, 60);

    var body = document.getElementById('tfExploreBody');
    if (!body || !window.sb) return;

    var html = '';
    try {
        var t = await sb.from('posts')
            .select('text_content')
            .not('text_content', 'is', null)
            .order('created_at', { ascending: false })
            .limit(200);
        var counts = {};
        (t.data || []).forEach(function (post) {
            ((post.text_content || '').match(/#[\w]+/g) || []).forEach(function (h) {
                var k = h.toLowerCase();
                counts[k] = (counts[k] || 0) + 1;
            });
        });
        var top = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; }).slice(0, 10);
        html += '<h3 style="font-size:17px;font-weight:800;margin:6px 0 8px;color:var(--text-primary,#000);">Trending</h3>';
        html += top.length ? top.map(function (h) {
            return '<div class="tf-rail-row" onclick="tfDeskSearch(\'' + escapeHtml(h) + '\')">' +
                '<div style="flex:1;min-width:0;">' +
                    '<div class="tf-rail-name">' + escapeHtml(h) + '</div>' +
                    '<div class="tf-rail-sub">' + counts[h] + ' post' + (counts[h] === 1 ? '' : 's') + '</div>' +
                '</div></div>';
        }).join('') : '<div class="tf-rail-empty">No hashtags yet. Post one and it shows up here.</div>';
    } catch (e) {
        html += '<div class="tf-rail-empty">Could not load trends.</div>';
    }

    try {
        var exclude = await tfDeskExcludeIds();
        var q = sb.from('users')
            .select('id,username,full_name,avatar_url,verified')
            .neq('is_banned', true)
            .limit(30);
        if (exclude.length) q = q.not('id', 'in', '(' + exclude.join(',') + ')');
        var r = await q;
        var people = tfDeskFilterPeople(r.data, exclude, 8);
        html += '<h3 style="font-size:17px;font-weight:800;margin:20px 0 8px;color:var(--text-primary,#000);">People</h3>';
        html += people.length ? people.map(function (u) {
            var av = u.avatar_url || (typeof tfAvatarFor === 'function'
                ? tfAvatarFor(u.username || 'user', '007AFF') : '');
            return '<div class="tf-rail-row" onclick="tfDeskOpenProfile(\'' + u.id + '\')">' +
                '<img src="' + escapeHtml(av) + '" alt="">' +
                '<div style="flex:1;min-width:0;">' +
                    '<div class="tf-rail-name">' + escapeHtml(u.full_name || u.username || 'User') + '</div>' +
                    '<div class="tf-rail-sub">@' + escapeHtml(u.username || 'user') + '</div>' +
                '</div></div>';
        }).join('') : '<div class="tf-rail-empty">Nobody new to suggest.</div>';
    } catch (e) {
        html += '<div class="tf-rail-empty">Could not load people.</div>';
    }

    var stillThere = document.getElementById('tfExploreBody');
    if (stillThere) stillThere.innerHTML = html;
}

// ----------------------------------------------------------------- create --

function tfDeskCreateOpen() {
    var m = document.getElementById('tfCreateModal');
    if (m) m.classList.add('on');
}

function tfDeskCreateClose() {
    var m = document.getElementById('tfCreateModal');
    if (m) m.classList.remove('on');
}

function tfDeskCreate(what) {
    tfDeskCreateClose();
    try {
        if (what === 'post') {
            if (typeof openPage === 'function') openPage('composer-overlay');
            if (typeof hideNavBar === 'function') hideNavBar();
        } else if (what === 'live') {
            if (typeof openLiveStreamFeed === 'function') openLiveStreamFeed();
        } else if (what === 'eddie') {
            if (typeof openEddieChat === 'function') openEddieChat();
        }
    } catch (e) {
        console.warn('[desktop] create', what, e && e.message);
    }
}

// ------------------------------------------------------------------- boot --

// The app carries its own signed-out marker on #app. Mirrored onto the root so
// the stylesheet can hide the laptop chrome, because CSS cannot reach a
// sibling's class from here.
function tfDeskSyncAuth() {
    var app = document.getElementById('app');
    var out = !app || app.classList.contains('not-authenticated');
    var wasOut = document.documentElement.classList.contains('tf-logged-out');
    document.documentElement.classList.toggle('tf-logged-out', out);
    if (!out) {
        tfDeskFillMe();
        // Signing in is the moment the suggestions become answerable: before
        // it there is no "you" to leave out and nobody known to be followed.
        if (wasOut) tfDeskLoadRail();
    }
}

function tfDeskInit() {
    if (!tfIsDesktop()) return;
    document.documentElement.classList.add('tf-is-desktop');
    tfDeskSyncAuth();
    tfDeskFillMe();
    tfDeskSyncBadges();
    tfDeskLoadRail();
}

// The pill updates its badges whenever counts change, and there is no event to
// listen for, so the sidebar checks the same elements on a slow timer. Cheap:
// it reads two nodes already in the page and touches nothing else.
if (typeof window !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
        tfDeskInit();
        setInterval(tfDeskSyncBadges, 4000);
        setInterval(tfReelNavSync, 700);
        setInterval(tfDeskWideSync, 500);
        // Signing in removes a class rather than reloading the page, so the
        // chrome has to be told. Watching the attribute costs nothing and
        // cannot drift the way a timer would.
        var appEl = document.getElementById('app');
        if (appEl && window.MutationObserver) {
            new MutationObserver(tfDeskSyncAuth).observe(appEl, {
                attributes: true, attributeFilter: ['class']
            });
        }
        // currentUser arrives after the session is restored, which is later
        // than DOMContentLoaded, so the avatar is filled again once it exists.
        var tries = 0;
        var waitForUser = setInterval(function () {
            if (tfMe() || ++tries > 40) {
                clearInterval(waitForUser);
                tfDeskFillMe();
                tfDeskLoadRail();
            }
        }, 500);
    });

    // A window dragged across the breakpoint should settle into the right
    // layout rather than needing a reload.
    window.addEventListener('resize', function () {
        clearTimeout(window._tfDeskResize);
        window._tfDeskResize = setTimeout(tfDeskInit, 250);
    });
}

// ------------------------------------------------------------------- clips --

// Whichever element is actually doing the scrolling. The clip player builds
// its container at runtime and the markup has changed before, so this asks
// rather than assuming one id will always be there.
function tfReelScroller() {
    var overlay = document.getElementById('reel-overlay');
    if (!overlay) return null;
    var candidates = [
        document.getElementById('reelsContainer'),
        overlay.querySelector('.reel-viewport'),
        overlay,
    ];
    for (var i = 0; i < candidates.length; i++) {
        var el = candidates[i];
        if (el && el.scrollHeight > el.clientHeight + 10) return el;
    }
    return null;
}

// One clip per press. Snapping does the aligning, this only has to move by
// roughly a screen and let the snap points finish the job.
function tfReelStep(direction) {
    var sc = tfReelScroller();
    if (!sc) return;
    sc.scrollBy({ top: direction * sc.clientHeight, behavior: 'smooth' });
}

// The arrows exist only while clips are on screen. Watching the overlay is
// more reliable than hooking every function that might open or close it.
function tfReelNavSync() {
    var nav = document.getElementById('tfReelNav');
    if (!nav) return;
    var overlay = document.getElementById('reel-overlay');
    var open = !!overlay && getComputedStyle(overlay).display !== 'none';
    nav.classList.toggle('on', open && tfIsDesktop());
}

// ----------------------------------------------------------------- account --

function tfDeskAccountMenu(anchorEl) {
    var menu = document.getElementById('tfAccountMenu');
    if (!menu) return;
    if (menu.classList.contains('on')) { menu.classList.remove('on'); return; }
    var r = anchorEl.getBoundingClientRect();
    menu.style.left = Math.round(r.left - 40) + 'px';
    menu.style.top = Math.round(r.top - 60) + 'px';
    menu.classList.add('on');
    setTimeout(function () {
        document.addEventListener('click', function close(e) {
            if (!menu.contains(e.target)) {
                menu.classList.remove('on');
                document.removeEventListener('click', close);
            }
        });
    }, 0);
}

function tfDeskLogOut() {
    var menu = document.getElementById('tfAccountMenu');
    if (menu) menu.classList.remove('on');
    if (typeof logOut === 'function') { logOut(); return; }
    console.warn('[desktop] no logOut function');
}

// ---------------------------------------------------------------- settings --

// Settings is one long list of 131 rows, which is correct for a thumb and
// wrong for a mouse. This groups what is already in the page rather than
// building a second settings screen: the rows, their handlers and their order
// are untouched, they are only put into boxes and one box is shown at a time.
//
// Nothing is destroyed, so if the window is dragged narrow the stylesheet
// stops hiding groups and the original single list is back.
var TF_SET_ICONS = {
    'YOUR TRUSTFIRST EXPERIENCE': 'fa-compass',
    'ACCOUNT': 'fa-user',
    'FOR CREATORS': 'fa-chart-simple',
    'WELLBEING': 'fa-heart',
    'PREFERENCES': 'fa-sliders',
    'EXPLORE': 'fa-magnifying-glass',
    'STORAGE': 'fa-box-archive',
    'SUPPORT': 'fa-circle-question',
    'ADMIN TOOLS': 'fa-shield-halved',
};

function tfDeskSplitSettings() {
    if (!tfIsDesktop()) return;
    var overlay = document.getElementById('settings-overlay');
    if (!overlay || overlay.querySelector('.tf-set-split')) return;   // once only

    // The padded box holding the cards, found by what it contains rather than
    // by a class it does not have.
    var content = null;
    var kids = overlay.children;
    for (var i = 0; i < kids.length; i++) {
        if (kids[i].querySelector && kids[i].querySelector('.settings-card')) {
            content = kids[i];
            break;
        }
    }
    if (!content) return;

    var nodes = Array.prototype.slice.call(content.children);
    var groups = [];
    var current = { title: 'Your account', nodes: [] };

    nodes.forEach(function (n) {
        if (n.classList && n.classList.contains('settings-section-title')) {
            if (current.nodes.length) groups.push(current);
            current = { title: (n.textContent || '').trim(), nodes: [], titleNode: n };
        } else {
            current.nodes.push(n);
        }
    });
    if (current.nodes.length) groups.push(current);
    if (groups.length < 2) return;

    var split = document.createElement('div');
    split.className = 'tf-set-split';
    var nav = document.createElement('div');
    nav.className = 'tf-set-nav';
    var body = document.createElement('div');
    body.className = 'tf-set-body';
    split.appendChild(nav);
    split.appendChild(body);

    groups.forEach(function (g, idx) {
        var box = document.createElement('div');
        box.className = 'tf-set-group' + (idx === 0 ? ' tf-set-on' : '');
        box.setAttribute('data-group', String(idx));
        // The heading moves into the group: the left list already names it, and
        // repeating it above the rows says the same thing twice.
        g.nodes.forEach(function (n) { box.appendChild(n); });
        body.appendChild(box);

        // Sentence case, except the brand, which is not a word to be lowered.
        var pretty = g.title.replace(/&amp;/g, '&');
        pretty = pretty.charAt(0).toUpperCase() + pretty.slice(1).toLowerCase();
        pretty = pretty.replace(/trustfirst/gi, 'TrustFirst');

        var cat = document.createElement('div');
        cat.className = 'tf-set-cat' + (idx === 0 ? ' tf-on' : '');
        cat.setAttribute('data-group', String(idx));
        cat.innerHTML = '<span><i class="fa-solid ' +
            (TF_SET_ICONS[g.title] || 'fa-gear') +
            '" style="width:18px;margin-right:9px;"></i>' + escapeHtml(pretty) +
            '</span><i class="fa-solid fa-chevron-right"></i>';
        cat.onclick = function () { tfDeskSettingsShow(idx); };
        nav.appendChild(cat);

        if (g.titleNode && g.titleNode.parentNode) {
            g.titleNode.parentNode.removeChild(g.titleNode);
        }
    });

    content.appendChild(split);
    tfDeskSettingsPrune();

    // Searching has to reach every group, not only the open one.
    var box = document.getElementById('settingsSearchInput');
    if (box) {
        box.addEventListener('input', function () {
            split.classList.toggle('tf-set-searching', !!this.value.trim());
        });
    }
}

function tfDeskSettingsShow(idx) {
    var overlay = document.getElementById('settings-overlay');
    if (!overlay) return;
    overlay.querySelectorAll('.tf-set-group').forEach(function (g) {
        g.classList.toggle('tf-set-on', g.getAttribute('data-group') === String(idx));
    });
    overlay.querySelectorAll('.tf-set-cat').forEach(function (c) {
        c.classList.toggle('tf-on', c.getAttribute('data-group') === String(idx));
    });
    overlay.scrollTop = 0;
}

// Categories whose rows are all hidden do not get shown.
//
// Admin tools is the case that matters: its rows carry display:none until the
// account is confirmed to be an admin, so without this everybody else sees an
// Admin tools heading that opens onto nothing. Run again after the admin check
// has had time to land, because that happens after settings is drawn.
function tfDeskSettingsPrune() {
    var overlay = document.getElementById('settings-overlay');
    if (!overlay) return;
    var firstVisible = -1;
    overlay.querySelectorAll('.tf-set-group').forEach(function (g) {
        var idx = g.getAttribute('data-group');
        var rows = g.querySelectorAll('.settings-row');
        var anyVisible = false;
        for (var i = 0; i < rows.length; i++) {
            if (getComputedStyle(rows[i]).display !== 'none') { anyVisible = true; break; }
        }
        var cat = overlay.querySelector('.tf-set-cat[data-group="' + idx + '"]');
        if (cat) cat.style.display = anyVisible ? '' : 'none';
        if (anyVisible && firstVisible < 0) firstVisible = parseInt(idx, 10);
    });

    // If the open category was the one just hidden, move to a real one.
    var open = overlay.querySelector('.tf-set-group.tf-set-on');
    if (open) {
        var openCat = overlay.querySelector('.tf-set-cat[data-group="' +
            open.getAttribute('data-group') + '"]');
        if ((!openCat || openCat.style.display === 'none') && firstVisible >= 0) {
            tfDeskSettingsShow(firstVisible);
        }
    }
}

// Screens that read better with the third column out of the way.
//
// Settings is a list beside a pane; in a 600px column the pane is too narrow
// to be worth having. Watched rather than set by the opener, so closing the
// screen any way at all puts the rail back.
var TF_WIDE_SCREENS = ['settings-overlay', 'msg-overlay'];

function tfDeskWideSync() {
    if (!tfIsDesktop()) {
        document.documentElement.classList.remove('tf-wide');
        return;
    }
    var wide = TF_WIDE_SCREENS.some(function (id) {
        var el = document.getElementById(id);
        return el && getComputedStyle(el).display !== 'none';
    });
    document.documentElement.classList.toggle('tf-wide', wide);

    // Messages gets a second class of its own, because the two panes are laid
    // out inside the column and that is a different question from how wide the
    // column is.
    var msgs = document.getElementById('msg-overlay');
    var msgsOpen = !!msgs && getComputedStyle(msgs).display !== 'none';
    document.documentElement.classList.toggle('tf-msgs', msgsOpen);

    if (msgsOpen) {
        var chat = document.getElementById('chat-interface');
        var chatOpen = !!chat && getComputedStyle(chat).display !== 'none';
        var empty = document.getElementById('tfMsgEmpty');
        if (!empty) {
            empty = document.createElement('div');
            empty.id = 'tfMsgEmpty';
            empty.innerHTML =
                '<i class="fa-regular fa-comments"></i>' +
                '<b>Your messages</b>' +
                '<span>Pick a conversation on the left, or start a new one.</span>';
            var app = document.getElementById('app');
            if (app) app.appendChild(empty);
        }
        empty.classList.toggle('on', !chatOpen);
    }
}
