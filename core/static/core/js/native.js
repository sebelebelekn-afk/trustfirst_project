// ============================================================
// NATIVE BRIDGE — only does anything inside the Capacitor shell.
// In the browser PWA every function here no-ops and the existing
// web behaviour is left exactly as it was.
//
// The shell loads this site from a URL rather than a bundled build, so the npm
// plugin wrappers are not available on the page. Capacitor still injects its
// bridge, so we call window.Capacitor.Plugins.<Name> directly, which is the
// supported way to reach a native plugin from a remotely loaded page.
// ============================================================

function tfIsNative() {
    try { return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()); }
    catch (e) { return false; }
}
function tfPlatform() {
    try { return (window.Capacitor && window.Capacitor.getPlatform && window.Capacitor.getPlatform()) || 'web'; }
    catch (e) { return 'web'; }
}
function _tfPlugin(name) {
    try { return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins[name]) || null; }
    catch (e) { return null; }
}

// ---------- Push notifications ----------------------------------------------
// Android delivery needs a Firebase project and its google-services.json in the
// native build. Without it registration simply fails and we stay silent rather
// than nagging the user.
async function tfInitPush() {
    var Push = _tfPlugin('PushNotifications');
    if (!tfIsNative() || !Push) return false;
    try {
        var perm = await Push.checkPermissions();
        if (perm.receive !== 'granted') {
            perm = await Push.requestPermissions();
        }
        if (perm.receive !== 'granted') return false;

        Push.addListener('registration', function (t) {
            if (t && t.value) _tfSavePushToken(t.value);
        });
        Push.addListener('registrationError', function (e) {
            console.warn('[Push] registration failed:', e && e.error);
        });
        // Tapping a notification should land on the thing it was about.
        Push.addListener('pushNotificationActionPerformed', function (a) {
            var data = (a && a.notification && a.notification.data) || {};
            _tfRoutePush(data);
        });

        await Push.register();
        return true;
    } catch (e) { console.warn('[Push] init failed:', e && e.message); return false; }
}

// feed.js declares currentUser as a lexical binding, so it is not always the same
// object as window.currentUser. Read whichever one actually holds the user, never
// guard on one and dereference the other.
function _tfUser() {
    if (window.currentUser) return window.currentUser;
    try { return (typeof currentUser !== 'undefined' && currentUser) ? currentUser : null; }
    catch (e) { return null; }
}

async function _tfSavePushToken(token) {
    var u = _tfUser();
    if (!token || !window.sb || !u) return;
    try {
        await sb.from('device_push_tokens').upsert({
            user_id: u.id,
            token: token,
            platform: tfPlatform(),
            updated_at: new Date().toISOString()
        }, { onConflict: 'token' });
    } catch (e) { console.warn('[Push] token save failed:', e && e.message); }
}

// Send the user where the notification points. Falls back to opening
// notifications so a tap is never a dead end.
function _tfRoutePush(data) {
    try {
        if (data.post_id && typeof realOpenComments === 'function') { realOpenComments(data.post_id); return; }
        if (data.conversation_id && typeof openConversation === 'function') { openConversation(data.conversation_id); return; }
        if (data.user_id && typeof viewUserProfile === 'function') { viewUserProfile(data.user_id); return; }
        if (typeof openNotifications === 'function') openNotifications();
    } catch (e) {}
}

// Signing out should stop this device receiving that account's notifications.
async function tfClearPushToken() {
    var u = _tfUser();
    if (!window.sb || !u) return;
    try { await sb.from('device_push_tokens').delete().eq('user_id', u.id); } catch (e) {}
}

// ---------- Native media picker ---------------------------------------------
// The web <input type=file> is what runs in the browser. Inside the shell we can
// use the real OS media picker, which handles large videos better and does not
// depend on WebView quirks.
function _tfB64ToFile(b64, mime, name) {
    var bin = atob(b64);
    var len = bin.length;
    var buf = new Uint8Array(len);
    for (var i = 0; i < len; i++) buf[i] = bin.charCodeAt(i);
    return new File([buf], name || ('media_' + Date.now()), { type: mime || 'application/octet-stream' });
}

// Returns an array of File objects, or null when the native picker is not
// available so the caller can fall back to the web input.
async function tfPickMedia(opts) {
    var FilePicker = _tfPlugin('FilePicker');
    if (!tfIsNative() || !FilePicker) return null;
    opts = opts || {};
    try {
        var res = await FilePicker.pickMedia({
            readData: true,
            limit: opts.multiple ? 0 : 1     // 0 means no limit
        });
        var picked = (res && res.files) || [];
        if (!picked.length) return [];        // cancelled, do not fall back
        return picked.map(function (f) {
            return _tfB64ToFile(f.data, f.mimeType, f.name);
        });
    } catch (e) {
        console.warn('[Native picker] failed, using web input:', e && e.message);
        return null;                           // fall back to the web input
    }
}

// Wrap the existing pickers. Each keeps its web behaviour whenever the native
// path is unavailable or the plugin errors.
(function () {
    var _webTrustclipPick = window.pickTrustclipMedia;
    window.pickTrustclipMedia = function () {
        if (!tfIsNative()) return _webTrustclipPick && _webTrustclipPick();
        tfPickMedia({ multiple: true }).then(function (files) {
            if (files === null) return _webTrustclipPick && _webTrustclipPick();
            if (!files.length) return;         // user cancelled
            window._clipFileObjects = files;
            window.selectedClipFiles = [];
            if (typeof openPage === 'function') openPage('clip-selector-overlay');
            if (typeof _renderClipGallery === 'function') _renderClipGallery(files);
            if (typeof _autoSelectAllClips === 'function') _autoSelectAllClips();
        });
    };

    var _webChatPick = window.openChatMediaPicker;
    window.openChatMediaPicker = function () {
        if (!tfIsNative()) return _webChatPick && _webChatPick();
        tfPickMedia({ multiple: false }).then(function (files) {
            if (files === null) return _webChatPick && _webChatPick();
            if (!files.length) return;
            // handleChatMediaPick only reads .files, so a stand-in works here.
            if (typeof handleChatMediaPick === 'function') handleChatMediaPick({ files: files, value: '' });
        });
    };
})();

// The story camera's gallery button, wrapped separately because story-camera.js
// loads after this file. Deferred to first use so the override lands on the real
// implementation rather than an undefined global.
(function () {
    var wrapped = false;
    function wrapStoryGallery() {
        if (wrapped || typeof window.lgGallery !== 'function') return;
        wrapped = true;
        var webPick = window.lgGallery;
        window.lgGallery = function () {
            if (!tfIsNative()) return webPick();
            tfPickMedia({ multiple: true }).then(function (files) {
                if (files === null) return webPick();      // plugin missing, use the web input
                if (!files.length) return;                 // cancelled
                window._lgPicked = files;
                window._lgSelected = files.map(function (_, i) { return i; });
                if (typeof openLgGalleryPicker === 'function') openLgGalleryPicker();
            });
        };
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wrapStoryGallery);
    else wrapStoryGallery();
    // story-camera.js may still be parsing at DOMContentLoaded, so try once more.
    setTimeout(wrapStoryGallery, 1200);
})();

// ---------- Boot -------------------------------------------------------------
// Register for push once there is a signed-in user to attach the token to.
(function () {
    if (!tfIsNative()) return;
    var tries = 0;
    var iv = setInterval(function () {
        tries++;
        if (_tfUser() && window.sb) { clearInterval(iv); tfInitPush(); }
        else if (tries > 60) { clearInterval(iv); }   // ~60s, user never signed in
    }, 1000);
})();
