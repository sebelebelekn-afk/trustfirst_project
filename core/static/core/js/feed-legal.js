// ============================================================
// TrustFirst legal — where the documents live, and how they open.
// Loaded after feed.js (uses escapeHtml, showToast, openLinkInApp).
//
// The privacy and terms text used to sit in this file as template literals.
// They are served as real pages now — /privacy/, /terms/, /cookies/,
// /accessibility/, /help/ — and every entry point loads those URLs, so the
// copies were removed rather than left to rot. Two versions of a legal document
// is one version nobody updates, and the app was still showing the stale one on
// the sign-up screen after the pages went live.
// ============================================================


var _tfInfoHTML = `<h2 style="font-size:20px;font-weight:900;margin:0 0 16px;">Why this information is important</h2><p style="font-size:14px;color:var(--text-secondary,#555);line-height:1.75;margin-bottom:20px;">TrustFirst shows certain account information to help people understand who they are interacting with. This transparency builds trust and helps keep the platform safe.</p><div style="background:var(--card-bg,#fff);border-radius:16px;padding:18px 20px;margin-bottom:14px;border:0.5px solid var(--border-color,rgba(0,0,0,0.06));"><div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:14px;"><div style="width:32px;height:32px;border-radius:9px;background:rgba(0,122,255,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="fa-regular fa-calendar" style="color:#007AFF;font-size:14px;"></i></div><div><b style="font-size:15px;color:var(--text-primary,#000);display:block;margin-bottom:4px;">Date Joined</b><p style="font-size:13px;color:var(--text-secondary,#555);line-height:1.6;margin:0;">Knowing when an account was created helps people identify recently-created accounts, which may indicate inauthentic activity.</p></div></div><div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:14px;"><div style="width:32px;height:32px;border-radius:9px;background:rgba(52,199,89,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="fa-solid fa-earth-africa" style="color:#34C759;font-size:14px;"></i></div><div><b style="font-size:15px;color:var(--text-primary,#000);display:block;margin-bottom:4px;">Account Based In</b><p style="font-size:13px;color:var(--text-secondary,#555);line-height:1.6;margin:0;">This refers to the country associated with your account at registration. It helps users make informed decisions about who they interact with.</p></div></div><div style="display:flex;gap:12px;align-items:flex-start;"><div style="width:32px;height:32px;border-radius:9px;background:rgba(255,149,0,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0;"><i class="fa-solid fa-clock-rotate-left" style="color:#FF9500;font-size:14px;"></i></div><div><b style="font-size:15px;color:var(--text-primary,#000);display:block;margin-bottom:4px;">Former Usernames</b><p style="font-size:13px;color:var(--text-secondary,#555);line-height:1.6;margin:0;">This helps prevent impersonation and keeps a transparent history of identity changes on the platform.</p></div></div></div>`;

// Every legal document lives at a real URL now. Anything listed here is opened
// as a web page — the same address anybody else would visit — rather than as a
// copy of the words kept inside the app.
//
// This map is the single place that decides. Both the Settings rows and the
// sign-up links go through it, which is what stopped them drifting apart: the
// sign-up screen had its own copy of the text and kept showing the old one after
// the pages went live.
var TF_LEGAL_URLS = {
    privacy: '/privacy/',
    terms: '/terms/',
    cookies: '/cookies/',
    accessibility: '/accessibility/',
    help: '/help/'
};

function tfLegalUrl(type) {
    var path = TF_LEGAL_URLS[type];
    return path ? (location.origin + path) : null;
}

function openInAppBrowser(title, type) {
    var url = tfLegalUrl(type);
    if (url) { openLinkInApp(url); return; }

    var existing = document.getElementById('inAppBrowserOverlay');
    if (existing) existing.remove();
    var overlay = document.createElement('div');
    overlay.id = 'inAppBrowserOverlay';
    overlay.style.cssText = 'position:absolute;inset:0;z-index:7400;display:flex;flex-direction:column;background:var(--bg-primary,#fff);animation:slideUpOverlay 0.3s cubic-bezier(0.32,0.72,0,1);';
    // Only 'info' reaches here now — everything else is a URL above. This used
    // to also name _tfPrivacyHTML and _tfTermsHTML, which no longer exist, and
    // an object literal is built eagerly, so it would have thrown on the way
    // past rather than falling through.
    var contentMap = { info: _tfInfoHTML };
    var html = contentMap[type] || '<p style="padding:20px;color:#888;">Content not found.</p>';
    overlay.innerHTML =
        '<div style="display:flex;align-items:center;justify-content:space-between;padding:max(52px,env(safe-area-inset-top,52px)) 20px 14px;background:var(--bg-primary,#fff);border-bottom:0.5px solid var(--border-color,#e0e0e0);flex-shrink:0;position:sticky;top:0;z-index:2;">' +
            '<button onclick="document.getElementById(\'inAppBrowserOverlay\').remove()" style="width:36px;height:36px;border-radius:50%;background:var(--bg-secondary,#f0f0f0);border:none;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;">' +
                '<i class="fa-solid fa-chevron-left" style="color:var(--text-primary,#000);font-size:14px;"></i></button>' +
            '<b style="font-size:16px;color:var(--text-primary,#000);text-overflow:ellipsis;overflow:hidden;white-space:nowrap;max-width:200px;">' + escapeHtml(title) + '</b>' +
            '<button onclick="shareInAppPage(\'' + type + '\')" style="width:36px;height:36px;border-radius:50%;background:var(--bg-secondary,#f0f0f0);border:none;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;">' +
                '<i class="fa-solid fa-share-nodes" style="color:#007AFF;font-size:14px;"></i></button>' +
        '</div>' +
        '<div style="flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:28px 20px max(60px,calc(env(safe-area-inset-bottom,0px)+60px));background:var(--bg-primary,#fff);">' +
            html +
        '</div>';
    document.getElementById('app').appendChild(overlay);
}

function shareInAppPage(type) {
    // These were hardcoded to trustfirst.app/privacy and /terms, neither of
    // which existed, so Share handed people a 404. It shares the page's real
    // address now, on whatever host the app is actually running on.
    var url = tfLegalUrl(type) || location.origin;
    if (navigator.share) {
        navigator.share({ title: 'TrustFirst', url: url }).catch(function(){});
    } else {
        try { navigator.clipboard.writeText(url); showToast('Link copied'); } catch(e) {}
    }
}
