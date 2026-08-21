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

// ---------- Open a link outside the app -------------------------------------
// A button labelled "open in browser" has to hand the link to the browser, not
// stack another view inside this app. What is actually possible depends on
// where the app is running, and this reports which happened so the caller can
// tell the truth rather than assume.
//
//   native shell   AppLauncher.openUrl gives the URL to whatever the device has
//                  set as its default browser. This is the real thing.
//   browser tab    a plain anchor opens a new tab, which is the browser.
//   installed PWA  neither is available. iOS in particular keeps target=_blank
//                  inside the app window, which is exactly the "it just expands
//                  the page" behaviour. Nothing here can override that, so it
//                  returns 'inapp' and the caller offers the link instead.
//
// window.open(url, '_blank', features) was what it used before. Passing a
// feature string asks for a popup window, and a webview answers that by opening
// another view of its own, which is the bug.
async function tfOpenExternalUrl(url) {
    if (!url) return 'failed';

    var Launcher = _tfPlugin('AppLauncher');
    if (tfIsNative() && Launcher && Launcher.openUrl) {
        try {
            var res = await Launcher.openUrl({ url: url });
            // completed === false means the system found nothing to handle it.
            if (!res || res.completed !== false) return 'native';
        } catch (e) { /* fall through and try the web route */ }
    }

    var standalone = false;
    try {
        standalone = window.navigator.standalone === true ||
            (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches);
    } catch (e) {}

    try {
        var a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch (e) { return 'failed'; }

    return standalone ? 'inapp' : 'tab';
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

    // Composer "add photo": the OS sheet returns several files at once, which
    // is what the composer's carousel wants.
    var _webComposerPick = window.openMedia;
    window.openMedia = function () {
        if (!tfIsNative()) return _webComposerPick && _webComposerPick();
        tfPickMedia({ multiple: true }).then(function (files) {
            if (files === null) return _webComposerPick && _webComposerPick();
            if (!files.length) return;             // user cancelled
            if (typeof handleMediaSelected === 'function') handleMediaSelected({ files: files, value: '' });
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

// ---------- Reading the real photo library ----------------------------------
// A web page cannot enumerate the camera roll, which is why every picker so far
// has had to hand off to the OS sheet. Inside the shell a native plugin CAN read
// the library, so the grids can show the user's actual photos and videos.
//
// Thumbnails come back as base64 so the grid paints immediately. The full file
// is only fetched for the items actually chosen, because pulling originals for a
// whole library would be slow and memory hungry.

// True when the grid can be filled with the real library.
function tfCanListLibrary() {
    return !!(tfIsNative() && _tfPlugin('Media'));
}

// Ask once; without permission the plugin returns nothing useful.
async function tfLibraryPermission() {
    var Media = _tfPlugin('Media');
    if (!Media) return false;
    try {
        if (typeof Media.checkPermissions === 'function') {
            var p = await Media.checkPermissions();
            var ok = p && (p.photos === 'granted' || p.photos === 'limited' ||
                           p.publicStorage === 'granted' || p.mediaLibrary === 'granted');
            if (!ok && typeof Media.requestPermissions === 'function') {
                p = await Media.requestPermissions();
                ok = p && (p.photos === 'granted' || p.photos === 'limited' ||
                           p.publicStorage === 'granted' || p.mediaLibrary === 'granted');
            }
            return !!ok;
        }
        return true;   // older plugin versions prompt on first read
    } catch (e) { return false; }
}

// Returns [{ id, thumb, isVideo, created }] newest first, or null when the
// library cannot be read so the caller can fall back to the OS picker.
async function tfListLibrary(opts) {
    var Media = _tfPlugin('Media');
    if (!tfIsNative() || !Media) return null;
    opts = opts || {};
    try {
        if (!(await tfLibraryPermission())) return null;
        var res = await Media.getMedias({
            quantity: opts.limit || 120,
            thumbnailWidth: 320,
            thumbnailHeight: 320,
            thumbnailQuality: 88,
            sort: 'creationDate'
        });
        var items = (res && (res.medias || res.media)) || [];
        return items.map(function (m) {
            var thumb = m.data || m.thumbnail || '';
            if (thumb && thumb.indexOf('data:') !== 0) thumb = 'data:image/jpeg;base64,' + thumb;
            return {
                id: m.identifier || m.id,
                thumb: thumb,
                // The plugin reports videos either by a type field or a duration.
                isVideo: (m.mediaType === 'video' || m.type === 'video' || !!m.duration),
                created: m.creationDate || m.created || 0
            };
        }).filter(function (m) { return m.id && m.thumb; });
    } catch (e) {
        console.warn('[Library] read failed, falling back to the picker:', e && e.message);
        return null;
    }
}

// Pull the full file for one library item, only when it is actually chosen.
async function tfLibraryFile(id, isVideo) {
    var Media = _tfPlugin('Media');
    if (!Media || !id) return null;
    try {
        var fn = Media.getMediaByIdentifier || Media.getMedia || null;
        if (!fn) return null;
        var res = await fn.call(Media, { identifier: id });
        var b64 = res && (res.data || res.base64 || res.base64String);
        if (b64) {
            if (b64.indexOf('data:') === 0) b64 = b64.split(',')[1];
            var mime = isVideo ? 'video/mp4' : 'image/jpeg';
            return _tfB64ToFile(b64, mime, (isVideo ? 'video_' : 'photo_') + id + (isVideo ? '.mp4' : '.jpg'));
        }
        // Some versions hand back a path instead of bytes.
        var path = res && (res.path || res.url || res.webPath);
        if (path) {
            var blob = await (await fetch(path)).blob();
            return new File([blob], (isVideo ? 'video.mp4' : 'photo.jpg'), { type: blob.type || (isVideo ? 'video/mp4' : 'image/jpeg') });
        }
        return null;
    } catch (e) { return null; }
}

// ---------- Saving a video to the camera roll --------------------------------
// Returns true only when the file really landed in the gallery. The caller uses
// the answer to decide what to tell the user, so guessing here would put the
// words "Saved to gallery" on screen for a file that is not there.
function _tfBlobToDataUrl(blob) {
    return new Promise(function (resolve, reject) {
        var fr = new FileReader();
        fr.onload = function () { resolve(fr.result); };
        fr.onerror = function () { reject(fr.error || new Error('read failed')); };
        fr.readAsDataURL(blob);
    });
}

async function tfSaveVideoToGallery(blob) {
    var Media = _tfPlugin('Media');
    if (!tfIsNative() || !Media || typeof Media.saveVideo !== 'function') return false;
    try {
        if (!(await tfLibraryPermission())) return false;
        var dataUrl = await _tfBlobToDataUrl(blob);
        await Media.saveVideo({ path: dataUrl });
        return true;
    } catch (e) {
        console.warn('[Native] saveVideo failed:', e && e.message);
        return false;
    }
}
window.tfSaveVideoToGallery = tfSaveVideoToGallery;

// ---------- Native camera capture -------------------------------------------
// The WebView camera is where the quality complaints come from: it hands back a
// landscape stream that has to be cropped hard to fill a phone screen, which is
// what looked like extreme zoom. The OS camera app has none of that problem, and
// gives back a full resolution frame.

// Photos go through the Camera plugin, which opens the real camera UI.
async function tfCapturePhoto() {
    var Camera = _tfPlugin('Camera');
    if (!tfIsNative() || !Camera) return null;
    try {
        var photo = await Camera.getPhoto({
            quality: 92,
            allowEditing: false,
            resultType: 'base64',
            source: 'CAMERA',
            direction: 'FRONT',
            saveToGallery: false
        });
        if (!photo || !photo.base64String) return [];   // cancelled
        var mime = 'image/' + (photo.format || 'jpeg');
        return [_tfB64ToFile(photo.base64String, mime, 'photo_' + Date.now() + '.' + (photo.format || 'jpg'))];
    } catch (e) {
        // The plugin throws on cancel too, so treat it as "nothing picked"
        // rather than falling back and reopening a second camera.
        if (/cancel/i.test((e && e.message) || '')) return [];
        console.warn('[Native camera] photo failed:', e && e.message);
        return null;
    }
}

// The Camera plugin does not record video, so video uses a capture input, which
// on a device hands off to the system camera recorder rather than the WebView.
function tfCaptureVideo() {
    return new Promise(function (resolve) {
        var inp = document.getElementById('_tfVideoCapture');
        if (!inp) {
            inp = document.createElement('input');
            inp.type = 'file';
            inp.id = '_tfVideoCapture';
            inp.accept = 'video/*';
            inp.setAttribute('capture', 'user');
            inp.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;';
            document.body.appendChild(inp);
        }
        inp.onchange = function () {
            var files = inp.files && inp.files.length ? Array.prototype.slice.call(inp.files) : [];
            try { inp.value = ''; } catch (e) {}
            resolve(files);
        };
        try { inp.value = ''; } catch (e) {}
        inp.click();
    });
}

// Capture straight into the story composer.
async function tfStoryCapture(mode) {
    var files = (mode === 'video') ? await tfCaptureVideo() : await tfCapturePhoto();
    if (!files || !files.length) return false;
    if (typeof openLgComposer === 'function') {
        if (typeof closeLgCam === 'function') { try { closeLgCam(); } catch (e) {} }
        openLgComposer(files);
        return true;
    }
    return false;
}

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
            // Show the real camera roll when the library can be read, so the grid
            // is the user's own photos rather than an OS sheet handoff.
            if (tfCanListLibrary()) {
                tfListLibrary({ limit: 120 }).then(function (items) {
                    if (items && items.length) {
                        window._lgPicked = items;
                        window._lgSelected = [];       // nothing preselected when browsing
                        if (typeof openLgGalleryPicker === 'function') openLgGalleryPicker();
                        return;
                    }
                    pickViaSheet();                    // no permission or empty library
                });
                return;
            }
            pickViaSheet();
        };
        function pickViaSheet() {
            tfPickMedia({ multiple: true }).then(function (files) {
                if (files === null) return webPick();      // plugin missing, use the web input
                if (!files.length) return;                 // cancelled
                window._lgPicked = files;
                window._lgSelected = files.map(function (_, i) { return i; });
                if (typeof openLgGalleryPicker === 'function') openLgGalleryPicker();
            });
        }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wrapStoryGallery);
    else wrapStoryGallery();
    // story-camera.js may still be parsing at DOMContentLoaded, so try once more.
    setTimeout(wrapStoryGallery, 1200);
})();

// The story camera's shutter. In the shell this hands off to the system camera
// instead of recording through the WebView preview.
(function () {
    var wrapped = false;
    function wrapShutter() {
        if (wrapped || typeof window.lgToggleRec !== 'function') return;
        wrapped = true;
        var webRec = window.lgToggleRec;
        window.lgToggleRec = function () {
            if (!tfIsNative()) return webRec();
            tfStoryCapture('video').then(function (ok) {
                if (!ok) webRec();     // capture unavailable or cancelled early
            });
        };
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wrapShutter);
    else wrapShutter();
    setTimeout(wrapShutter, 1200);
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
