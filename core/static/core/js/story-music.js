// ============================================================
// STORY MUSIC EDITOR — Apple-Music-style clip editor.
// Flow: music button -> pick song -> the button becomes the album
// cover -> tap it -> editor (Trash top-left, Album cover top-center,
// Done top-right; style row; waveform scrubber 0:00 -> end; duration
// wheel). Tapping the album cover opens the song picker to change song.
// Loaded after feed.js (uses showToast, triggerHaptic, openThoughtMusicPicker).
// ============================================================
(function () {
  var DUR_MIN = 10;
  function durMax() {
    // Story max 45s, thoughts max 30s (decided by which surface is active)
    return window._spMusicForThought ? 30 : 45;
  }
  function track() { return window._spStoryMusicInfo || null; }

  // Called after a song is picked for a story (wired from selectRealMusicTrack).
  window.storyOnSongChosen = function (t) {
    var prev = window._spStoryMusicInfo || {};
    window._spStoryMusicInfo = Object.assign({}, prev, t, {
      start: typeof prev.start === 'number' ? prev.start : 0,
      duration: typeof prev.duration === 'number' ? prev.duration : 15
    });
    setMusicButtonToAlbum();
    window.storyOpenMusicEditor();
  };

  function setMusicButtonToAlbum() {
    var t = track();
    var btn = document.getElementById('spBtnMusic');
    if (!btn) return;
    if (t && t.artUrl) {
      btn.innerHTML = '<img src="' + t.artUrl + '" alt="" style="width:100%;height:100%;border-radius:50%;object-fit:cover;display:block;">';
    } else {
      btn.innerHTML = '<i class="fa-solid fa-music"></i>';
    }
    btn.style.padding = '0';
    btn.style.overflow = 'hidden';
    btn.style.background = 'rgba(0,0,0,0.55)';
    btn.onclick = function () { window.storyOpenMusicEditor(); };
  }
  window.setStoryMusicButtonToAlbum = setMusicButtonToAlbum;

  // Re-open the song picker to change the song
  window.storyChangeSong = function () {
    window._spMusicModalActive = true;
    var ed = document.getElementById('storyMusicEditor'); if (ed) ed.remove();
    if (typeof openThoughtMusicPicker === 'function') openThoughtMusicPicker();
  };

  // Remove the music entirely
  window.storyRemoveMusic = function () {
    window._spStoryMusicInfo = null;
    window._spMusicOnly = false;
    stopPreview();
    var ed = document.getElementById('storyMusicEditor'); if (ed) ed.remove();
    var btn = document.getElementById('spBtnMusic');
    if (btn) { btn.innerHTML = '<i class="fa-solid fa-music"></i>'; btn.onclick = function () { window._spMusicModalActive = true; if (typeof openThoughtMusicPicker === 'function') openThoughtMusicPicker(); }; }
    if (typeof triggerHaptic === 'function') triggerHaptic(10);
  };

  var _audio = null;
  function stopPreview() { try { if (_audio) { _audio.pause(); _audio.src = ''; } } catch (e) {} _audio = null; }

  window.storyOpenMusicEditor = function () {
    var t = track();
    if (!t) { window._spMusicModalActive = true; if (typeof openThoughtMusicPicker === 'function') openThoughtMusicPicker(); return; }
    var existing = document.getElementById('storyMusicEditor'); if (existing) existing.remove();

    var sheet = document.createElement('div');
    sheet.id = 'storyMusicEditor';
    sheet.style.cssText = 'position:absolute;inset:0;z-index:9850;display:flex;flex-direction:column;background:rgba(8,8,10,0.86);backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);animation:fadeUp 0.28s ease;';

    // 40 deterministic waveform bars
    var bars = '';
    for (var i = 0; i < 44; i++) {
      var h = 14 + Math.round(Math.abs(Math.sin(i * 1.7) * 26) + (i % 5) * 3);
      bars += '<div style="flex:1;min-width:2px;height:' + h + 'px;border-radius:2px;background:rgba(255,255,255,0.35);"></div>';
    }

    var styleRow = ['pill', 'card', 'minimal'].map(function (s) {
      var sel = (t.style || 'pill') === s;
      var icon = s === 'pill' ? 'fa-record-vinyl' : (s === 'card' ? 'fa-id-card' : 'fa-align-left');
      return '<div onclick="storySetMusicStyle(\'' + s + '\')" data-mstyle="' + s + '" style="width:48px;height:48px;border-radius:14px;display:flex;align-items:center;justify-content:center;cursor:pointer;background:' + (sel ? 'rgba(0,122,255,0.85)' : 'rgba(255,255,255,0.12)') + ';border:1px solid rgba(255,255,255,0.15);"><i class="fa-solid ' + icon + '" style="color:white;font-size:18px;"></i></div>';
    }).join('');

    sheet.innerHTML =
      // Top bar: trash (left) / album cover (center) / Done (right)
      '<div style="display:flex;align-items:center;justify-content:space-between;padding:max(50px,env(safe-area-inset-top,50px)) 20px 10px;">' +
        '<button onclick="storyRemoveMusic()" title="Remove music" style="width:40px;height:40px;border-radius:50%;background:rgba(255,255,255,0.12);border:none;color:#FF6B6B;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;"><i class="fa-solid fa-trash"></i></button>' +
        '<div onclick="storyChangeSong()" title="Change song" style="width:64px;height:64px;border-radius:50%;overflow:hidden;cursor:pointer;border:2px solid rgba(255,255,255,0.5);box-shadow:0 6px 20px rgba(0,0,0,0.5);">' +
          (t.artUrl ? '<img src="' + t.artUrl + '" style="width:100%;height:100%;object-fit:cover;">' : '<div style="width:100%;height:100%;background:#222;display:flex;align-items:center;justify-content:center;"><i class="fa-solid fa-music" style="color:#fff;"></i></div>') +
        '</div>' +
        '<button onclick="storyApplyMusicEdit()" style="background:#007AFF;border:none;border-radius:50px;padding:9px 22px;color:white;font-size:15px;font-weight:700;cursor:pointer;">Done</button>' +
      '</div>' +

      // Track name + change hint
      '<div style="text-align:center;margin-top:4px;">' +
        '<div style="color:white;font-size:16px;font-weight:700;">' + (t.name || 'Music') + '</div>' +
        '<div style="color:rgba(255,255,255,0.55);font-size:12px;margin-top:2px;">' + (t.artist || '') + ' · tap cover to change</div>' +
      '</div>' +

      '<div style="flex:1;"></div>' +

      // Style row
      '<div style="display:flex;justify-content:center;gap:14px;margin-bottom:18px;">' + styleRow + '</div>' +

      // Waveform scrubber with a draggable selection window
      '<div style="padding:0 18px 6px;">' +
        '<div id="smTrack" style="position:relative;height:64px;border-radius:14px;background:rgba(255,255,255,0.06);overflow:hidden;display:flex;align-items:center;gap:2px;padding:0 8px;">' +
          bars +
          '<div id="smWindow" style="position:absolute;top:0;bottom:0;left:0%;width:35%;border:2.5px solid #FF9500;border-radius:12px;background:rgba(255,149,0,0.14);cursor:grab;touch-action:none;box-shadow:0 0 0 100vmax rgba(0,0,0,0.0);"></div>' +
        '</div>' +
      '</div>' +

      // Play/pause + current time + duration chip (opens wheel)
      '<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 22px max(26px,env(safe-area-inset-bottom,26px));">' +
        '<button id="smPlayBtn" onclick="storyToggleMusicPreview(this)" style="width:46px;height:46px;border-radius:50%;background:rgba(255,255,255,0.16);border:none;color:white;font-size:16px;cursor:pointer;"><i class="fa-solid fa-pause"></i></button>' +
        '<div id="smStartLabel" style="color:rgba(255,255,255,0.7);font-size:13px;font-weight:600;">0:00</div>' +
        '<button onclick="storyOpenDurationWheel()" style="background:rgba(255,255,255,0.16);border:none;border-radius:50px;padding:10px 18px;color:white;font-size:14px;font-weight:700;cursor:pointer;"><span id="smDurChip">' + (t.duration || 15) + 's</span> <i class="fa-solid fa-chevron-down" style="font-size:10px;opacity:0.7;margin-left:4px;"></i></button>' +
      '</div>';

    var host = document.getElementById('storyPostScreen') || document.getElementById('app') || document.body;
    host.appendChild(sheet);

    // Audio + scrubber wiring
    stopPreview();
    if (t.previewUrl) { _audio = new Audio(t.previewUrl); _audio.loop = true; _audio.volume = 0.85; }
    var win = document.getElementById('smWindow');
    var trackEl = document.getElementById('smTrack');
    var songDur = 30; // default until metadata loads

    function applyWindowWidth() {
      var d = (track() && track().duration) || 15;
      var pct = Math.max(8, Math.min(100, (d / songDur) * 100));
      win.style.width = pct + '%';
      // keep within bounds
      var left = parseFloat(win.style.left) || 0;
      win.style.left = Math.max(0, Math.min(100 - pct, left)) + '%';
    }
    function startFromLeft() {
      var pct = parseFloat(win.style.left) || 0;
      return (pct / 100) * songDur;
    }
    function syncStartLabel() {
      var s = startFromLeft();
      var m = Math.floor(s / 60), sec = Math.floor(s % 60);
      var lbl = document.getElementById('smStartLabel');
      if (lbl) lbl.textContent = m + ':' + (sec < 10 ? '0' : '') + sec;
      if (track()) track().start = s;
    }

    if (_audio) {
      _audio.addEventListener('loadedmetadata', function () {
        if (_audio.duration && isFinite(_audio.duration)) songDur = _audio.duration;
        applyWindowWidth(); syncStartLabel();
      });
      // position to current start, play
      _audio.addEventListener('canplay', function () {
        try { _audio.currentTime = (track() && track().start) || 0; } catch (e) {}
      }, { once: true });
      _audio.play().catch(function () {});
    }
    applyWindowWidth();
    // restore left from stored start
    if (track() && track().start) { win.style.left = Math.min(90, (track().start / songDur) * 100) + '%'; }
    syncStartLabel();

    // Drag the selection window to scrub the start point
    var dragging = false, startX = 0, startLeft = 0;
    win.addEventListener('pointerdown', function (e) {
      dragging = true; startX = e.clientX; startLeft = parseFloat(win.style.left) || 0;
      win.style.cursor = 'grabbing'; win.setPointerCapture(e.pointerId);
    });
    win.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var tw = trackEl.getBoundingClientRect().width; if (!tw) return;
      var dx = ((e.clientX - startX) / tw) * 100;
      var w = parseFloat(win.style.width) || 35;
      var nl = Math.max(0, Math.min(100 - w, startLeft + dx));
      win.style.left = nl + '%';
      syncStartLabel();
      if (_audio && _audio.duration) { try { _audio.currentTime = startFromLeft(); } catch (e2) {} }
    });
    win.addEventListener('pointerup', function () { dragging = false; win.style.cursor = 'grab'; });

    sheet._applyWindowWidth = applyWindowWidth;
    if (typeof triggerHaptic === 'function') triggerHaptic(10);
  };

  window.storyToggleMusicPreview = function (btn) {
    if (!_audio) return;
    if (_audio.paused) { _audio.play().catch(function () {}); btn.innerHTML = '<i class="fa-solid fa-pause"></i>'; }
    else { _audio.pause(); btn.innerHTML = '<i class="fa-solid fa-play"></i>'; }
  };

  window.storySetMusicStyle = function (s) {
    if (track()) track().style = s;
    document.querySelectorAll('#storyMusicEditor [data-mstyle]').forEach(function (el) {
      var on = el.getAttribute('data-mstyle') === s;
      el.style.background = on ? 'rgba(0,122,255,0.85)' : 'rgba(255,255,255,0.12)';
    });
    if (typeof triggerHaptic === 'function') triggerHaptic(6);
  };

  window.storyApplyMusicEdit = function () {
    stopPreview();
    var ed = document.getElementById('storyMusicEditor'); if (ed) ed.remove();
    setMusicButtonToAlbum();
    if (typeof showToast === 'function') showToast('Music added');
    if (typeof triggerHaptic === 'function') triggerHaptic(15);
  };

  // ---- Duration wheel (matches the "Choose clip duration" screenshot) ----
  window.storyOpenDurationWheel = function () {
    var existing = document.getElementById('durWheelModal'); if (existing) existing.remove();
    var cur = (track() && track().duration) || 15;
    var max = durMax();
    var modal = document.createElement('div');
    modal.id = 'durWheelModal';
    modal.style.cssText = 'position:absolute;inset:0;z-index:9900;display:flex;align-items:flex-end;justify-content:center;background:rgba(0,0,0,0.5);';
    var ITEM = 54;
    var items = '';
    for (var v = DUR_MIN; v <= max; v++) {
      items += '<div data-val="' + v + '" style="height:' + ITEM + 'px;display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--text-primary,#000);scroll-snap-align:center;">' + v + ' seconds</div>';
    }
    modal.innerHTML =
      '<div style="width:100%;max-width:500px;background:var(--bg-primary,#fff);border-radius:22px 22px 0 0;padding:18px 0 max(24px,env(safe-area-inset-bottom,24px));">' +
        '<div style="text-align:center;font-size:17px;font-weight:800;color:var(--text-primary,#000);margin-bottom:10px;">Choose clip duration</div>' +
        '<div style="position:relative;height:' + (ITEM * 3) + 'px;">' +
          '<div style="position:absolute;top:' + ITEM + 'px;left:16px;right:16px;height:' + ITEM + 'px;border-radius:14px;background:var(--bg-secondary,#f2f2f7);pointer-events:none;"></div>' +
          '<div id="durWheelScroll" style="position:relative;height:100%;overflow-y:auto;scroll-snap-type:y mandatory;padding:' + ITEM + 'px 0;scrollbar-width:none;">' + items + '</div>' +
        '</div>' +
        '<button onclick="storyConfirmDuration()" style="display:block;margin:10px auto 0;background:none;border:none;color:#007AFF;font-size:17px;font-weight:700;cursor:pointer;">Done</button>' +
      '</div>';
    var host = document.getElementById('storyPostScreen') || document.getElementById('app') || document.body;
    host.appendChild(modal);
    var scroll = document.getElementById('durWheelScroll');
    // center the current value
    setTimeout(function () { scroll.scrollTop = (cur - DUR_MIN) * ITEM; }, 0);
    scroll._itemHeight = ITEM; scroll._min = DUR_MIN; scroll._max = max;
  };

  window.storyConfirmDuration = function () {
    var scroll = document.getElementById('durWheelScroll');
    if (scroll) {
      var ITEM = scroll._itemHeight || 54;
      var val = scroll._min + Math.round(scroll.scrollTop / ITEM);
      val = Math.max(scroll._min, Math.min(scroll._max, val));
      if (track()) track().duration = val;
      var chip = document.getElementById('smDurChip'); if (chip) chip.textContent = val + 's';
      var ed = document.getElementById('storyMusicEditor');
      if (ed && ed._applyWindowWidth) ed._applyWindowWidth();
    }
    var m = document.getElementById('durWheelModal'); if (m) m.remove();
    if (typeof triggerHaptic === 'function') triggerHaptic(10);
  };
})();
