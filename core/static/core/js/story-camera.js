// ============================================================
// STORY CAMERA (liquid glass) - gallery picker, composer, sound
// picker and sound trimmer.
//
// Scoped to the camera opened from the story area. It reuses the existing
// editor and trustclip screens rather than duplicating them: the tool rail
// opens the editor's own modals, Next hands off to the trustclip composer,
// and Your Story posts straight to stories.
//
// Loaded after feed.js because it overrides lgGallery().
// ============================================================

var _lgPicked = [];        // File objects chosen for this story
var _lgSelected = [];      // indexes ticked in the picker grid
var _lgSound = null;       // { id, name, artist, audio_url, startSec, endSec, loop }

// An entry is either a File the OS picker handed over, or a library item read
// natively as { id, thumb, isVideo }. Both render in the same grid.
function _lgIsVideo(f) {
    if (!f) return false;
    if (f.isVideo !== undefined) return !!f.isVideo;
    return !!(f.type && f.type.indexOf('video/') === 0);
}
function _lgIsLibraryItem(f) { return !!(f && f.thumb && f.id && !(f instanceof File)); }
function _lgFmt(s) {
    s = Math.max(0, Math.round(s || 0));
    return Math.floor(s / 60) + ':' + (s % 60 < 10 ? '0' : '') + (s % 60);
}

// ---------- 1. Gallery picker -------------------------------------------
// A page cannot enumerate the camera roll, so the OS picker supplies the media
// and this grid is where you then choose which of it to use.
function _lgEnsureInput() {
    var inp = document.getElementById('_lgGalleryInput');
    if (!inp) {
        inp = document.createElement('input');
        inp.type = 'file';
        inp.accept = 'image/*,video/*';
        inp.multiple = true;
        inp.id = '_lgGalleryInput';
        inp.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;';
        inp.addEventListener('change', function () {
            if (!inp.files || !inp.files.length) return;
            _lgPicked = Array.prototype.slice.call(inp.files);
            _lgSelected = _lgPicked.map(function (_, i) { return i; });
            openLgGalleryPicker();
            try { inp.value = ''; } catch (e) {}
        });
        document.body.appendChild(inp);
    }
    return inp;
}

// Replaces the camera's gallery button, which previously did nothing.
window.lgGallery = function () {
    var inp = _lgEnsureInput();
    try { inp.value = ''; } catch (e) {}
    inp.click();
};

function openLgGalleryPicker() {
    var ex = document.getElementById('lgGalleryPage');
    if (ex) ex.remove();
    var page = document.createElement('div');
    page.id = 'lgGalleryPage';
    page.style.cssText = 'position:absolute;inset:0;z-index:9700;background:var(--bg-primary,#000);display:flex;flex-direction:column;';
    page.innerHTML =
        '<div style="flex-shrink:0;display:flex;align-items:center;justify-content:space-between;gap:10px;' +
            'padding:max(50px,env(safe-area-inset-top,50px)) 16px 12px;">' +
            '<button onclick="closeLgGalleryPicker()" style="width:36px;height:36px;border-radius:50%;background:rgba(255,255,255,0.12);border:none;color:#fff;font-size:16px;cursor:pointer;"><i class="fa-solid fa-xmark"></i></button>' +
            // A page cannot list the device's albums, so this sorts what you
            // picked by date instead of pretending to browse the library.
            '<div id="lgSortChip" onclick="lgToggleSort()" style="background:rgba(255,255,255,0.12);border-radius:20px;padding:8px 16px;color:#fff;font-size:14px;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:7px;">' +
                '<span id="lgSortLabel">Recents</span><i class="fa-solid fa-chevron-down" style="font-size:10px;opacity:0.7;"></i>' +
            '</div>' +
            '<button onclick="lgGallery()" style="background:rgba(255,255,255,0.12);border:none;border-radius:20px;padding:8px 14px;color:#fff;font-size:13px;font-weight:700;cursor:pointer;">Add more</button>' +
        '</div>' +
        '<div style="flex-shrink:0;display:flex;gap:18px;padding:0 18px 10px;">' +
            ['All', 'Videos', 'Photos'].map(function (t, i) {
                return '<span onclick="lgGalleryFilter(\'' + t.toLowerCase() + '\',this)" class="lg-gal-tab" style="font-size:15px;font-weight:' + (i === 0 ? '800' : '600') + ';color:' + (i === 0 ? '#fff' : 'rgba(255,255,255,0.45)') + ';cursor:pointer;padding-bottom:6px;border-bottom:2px solid ' + (i === 0 ? '#fff' : 'transparent') + ';">' + t + '</span>';
            }).join('') +
        '</div>' +
        '<div id="lgGalleryGrid" style="flex:1;overflow-y:auto;display:grid;grid-template-columns:repeat(3,1fr);gap:3px;padding:0 3px 12px;"></div>' +
        '<div style="flex-shrink:0;display:flex;align-items:center;gap:12px;padding:12px 16px max(28px,env(safe-area-inset-bottom,28px));">' +
            '<span id="lgSelCount" style="flex:1;color:rgba(255,255,255,0.6);font-size:13px;font-weight:600;"></span>' +
            '<button id="lgNextBtn" onclick="lgGalleryNext()" style="background:#007AFF;border:none;border-radius:24px;padding:13px 34px;color:#fff;font-size:15px;font-weight:800;cursor:pointer;">Next</button>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(page);
    _lgRenderGalleryGrid('all');
}

function closeLgGalleryPicker() {
    var p = document.getElementById('lgGalleryPage');
    if (p) p.remove();
}

// Newest first by default, matching what the chip says.
var _lgSortNewest = true;
var _lgActiveFilter = 'all';

function lgToggleSort() {
    _lgSortNewest = !_lgSortNewest;
    // Keep the same files ticked across a re-sort: the selection is held as
    // indexes, so remap it through the files themselves rather than the numbers.
    var chosen = _lgSelected.map(function (i) { return _lgPicked[i]; }).filter(Boolean);
    _lgPicked = _lgPicked.slice().sort(function (a, b) {
        var d = (b.lastModified || 0) - (a.lastModified || 0);
        return _lgSortNewest ? d : -d;
    });
    _lgSelected = chosen.map(function (f) { return _lgPicked.indexOf(f); }).filter(function (i) { return i >= 0; });
    var lbl = document.getElementById('lgSortLabel');
    if (lbl) lbl.textContent = _lgSortNewest ? 'Recents' : 'Oldest';
    if (typeof triggerHaptic === 'function') triggerHaptic(6);
    _lgRenderGalleryGrid(_lgActiveFilter);
}

function lgGalleryFilter(kind, el) {
    _lgActiveFilter = kind;
    document.querySelectorAll('#lgGalleryPage .lg-gal-tab').forEach(function (t) {
        t.style.color = 'rgba(255,255,255,0.45)'; t.style.fontWeight = '600'; t.style.borderBottomColor = 'transparent';
    });
    if (el) { el.style.color = '#fff'; el.style.fontWeight = '800'; el.style.borderBottomColor = '#fff'; }
    _lgRenderGalleryGrid(kind);
}

function _lgRenderGalleryGrid(kind) {
    var grid = document.getElementById('lgGalleryGrid');
    if (!grid) return;
    grid.innerHTML = '';
    _lgPicked.forEach(function (f, i) {
        var isVid = _lgIsVideo(f);
        if (kind === 'videos' && !isVid) return;
        if (kind === 'photos' && isVid) return;
        var on = _lgSelected.indexOf(i) !== -1;
        var cell = document.createElement('div');
        cell.style.cssText = 'position:relative;aspect-ratio:1;background:#111;overflow:hidden;cursor:pointer;';
        // Library items already carry a thumbnail; picked Files need an object URL.
        var media;
        if (_lgIsLibraryItem(f)) {
            media = '<img src="' + f.thumb + '" style="width:100%;height:100%;object-fit:cover;">' +
                    (isVid ? '<i class="fa-solid fa-video" style="position:absolute;left:6px;bottom:6px;color:#fff;font-size:12px;text-shadow:0 1px 3px rgba(0,0,0,0.8);"></i>' : '');
        } else {
            var url = URL.createObjectURL(f);
            media = isVid
                ? '<video src="' + url + '" muted playsinline preload="metadata" style="width:100%;height:100%;object-fit:cover;"></video>'
                : '<img src="' + url + '" style="width:100%;height:100%;object-fit:cover;">';
        }
        cell.innerHTML = media +
            '<div class="lg-tick" style="position:absolute;top:6px;right:6px;width:24px;height:24px;border-radius:50%;' +
                'border:2px solid #fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:#fff;' +
                'background:' + (on ? '#007AFF' : 'rgba(0,0,0,0.3)') + ';">' + (on ? (_lgSelected.indexOf(i) + 1) : '') + '</div>';
        cell.onclick = function () { _lgToggleSelect(i, kind); };
        grid.appendChild(cell);
    });
    _lgUpdateCount();
}

function _lgToggleSelect(i, kind) {
    var at = _lgSelected.indexOf(i);
    if (at === -1) _lgSelected.push(i); else _lgSelected.splice(at, 1);
    if (typeof triggerHaptic === 'function') triggerHaptic(6);
    _lgRenderGalleryGrid(kind || 'all');
}

function _lgUpdateCount() {
    var c = document.getElementById('lgSelCount');
    if (c) c.textContent = _lgSelected.length ? (_lgSelected.length + ' selected') : 'Tap to select';
    var b = document.getElementById('lgNextBtn');
    if (b) { b.style.opacity = _lgSelected.length ? '1' : '0.45'; b.style.pointerEvents = _lgSelected.length ? 'auto' : 'none'; }
}

async function lgGalleryNext() {
    if (!_lgSelected.length) return;
    var chosen = _lgSelected.map(function (i) { return _lgPicked[i]; }).filter(Boolean);
    var btn = document.getElementById('lgNextBtn');
    if (btn) { btn.textContent = 'Loading...'; btn.style.pointerEvents = 'none'; }

    // Library entries are thumbnails only, so fetch the originals now, for the
    // few that were actually chosen rather than the whole library.
    var files = [];
    for (var i = 0; i < chosen.length; i++) {
        var it = chosen[i];
        if (_lgIsLibraryItem(it)) {
            var full = (typeof tfLibraryFile === 'function') ? await tfLibraryFile(it.id, it.isVideo) : null;
            if (full) files.push(full);
        } else {
            files.push(it);
        }
    }
    if (btn) { btn.textContent = 'Next'; btn.style.pointerEvents = 'auto'; }
    if (!files.length) {
        if (typeof showToast === 'function') showToast('Could not open that media');
        return;
    }
    closeLgGalleryPicker();
    openLgComposer(files);
}

// ---------- 2. Composer --------------------------------------------------
// Preview with a tool rail down the side. Each tool opens the editor's own
// modal, so there is one implementation of text, stickers, effects and so on.
function openLgComposer(files) {
    window._lgComposerFiles = files || [];
    var first = window._lgComposerFiles[0];
    if (!first) return;
    var ex = document.getElementById('lgComposer');
    if (ex) ex.remove();
    var url = URL.createObjectURL(first);
    var isVid = _lgIsVideo(first);

    var TOOLS = [
        // Single quotes inside: these go into a double quoted onclick attribute,
        // and double quotes here closed it early, truncating every handler to
        // "lgTool(" so nothing but Edit did anything.
        { label: 'Edit',     icon: 'fa-sliders',        fn: 'lgToolEditor()' },
        { label: 'Text',     icon: 'fa-font',           fn: "lgTool('text')" },
        { label: 'Stickers', icon: 'fa-face-smile',     fn: "lgTool('sticker')" },
        { label: 'Effects',  icon: 'fa-wand-magic-sparkles', fn: "lgTool('effects')" },
        { label: 'Filters',  icon: 'fa-circle-half-stroke', fn: "lgTool('filter')" },
        { label: 'Voice',    icon: 'fa-microphone',     fn: "lgTool('voice')" },
        { label: 'Captions', icon: 'fa-closed-captioning', fn: "lgTool('captions')" }
    ];

    var page = document.createElement('div');
    page.id = 'lgComposer';
    page.style.cssText = 'position:absolute;inset:0;z-index:9700;background:#000;display:flex;flex-direction:column;';
    page.innerHTML =
        '<div style="flex-shrink:0;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:max(48px,env(safe-area-inset-top,48px)) 14px 10px;">' +
            '<button onclick="closeLgComposer()" style="width:36px;height:36px;border-radius:50%;background:rgba(255,255,255,0.14);border:none;color:#fff;font-size:16px;cursor:pointer;"><i class="fa-solid fa-chevron-left"></i></button>' +
            '<div id="lgSoundPill" onclick="openLgSoundModal()" style="display:flex;align-items:center;gap:8px;max-width:62%;background:rgba(0,0,0,0.55);border:0.5px solid rgba(255,255,255,0.18);border-radius:22px;padding:9px 16px;cursor:pointer;">' +
                '<i class="fa-solid fa-music" style="color:#fff;font-size:12px;flex-shrink:0;"></i>' +
                '<span id="lgSoundPillText" style="color:#fff;font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Add sound</span>' +
            '</div>' +
            '<div style="width:36px;"></div>' +
        '</div>' +

        '<div style="flex:1;position:relative;display:flex;align-items:center;justify-content:center;overflow:hidden;min-height:0;">' +
            (isVid
                ? '<video id="lgPreviewMedia" src="' + url + '" autoplay loop playsinline style="max-width:100%;max-height:100%;object-fit:contain;"></video>'
                : '<img id="lgPreviewMedia" src="' + url + '" style="max-width:100%;max-height:100%;object-fit:contain;">') +
            '<div style="position:absolute;right:10px;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:14px;">' +
                TOOLS.map(function (t) {
                    return '<div onclick="' + t.fn + '" style="display:flex;align-items:center;gap:8px;cursor:pointer;justify-content:flex-end;">' +
                        '<span style="color:#fff;font-size:13px;font-weight:700;text-shadow:0 1px 4px rgba(0,0,0,0.8);">' + t.label + '</span>' +
                        '<div style="width:36px;height:36px;border-radius:11px;background:rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;flex-shrink:0;">' +
                            '<i class="fa-solid ' + t.icon + '" style="color:#fff;font-size:15px;"></i></div>' +
                    '</div>';
                }).join('') +
            '</div>' +
        '</div>' +

        '<div style="flex-shrink:0;display:flex;align-items:center;gap:10px;padding:12px 14px max(26px,env(safe-area-inset-bottom,26px));">' +
            '<button id="lgStoryBtn" style="flex:1;background:#fff;border:none;border-radius:26px;padding:14px;color:#000;font-size:15px;font-weight:800;cursor:pointer;">Your Story</button>' +
            '<button onclick="lgComposerNext()" style="flex:1;background:#007AFF;border:none;border-radius:26px;padding:14px;color:#fff;font-size:15px;font-weight:800;cursor:pointer;">Next</button>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(page);
    _lgSyncSoundPill();
    _lgWireStoryButton();
}

function closeLgComposer() {
    var p = document.getElementById('lgComposer');
    if (p) p.remove();
}

// Tap posts to your story as-is. Long press asks who can see it first.
function _lgWireStoryButton() {
    var btn = document.getElementById('lgStoryBtn');
    if (!btn) return;
    var timer = null, held = false;
    function down() {
        held = false;
        timer = setTimeout(function () { held = true; if (typeof triggerHaptic === 'function') triggerHaptic(15); openLgAudienceSheet(); }, 500);
    }
    function up() { clearTimeout(timer); if (!held) lgPostStory(); }
    btn.addEventListener('touchstart', down, { passive: true });
    btn.addEventListener('touchend', up);
    btn.addEventListener('mousedown', down);
    btn.addEventListener('mouseup', up);
    btn.addEventListener('mouseleave', function () { clearTimeout(timer); });
}

function openLgAudienceSheet() {
    var ex = document.getElementById('lgAudienceSheet');
    if (ex) ex.remove();
    var sheet = document.createElement('div');
    sheet.id = 'lgAudienceSheet';
    sheet.style.cssText = 'position:absolute;inset:0;z-index:9800;background:rgba(0,0,0,0.55);display:flex;flex-direction:column;justify-content:flex-end;';
    sheet.onclick = function (e) { if (e.target === sheet) sheet.remove(); };
    sheet.innerHTML =
        '<div style="background:rgba(22,22,24,0.98);backdrop-filter:blur(30px);border-radius:26px 26px 0 0;padding:20px 20px max(30px,env(safe-area-inset-bottom,30px));">' +
            '<div style="width:40px;height:4px;background:rgba(255,255,255,0.2);border-radius:4px;margin:0 auto 18px;"></div>' +
            '<b style="color:#fff;font-size:17px;display:block;margin-bottom:4px;">Who can see this story?</b>' +
            '<p style="color:rgba(255,255,255,0.45);font-size:13px;margin:0 0 16px;">You can change this before you post.</p>' +
            '<div onclick="lgSetAudience(\'everyone\')" style="display:flex;align-items:center;gap:14px;padding:15px 4px;border-bottom:0.5px solid rgba(255,255,255,0.08);cursor:pointer;">' +
                '<div style="width:42px;height:42px;border-radius:50%;background:rgba(0,122,255,0.16);display:flex;align-items:center;justify-content:center;"><i class="fa-solid fa-globe" style="color:#007AFF;"></i></div>' +
                '<div><b style="color:#fff;font-size:15px;">Everyone</b><p style="color:rgba(255,255,255,0.45);font-size:12px;margin:2px 0 0;">Anyone on TrustFirst</p></div>' +
            '</div>' +
            '<div onclick="lgSetAudience(\'trustcircle\')" style="display:flex;align-items:center;gap:14px;padding:15px 4px;cursor:pointer;">' +
                '<div style="width:42px;height:42px;border-radius:50%;background:rgba(52,199,89,0.16);display:flex;align-items:center;justify-content:center;"><i class="fa-solid fa-shield-halved" style="color:#34C759;"></i></div>' +
                '<div><b style="color:#fff;font-size:15px;">Trust Circle</b><p style="color:rgba(255,255,255,0.45);font-size:12px;margin:2px 0 0;">Only people in your circle</p></div>' +
            '</div>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(sheet);
}

function lgSetAudience(a) {
    window._lgStoryAudience = a;
    var s = document.getElementById('lgAudienceSheet');
    if (s) s.remove();
    var btn = document.getElementById('lgStoryBtn');
    if (btn) btn.textContent = a === 'trustcircle' ? 'Post to Trust Circle' : 'Post to Everyone';
    if (typeof showToast === 'function') showToast(a === 'trustcircle' ? 'Trust Circle only' : 'Visible to everyone');
}

// Post straight to stories, skipping the story editor.
async function lgPostStory() {
    var f = (window._lgComposerFiles || [])[0];
    if (!f) return;
    if (typeof showToast === 'function') showToast('Posting story...');
    closeLgComposer();
    if (typeof closeLgCam === 'function') { try { closeLgCam(); } catch (e) {} }
    try {
        if (!window.sb || !window.currentUser) { showToast('Please sign in'); return; }
        // An iPhone photo arrives as HEIC, which storage refused and Android
        // cannot display. Re-encode to JPEG first; videos pass straight through.
        if (!_lgIsVideo(f) && typeof tfNormaliseImageFile === 'function') {
            try { f = await tfNormaliseImageFile(f); } catch (e) {}
        }
        var ext = (f.name && f.name.split('.').pop()) || (_lgIsVideo(f) ? 'mp4' : 'jpg');
        var path = currentUser.id + '/story_' + Date.now() + '.' + ext;
        // Same route as every other upload: R2 first, Supabase if that fails.
        // This was going only to Supabase, which is the storage that ran out.
        var url;
        try {
            url = await tfUploadPublicMedia(f, 'story', 'stories', path);
        } catch (upErr) {
            // Say what actually went wrong. The bare "Could not upload story" is
            // why a rejected file type looked like the feature simply not working.
            showToast('Story upload failed: ' + ((upErr && upErr.message) || 'try again'));
            return;
        }
        if (!url) { showToast('Story upload failed: no address came back'); return; }
        var row = {
            user_id: currentUser.id,
            media_url: url,
            media_type: _lgIsVideo(f) ? 'video' : 'image',
            audience: window._lgStoryAudience || 'everyone'
        };
        if (_lgSound && _lgSound.name) row.sound_name = _lgSound.name;

        // The upload has already succeeded by this point: the media is stored
        // and only the row is missing. A bare "load failed" here is Safari's
        // wording for a request that never completed, which is worth separating
        // from the database refusing the row, because one is worth retrying on
        // the spot and the other is not. Retried once before giving up, since
        // the usual cause is a connection that dropped while a large video was
        // going up.
        var res = await sb.from('stories').insert(row);
        if (res.error && /load failed|fetch|network/i.test(res.error.message || '')) {
            await new Promise(function (r) { setTimeout(r, 1200); });
            res = await sb.from('stories').insert(row);
        }
        if (res.error) {
            console.error('[Story] insert failed', res.error, row);
            showToast('Could not post story: ' + (res.error.message || 'try again') +
                      ' — the file uploaded, only the post did not save');
            return;
        }
        showToast('Story posted');
        if (typeof triggerHaptic === 'function') triggerHaptic(25);
    } catch (e) { showToast('Story failed: ' + ((e && e.message) || 'try again')); }
}

// Next skips the editor and goes to the trustclip composer for the caption step.
function lgComposerNext() {
    var f = (window._lgComposerFiles || [])[0];
    if (!f) return;
    try { window._lastPickedVideoSrc = URL.createObjectURL(f); window._lastRecordedBlob = null; } catch (e) {}
    if (_lgSound && _lgSound.name) window._tcAudioName = _lgSound.name;
    if (_lgSound && _lgSound.id) window._tcSoundId = _lgSound.id;
    // Next skips the editor, so Back must return here rather than opening one.
    if (typeof tfSetOrigin === 'function') tfSetOrigin('trustclip', 'story-camera');
    closeLgComposer();
    if (typeof closeLgCam === 'function') { try { closeLgCam(); } catch (e) {} }
    if (typeof openNewTrustClipPost === 'function') openNewTrustClipPost();
    else if (typeof openPage === 'function') openPage('new-trust-clip-overlay');
}

// The Edit tool hands the media to the full editor via the normal clip flow.
function lgToolEditor() {
    var files = window._lgComposerFiles || [];
    if (!files.length) return;
    window._clipFileObjects = files;
    window.selectedClipFiles = files.map(function (_, i) { return i; });
    // Leaving the editor should come back here, not to the clip selector.
    if (typeof tfSetOrigin === 'function') tfSetOrigin('editor', 'story-camera');
    closeLgComposer();
    if (typeof closeLgCam === 'function') { try { closeLgCam(); } catch (e) {} }
    if (typeof openPreviewEditScreen === 'function') openPreviewEditScreen();
}

// The other tools live in the editor, so open it and trigger the matching panel
// rather than building a second copy of each one here.
// The editor exposes one dispatcher, edOpenPanel(kind), and its kinds are the
// same words used on this rail, so a tool passes its kind straight through.
// Waits for the editor's video to be ready rather than guessing a delay, because
// opening a panel before the clip has loaded lands on an empty editor.
function lgTool(kind) {
    lgToolEditor();
    var tries = 0;
    (function waitForEditor() {
        tries++;
        var overlay = document.getElementById('preview-edit-overlay');
        var ready = overlay && overlay.style.display !== 'none' && typeof window.edOpenPanel === 'function';
        if (ready) { window.edOpenPanel(kind); return; }
        if (tries > 40) {   // ~4s, the editor is open but the panel is not reachable
            if (typeof showToast === 'function') showToast('Opened in the editor');
            return;
        }
        setTimeout(waitForEditor, 100);
    })();
}

// ---------- 3. Sound picker ---------------------------------------------
function openLgSoundModal() {
    var ex = document.getElementById('lgSoundModal');
    if (ex) ex.remove();
    var m = document.createElement('div');
    m.id = 'lgSoundModal';
    m.style.cssText = 'position:absolute;inset:0;z-index:9820;background:rgba(0,0,0,0.5);display:flex;flex-direction:column;justify-content:flex-end;';
    m.onclick = function (e) { if (e.target === m) m.remove(); };
    m.innerHTML =
        '<div style="background:var(--bg-primary,#fff);border-radius:20px 20px 0 0;height:66%;display:flex;flex-direction:column;overflow:hidden;">' +
            '<div style="flex-shrink:0;padding:10px 0 0;"><div style="width:40px;height:4px;background:rgba(128,128,128,0.35);border-radius:4px;margin:0 auto;"></div></div>' +
            '<div style="flex-shrink:0;display:flex;align-items:center;gap:18px;padding:14px 18px 8px;">' +
                ['Hot', 'For You', 'Favourites', 'Recent'].map(function (t, i) {
                    return '<span class="lg-snd-tab" onclick="lgSoundTab(\'' + t.toLowerCase().replace(' ', '') + '\',this)" style="font-size:15px;font-weight:' + (i === 1 ? '800' : '600') + ';color:' + (i === 1 ? 'var(--text-primary,#000)' : '#888') + ';cursor:pointer;padding-bottom:6px;border-bottom:2px solid ' + (i === 1 ? 'var(--text-primary,#000)' : 'transparent') + ';">' + t + '</span>';
                }).join('') +
                '<i class="fa-solid fa-magnifying-glass" onclick="lgToggleSoundSearch()" style="margin-left:auto;color:var(--text-primary,#000);font-size:16px;cursor:pointer;"></i>' +
            '</div>' +
            '<div id="lgSoundSearchWrap" style="display:none;flex-shrink:0;padding:0 18px 10px;">' +
                '<input id="lgSoundSearch" oninput="lgSoundTab(\'search\')" placeholder="Search sounds" style="width:100%;padding:11px 14px;border-radius:12px;border:1px solid var(--border-color,#e5e5e5);background:var(--input-bg,#f5f5f5);color:var(--text-primary,#000);font-size:14px;outline:none;box-sizing:border-box;">' +
            '</div>' +
            '<div id="lgSoundList" style="flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 0 20px;"></div>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(m);
    lgSoundTab('foryou');
}

function lgToggleSoundSearch() {
    var w = document.getElementById('lgSoundSearchWrap');
    if (!w) return;
    w.style.display = w.style.display === 'none' ? 'block' : 'none';
    if (w.style.display === 'block') { var i = document.getElementById('lgSoundSearch'); if (i) i.focus(); }
}

async function lgSoundTab(tab, el) {
    if (el) {
        document.querySelectorAll('#lgSoundModal .lg-snd-tab').forEach(function (t) {
            t.style.fontWeight = '600'; t.style.color = '#888'; t.style.borderBottomColor = 'transparent';
        });
        el.style.fontWeight = '800'; el.style.color = 'var(--text-primary,#000)'; el.style.borderBottomColor = 'var(--text-primary,#000)';
    }
    var list = document.getElementById('lgSoundList');
    if (!list) return;
    list.innerHTML = '<div style="text-align:center;padding:30px;color:#888;font-size:13px;">Loading...</div>';
    var rows = [];
    try {
        if (!window.sb) throw new Error('no sb');
        if (tab === 'favourites') {
            var fav = await sb.from('sound_favourites').select('sound_id').eq('user_id', currentUser.id);
            var ids = (fav.data || []).map(function (r) { return r.sound_id; });
            if (ids.length) rows = ((await sb.from('sounds').select('*').in('id', ids)).data) || [];
        } else if (tab === 'search') {
            var q = (document.getElementById('lgSoundSearch') || {}).value || '';
            if (q.trim()) rows = ((await sb.from('sounds').select('*').ilike('name', '%' + q.trim() + '%').limit(40)).data) || [];
        } else {
            var qb = sb.from('sounds').select('*').eq('is_public', true).limit(40);
            qb = (tab === 'recent') ? qb.order('created_at', { ascending: false }) : qb.order('use_count', { ascending: false });
            rows = ((await qb).data) || [];
        }
    } catch (e) { rows = []; }

    if (!rows.length) {
        list.innerHTML = '<div style="text-align:center;padding:40px 24px;color:#888;font-size:13px;line-height:1.6;">' +
            'No sounds here yet.<br>Sounds appear once people post clips with original audio.</div>';
        return;
    }
    list.innerHTML = rows.map(function (s) {
        var cover = s.cover_url || 'https://ui-avatars.com/api/?name=' + encodeURIComponent(s.name || 'S') + '&background=007AFF&color=fff&size=64';
        return '<div style="display:flex;align-items:center;gap:12px;padding:11px 18px;">' +
            '<img src="' + cover + '" onclick="lgPreviewSound(\'' + s.id + '\')" style="width:46px;height:46px;border-radius:8px;object-fit:cover;flex-shrink:0;cursor:pointer;">' +
            '<div style="flex:1;min-width:0;cursor:pointer;" onclick="lgPreviewSound(\'' + s.id + '\')">' +
                '<div style="font-size:15px;font-weight:700;color:var(--text-primary,#000);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + escapeHtml(s.name || 'Sound') + '</div>' +
                '<div style="font-size:12px;color:#888;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + escapeHtml(s.artist || 'Original sound') + ' · ' + _lgFmt(s.duration_sec) + '</div>' +
            '</div>' +
            '<i class="fa-solid fa-scissors" onclick="lgOpenSoundTrim(\'' + s.id + '\')" title="Trim" style="color:var(--text-primary,#000);font-size:16px;padding:8px;cursor:pointer;"></i>' +
            '<i class="fa-regular fa-bookmark" onclick="lgFavSound(\'' + s.id + '\',this)" style="color:var(--text-primary,#000);font-size:16px;padding:8px;cursor:pointer;"></i>' +
        '</div>';
    }).join('');
    window._lgSoundRows = rows;
}

function _lgFindSound(id) {
    return (window._lgSoundRows || []).find(function (s) { return s.id === id; }) || null;
}

// Tapping a sound selects it whole; the scissors opens the trimmer.
function lgPreviewSound(id) {
    var s = _lgFindSound(id);
    if (!s) return;
    _lgSound = { id: s.id, name: s.name, artist: s.artist, audio_url: s.audio_url,
                 startSec: 0, endSec: _lgDefaultLen(), loop: false };
    var m = document.getElementById('lgSoundModal');
    if (m) m.remove();
    _lgSyncSoundPill();
    if (typeof showToast === 'function') showToast('Sound added');
}

async function lgFavSound(id, el) {
    if (!window.sb || !window.currentUser) return;
    try {
        await sb.from('sound_favourites').upsert({ user_id: currentUser.id, sound_id: id });
        if (el) { el.className = 'fa-solid fa-bookmark'; el.style.color = '#007AFF'; }
        if (typeof showToast === 'function') showToast('Saved to favourites');
    } catch (e) {}
}

// Images take a 15 second sound, videos take the clip's length up to 33 seconds.
function _lgDefaultLen() {
    var f = (window._lgComposerFiles || [])[0];
    if (f && !_lgIsVideo(f)) return 15;
    var v = document.getElementById('lgPreviewMedia');
    if (v && v.duration && isFinite(v.duration)) return Math.min(33, Math.round(v.duration));
    return 33;
}

// ---------- 4. Sound trimmer --------------------------------------------
function lgOpenSoundTrim(id) {
    var s = _lgFindSound(id) || (_lgSound && _lgSound.id === id ? _lgSound : null);
    if (!s) return;
    var len = _lgDefaultLen();
    var total = Math.max(len, Math.round(s.duration_sec || 34));
    var isImg = !!((window._lgComposerFiles || [])[0] && !_lgIsVideo(window._lgComposerFiles[0]));

    var ex = document.getElementById('lgTrimSheet');
    if (ex) ex.remove();
    var sheet = document.createElement('div');
    sheet.id = 'lgTrimSheet';
    sheet.style.cssText = 'position:absolute;inset:0;z-index:9840;background:rgba(0,0,0,0.45);display:flex;flex-direction:column;justify-content:flex-end;';
    sheet.onclick = function (e) { if (e.target === sheet) sheet.remove(); };

    var bars = '';
    for (var i = 0; i < 90; i++) {
        var h = 6 + Math.abs(Math.sin(i * 0.7)) * 22;
        bars += '<div class="lg-wave-bar" data-i="' + i + '" style="flex:1;height:' + h.toFixed(1) + 'px;border-radius:1px;background:#111;"></div>';
    }
    sheet.innerHTML =
        '<div style="background:var(--bg-primary,#fff);border-radius:20px 20px 0 0;padding:14px 18px max(28px,env(safe-area-inset-bottom,28px));">' +
            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">' +
                '<i class="fa-solid fa-xmark" onclick="document.getElementById(\'lgTrimSheet\').remove()" style="font-size:20px;color:var(--text-primary,#000);cursor:pointer;padding:4px;"></i>' +
                '<i class="fa-solid fa-check" onclick="lgApplySoundTrim(\'' + s.id + '\')" style="font-size:20px;color:var(--text-primary,#000);cursor:pointer;padding:4px;"></i>' +
            '</div>' +
            '<div id="lgWave" style="display:flex;align-items:center;gap:2px;height:74px;border:2px solid var(--text-primary,#000);border-radius:16px;padding:8px 10px;overflow:hidden;">' + bars + '</div>' +
            '<div style="display:flex;align-items:center;justify-content:space-between;margin-top:14px;">' +
                '<span id="lgTrimLabel" style="font-size:14px;color:var(--text-primary,#000);font-weight:600;">' + len + 's selected</span>' +
                '<div onclick="lgToggleLoop(this)" style="display:flex;align-items:center;gap:8px;cursor:pointer;">' +
                    '<span style="font-size:14px;color:var(--text-primary,#000);">Loop</span>' +
                    '<div id="lgLoopDot" style="width:22px;height:22px;border-radius:50%;border:2px solid #bbb;"></div>' +
                '</div>' +
            '</div>' +
            '<p style="font-size:11px;color:#999;margin:10px 0 0;">' +
                (isImg ? 'Photos use a 15 second sound.' : 'Videos use up to 33 seconds, matched to your clip.') +
            '</p>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(sheet);
    window._lgTrim = { start: 0, len: len, total: total, loop: false };
    _lgPaintWave();
    _lgWireWaveDrag();
}

function _lgPaintWave() {
    var t = window._lgTrim; if (!t) return;
    var bars = document.querySelectorAll('#lgWave .lg-wave-bar');
    var from = Math.round((t.start / t.total) * bars.length);
    var to = Math.round(((t.start + t.len) / t.total) * bars.length);
    bars.forEach(function (b, i) { b.style.background = (i >= from && i < to) ? '#007AFF' : '#c9c9c9'; });
    var lbl = document.getElementById('lgTrimLabel');
    if (lbl) lbl.textContent = t.len + 's selected';
}

// Drag the waveform to move which part of the sound is used.
function _lgWireWaveDrag() {
    var wave = document.getElementById('lgWave');
    if (!wave || wave._wired) return;
    wave._wired = true;
    var startX = 0, baseStart = 0, dragging = false;
    function down(e) {
        dragging = true;
        startX = (e.touches ? e.touches[0].clientX : e.clientX);
        baseStart = (window._lgTrim || {}).start || 0;
    }
    function move(e) {
        if (!dragging) return;
        var t = window._lgTrim; if (!t) return;
        var x = (e.touches ? e.touches[0].clientX : e.clientX);
        var perPx = t.total / Math.max(1, wave.offsetWidth);
        var next = baseStart + (x - startX) * perPx * -1;
        t.start = Math.max(0, Math.min(next, Math.max(0, t.total - t.len)));
        _lgPaintWave();
    }
    function up() { dragging = false; }
    wave.addEventListener('touchstart', down, { passive: true });
    wave.addEventListener('touchmove', move, { passive: true });
    wave.addEventListener('touchend', up);
    wave.addEventListener('mousedown', down);
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
}

function lgToggleLoop(el) {
    var t = window._lgTrim; if (!t) return;
    t.loop = !t.loop;
    var dot = document.getElementById('lgLoopDot');
    if (dot) { dot.style.background = t.loop ? '#007AFF' : 'transparent'; dot.style.borderColor = t.loop ? '#007AFF' : '#bbb'; }
    if (typeof triggerHaptic === 'function') triggerHaptic(6);
}

function lgApplySoundTrim(id) {
    var s = _lgFindSound(id) || _lgSound;
    var t = window._lgTrim || { start: 0, len: 15, loop: false };
    if (s) {
        _lgSound = { id: s.id, name: s.name, artist: s.artist, audio_url: s.audio_url,
                     startSec: Math.round(t.start), endSec: Math.round(t.start + t.len), loop: !!t.loop };
    }
    var sh = document.getElementById('lgTrimSheet'); if (sh) sh.remove();
    var sm = document.getElementById('lgSoundModal'); if (sm) sm.remove();
    _lgSyncSoundPill();
    if (typeof showToast === 'function') showToast('Sound trimmed');
}

// ---------- 5. Sound pill ------------------------------------------------
function _lgSyncSoundPill() {
    var txt = document.getElementById('lgSoundPillText');
    var pill = document.getElementById('lgSoundPill');
    if (!txt || !pill) return;
    if (_lgSound && _lgSound.name) {
        txt.textContent = _lgSound.name;
        pill.style.background = 'rgba(0,0,0,0.72)';
        if (!pill.querySelector('.lg-sound-clear')) {
            var x = document.createElement('i');
            x.className = 'fa-solid fa-xmark lg-sound-clear';
            x.style.cssText = 'color:rgba(255,255,255,0.75);font-size:12px;flex-shrink:0;padding-left:4px;';
            x.onclick = function (e) { e.stopPropagation(); _lgSound = null; _lgSyncSoundPill(); };
            pill.appendChild(x);
        }
    } else {
        txt.textContent = 'Add sound';
        pill.style.background = 'rgba(0,0,0,0.55)';
        var c = pill.querySelector('.lg-sound-clear');
        if (c) c.remove();
    }
}

// Expose the chosen sound so the trustclip insert can record which one was used.
window.lgCurrentSound = function () { return _lgSound; };

// ---------- 6. Collage ---------------------------------------------------
// Shoot several frames into one image. Cells are fractions of the canvas, so a
// layout works at any output size. Order is the order you shoot them in.
var LG_COLLAGE_LAYOUTS = [
    { id: 'grid4',  label: 'Four',        cells: [[0,0,.5,.5],[.5,0,.5,.5],[0,.5,.5,.5],[.5,.5,.5,.5]] },
    { id: 'split2h',label: 'Top bottom',  cells: [[0,0,1,.5],[0,.5,1,.5]] },
    { id: 'strip3', label: 'Three rows',  cells: [[0,0,1,1/3],[0,1/3,1,1/3],[0,2/3,1,1/3]] },
    { id: 'hero3',  label: 'One and two', cells: [[0,0,1,.5],[0,.5,.5,.5],[.5,.5,.5,.5]] },
    { id: 'grid6',  label: 'Six',         cells: [[0,0,.5,1/3],[.5,0,.5,1/3],[0,1/3,.5,1/3],[.5,1/3,.5,1/3],[0,2/3,.5,1/3],[.5,2/3,.5,1/3]] },
    { id: 'split2v',label: 'Side by side',cells: [[0,0,.5,1],[.5,0,.5,1]] }
];

var _lgCollage = null;   // { layout, shots:[dataUrl], idx }

function _lgLayoutIcon(cells) {
    return '<svg viewBox="0 0 24 24" width="26" height="26" style="display:block;">' +
        cells.map(function (c) {
            return '<rect x="' + (1 + c[0] * 22).toFixed(1) + '" y="' + (1 + c[1] * 22).toFixed(1) +
                   '" width="' + (c[2] * 22 - 1).toFixed(1) + '" height="' + (c[3] * 22 - 1).toFixed(1) +
                   '" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.6"/>';
        }).join('') + '</svg>';
}

// Layout picker, opened from the collage button in the camera.
function lgOpenCollagePicker() {
    var ex = document.getElementById('lgCollagePicker');
    if (ex) { ex.remove(); return; }
    var box = document.createElement('div');
    box.id = 'lgCollagePicker';
    box.style.cssText = 'position:absolute;left:14px;bottom:150px;z-index:30;background:rgba(40,40,42,0.92);backdrop-filter:blur(24px);border-radius:18px;padding:12px;display:grid;grid-template-columns:repeat(2,1fr);gap:12px;';
    box.innerHTML = LG_COLLAGE_LAYOUTS.map(function (l) {
        return '<div onclick="lgStartCollage(\'' + l.id + '\')" title="' + l.label + '" ' +
            'style="width:52px;height:52px;border-radius:12px;background:rgba(255,255,255,0.1);color:#fff;' +
            'display:flex;align-items:center;justify-content:center;cursor:pointer;">' + _lgLayoutIcon(l.cells) + '</div>';
    }).join('');
    var page = document.getElementById('lgCameraPage') || document.getElementById('app') || document.body;
    page.appendChild(box);
}

function lgStartCollage(id) {
    var layout = LG_COLLAGE_LAYOUTS.find(function (l) { return l.id === id; });
    if (!layout) return;
    _lgCollage = { layout: layout, shots: [], idx: 0 };
    var p = document.getElementById('lgCollagePicker');
    if (p) p.remove();
    _lgRenderCollageHud();
    if (typeof showToast === 'function') showToast('Tap the shutter for shot 1 of ' + layout.cells.length);
}

function lgCancelCollage() {
    _lgCollage = null;
    var h = document.getElementById('lgCollageHud');
    if (h) h.remove();
    _lgSyncShutter();
}

// A live preview of the collage: filled cells show their shot, the next one is
// outlined so you know where the shutter is about to put the frame.
function _lgRenderCollageHud() {
    if (!_lgCollage) return;
    var hud = document.getElementById('lgCollageHud');
    if (!hud) {
        hud = document.createElement('div');
        hud.id = 'lgCollageHud';
        hud.style.cssText = 'position:absolute;left:12px;top:120px;width:78px;aspect-ratio:9/16;z-index:26;border-radius:10px;overflow:hidden;background:rgba(0,0,0,0.45);border:1px solid rgba(255,255,255,0.3);';
        var page = document.getElementById('lgCameraPage') || document.getElementById('app') || document.body;
        page.appendChild(hud);
    }
    hud.innerHTML = _lgCollage.layout.cells.map(function (c, i) {
        var shot = _lgCollage.shots[i];
        var base = 'position:absolute;left:' + (c[0] * 100) + '%;top:' + (c[1] * 100) + '%;width:' + (c[2] * 100) + '%;height:' + (c[3] * 100) + '%;box-sizing:border-box;';
        if (shot) return '<div style="' + base + 'background-image:url(' + shot + ');background-size:cover;background-position:center;"></div>';
        var next = i === _lgCollage.idx;
        return '<div style="' + base + 'border:' + (next ? '2px solid #007AFF' : '1px solid rgba(255,255,255,0.25)') + ';background:rgba(255,255,255,0.05);"></div>';
    }).join('');
    _lgSyncShutter();
}

// Once every cell is filled the shutter becomes a tick, which finishes it.
function _lgSyncShutter() {
    var dot = document.getElementById('lgDot');
    if (!dot) return;
    var done = _lgCollage && _lgCollage.shots.length >= _lgCollage.layout.cells.length;
    if (done) {
        dot.innerHTML = '<i class="fa-solid fa-check" style="color:#111;font-size:22px;"></i>';
        dot.style.display = 'flex'; dot.style.alignItems = 'center'; dot.style.justifyContent = 'center';
        dot.style.background = '#fff';
    } else {
        dot.innerHTML = '';
        dot.style.background = '';
    }
}

// Grab the current camera frame into the next cell.
function lgCollageShoot() {
    if (!_lgCollage) return false;
    if (_lgCollage.shots.length >= _lgCollage.layout.cells.length) { lgFinishCollage(); return true; }
    var v = document.getElementById('lgVid');
    if (!v || !v.videoWidth) return false;
    try {
        var c = document.createElement('canvas');
        c.width = 720; c.height = Math.round(720 * (v.videoHeight / v.videoWidth));
        c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
        _lgCollage.shots.push(c.toDataURL('image/jpeg', 0.85));
        _lgCollage.idx = _lgCollage.shots.length;
        if (typeof triggerHaptic === 'function') triggerHaptic(12);
        _lgRenderCollageHud();
        var left = _lgCollage.layout.cells.length - _lgCollage.shots.length;
        if (typeof showToast === 'function') {
            showToast(left ? ('Shot ' + (_lgCollage.shots.length + 1) + ' of ' + _lgCollage.layout.cells.length) : 'Tap the tick when ready');
        }
        return true;
    } catch (e) { return false; }
}

// Shoot a cell with the system camera. Falls back to the preview frame if the
// capture is unavailable, and treats a cancel as "no shot" rather than an error.
async function lgCollageShootNative() {
    if (!_lgCollage) return false;
    var files = null;
    try { files = await tfCapturePhoto(); } catch (e) { files = null; }
    if (files === null) return lgCollageShoot();   // plugin missing, use the preview
    if (!files.length) return false;               // cancelled, leave the cell empty
    var url = await new Promise(function (res) {
        var r = new FileReader();
        r.onload = function () { res(r.result); };
        r.onerror = function () { res(null); };
        r.readAsDataURL(files[0]);
    });
    if (!url) return false;
    _lgCollage.shots.push(url);
    _lgCollage.idx = _lgCollage.shots.length;
    if (typeof triggerHaptic === 'function') triggerHaptic(12);
    _lgRenderCollageHud();
    var left = _lgCollage.layout.cells.length - _lgCollage.shots.length;
    if (typeof showToast === 'function') {
        showToast(left ? ('Shot ' + (_lgCollage.shots.length + 1) + ' of ' + _lgCollage.layout.cells.length) : 'Tap the tick when ready');
    }
    return true;
}

// Composite every shot into one portrait image, cropping each to fill its cell,
// then hand it to the story composer.
function lgFinishCollage() {
    if (!_lgCollage || !_lgCollage.shots.length) return;
    var W = 1080, H = 1920;
    var canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);

    var cells = _lgCollage.layout.cells;
    var loaded = 0;
    var imgs = [];
    cells.forEach(function (c, i) {
        var im = new Image();
        im.onload = im.onerror = function () {
            loaded++;
            if (loaded === cells.length) paint();
        };
        im.src = _lgCollage.shots[i] || '';
        imgs.push(im);
    });

    function paint() {
        cells.forEach(function (c, i) {
            var im = imgs[i];
            if (!im || !im.width) return;
            var dx = c[0] * W, dy = c[1] * H, dw = c[2] * W, dh = c[3] * H;
            // Cover: crop the source so the cell is filled without stretching.
            var sr = im.width / im.height, dr = dw / dh;
            var sw = im.width, sh = im.height, sx = 0, sy = 0;
            if (sr > dr) { sw = im.height * dr; sx = (im.width - sw) / 2; }
            else { sh = im.width / dr; sy = (im.height - sh) / 2; }
            ctx.drawImage(im, sx, sy, sw, sh, dx, dy, dw, dh);
            ctx.strokeStyle = '#000'; ctx.lineWidth = 6; ctx.strokeRect(dx, dy, dw, dh);
        });
        canvas.toBlob(function (blob) {
            if (!blob) return;
            var file = new File([blob], 'collage_' + Date.now() + '.jpg', { type: 'image/jpeg' });
            var layoutId = _lgCollage.layout.id;
            lgCancelCollage();
            if (typeof closeLgCam === 'function') { try { closeLgCam(); } catch (e) {} }
            // Carried through so a viewer can shoot the same layout from the pill.
            window._lgTemplate = { kind: 'collage', layout: layoutId };
            openLgComposer([file]);
            _lgShowTemplatePill();
        }, 'image/jpeg', 0.9);
    }
}

// The Drop Yours pill on the composer, so the story carries its template.
function _lgShowTemplatePill() {
    var comp = document.getElementById('lgComposer');
    if (!comp || document.getElementById('lgTemplatePill')) return;
    var pill = document.createElement('div');
    pill.id = 'lgTemplatePill';
    pill.style.cssText = 'position:absolute;left:50%;bottom:86px;transform:translateX(-50%);z-index:20;display:flex;align-items:center;gap:8px;background:#fff;border-radius:24px;padding:9px 18px;box-shadow:0 4px 18px rgba(0,0,0,0.35);';
    pill.innerHTML = '<i class="fa-solid fa-reply" style="color:#007AFF;font-size:13px;"></i>' +
                     '<span style="color:#007AFF;font-size:14px;font-weight:800;">Drop yours</span>';
    comp.appendChild(pill);
}

// Viewers tap the pill on a posted story. A collage template reopens the camera
// on that same layout. A photo template made by someone else has nothing to
// shoot, so it goes straight to the composer instead.
window.lgDropYoursFromStory = function (template) {
    var t = template || window._lgTemplate || null;
    if (!t) return;
    if (t.kind === 'photo') {
        // A photo template has nothing to shoot, so it goes to the existing story
        // editor, openStoryPostArea for a picture and openStoryVideoTrim for a
        // clip, rather than the camera composer.
        var inp = document.createElement('input');
        inp.type = 'file';
        inp.accept = 'image/*,video/*';
        inp.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;';
        inp.onchange = function () {
            var f = inp.files && inp.files[0];
            inp.remove();
            if (!f) return;
            var url = URL.createObjectURL(f);
            if (_lgIsVideo(f) && typeof openStoryVideoTrim === 'function') openStoryVideoTrim(f, url);
            else if (typeof openStoryPostArea === 'function') openStoryPostArea(f, url);
            else openLgComposer([f]);
        };
        document.body.appendChild(inp);
        inp.click();
        return;
    }
    if (typeof openLiquidGlassCamera === 'function') openLiquidGlassCamera();
    setTimeout(function () { if (t.layout) lgStartCollage(t.layout); }, 500);
};

// While a collage is in progress the shutter fills the next cell instead of
// recording, and once every cell is filled it finishes the collage. This wrap is
// last in the chain, so it runs before the native and web recorders.
(function () {
    var wrapped = false;
    function wrapShutterForCollage() {
        if (wrapped || typeof window.lgToggleRec !== 'function') return;
        wrapped = true;
        var prev = window.lgToggleRec;
        window.lgToggleRec = function () {
            if (_lgCollage) {
                if (_lgCollage.shots.length >= _lgCollage.layout.cells.length) { lgFinishCollage(); return; }
                // In the shell each cell is shot with the system camera, so the
                // collage is made of full resolution frames instead of frames
                // grabbed off the WebView preview.
                if (typeof tfIsNative === 'function' && tfIsNative() && typeof tfCapturePhoto === 'function') {
                    lgCollageShootNative();
                    return;
                }
                if (lgCollageShoot()) return;
            }
            return prev.apply(this, arguments);
        };
    }
    // Add the collage button to the camera each time it opens.
    function wrapCameraOpen() {
        if (typeof window.openLiquidGlassCamera !== 'function' || window.openLiquidGlassCamera._collageWrapped) return;
        var orig = window.openLiquidGlassCamera;
        window.openLiquidGlassCamera = function () {
            var r = orig.apply(this, arguments);
            setTimeout(function () {
                var page = document.getElementById('lgCameraPage');
                if (!page || document.getElementById('lgCollageBtn')) return;
                var rail = page.querySelector('div[style*="right:14px"]');
                if (!rail) return;
                var btn = document.createElement('button');
                btn.id = 'lgCollageBtn';
                btn.className = 'lg-btn';
                btn.title = 'Collage';
                btn.onclick = lgOpenCollagePicker;
                btn.innerHTML = '<i class="fa-solid fa-table-cells-large" style="font-size:16px;"></i>';
                rail.appendChild(btn);
            }, 60);
            return r;
        };
        window.openLiquidGlassCamera._collageWrapped = true;
    }
    function go() { wrapShutterForCollage(); wrapCameraOpen(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go);
    else go();
    setTimeout(go, 1400);
})();
