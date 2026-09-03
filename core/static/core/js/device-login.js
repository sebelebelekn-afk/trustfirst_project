// ==========================================================================
// SIGNING IN BY APPROVING IT ON YOUR PHONE
//
// Two screens that never appear on the same device:
//
//   the laptop  waits, showing one number and a code to scan
//   the phone   asks "is this you", and offers three numbers
//
// Only the number printed on the laptop lets the session through. The phone is
// never told which one that is, so the number genuinely has to be read off the
// other screen. That is what stops somebody who knows your username from simply
// asking over and over until you press yes.
//
// The laptop half is offered only on a laptop, because a phone approving its
// own sign-in proves nothing. The approval half runs everywhere, since the
// phone is the thing doing the approving.
// ==========================================================================

var TF_DL_POLL_MS = 2000;
var TF_DL_GIVE_UP_MS = 130000;      // a little past the server's two minutes

// ---------------------------------------------------------------- laptop --

function tfDlSupported() {
    return typeof tfIsDesktop === 'function' ? tfIsDesktop() : false;
}

// Offered after a wrong password, as a way in that does not need one.
//
// Added beside the existing error rather than replacing it, because the usual
// reason a password fails is a typo and the usual reason should stay the
// obvious thing to fix. Desktop only: a phone approving its own sign-in proves
// nothing, since it is the same device either way.
function tfDlOfferAfterFailure() {
    if (!tfDlSupported()) return;
    var step = document.getElementById('step-login-password');
    if (!step || document.getElementById('tfDlOffer')) return;

    var who = ((document.getElementById('login-user') || {}).value || '').trim();
    if (!who) return;

    var p = document.createElement('p');
    p.id = 'tfDlOffer';
    p.style.cssText = 'margin-top:10px;';
    p.innerHTML = '<span class="auth-x-forgot" style="color:#007AFF;cursor:pointer;">' +
        'Approve from your phone instead</span>';
    p.onclick = function () { tfDlStart(); };

    var anchor = document.getElementById('login-pass-usecode');
    if (anchor && anchor.parentNode === step) {
        step.insertBefore(p, anchor.nextSibling);
    } else {
        var spacer = step.querySelector('.auth-x-spacer');
        step.insertBefore(p, spacer || null);
    }
}

// showAuthError only raises a toast, so there is nothing to hang this off.
// Wrapping it is how the rest of this app extends behaviour, and the wrapper
// runs the original first so the message people already expect is unchanged.
if (typeof window !== 'undefined') {
    var _tfDlWrapError = function () {
        if (typeof showAuthError !== 'function' || window._tfDlWrapped) return;
        window._tfDlWrapped = true;
        var original = showAuthError;
        window.showAuthError = function (message, returnStep) {
            original(message, returnStep);
            if (/password|invalid|credential/i.test(String(message || ''))) {
                setTimeout(tfDlOfferAfterFailure, 150);
            }
        };
    };
    // feed.js may not have run yet when this file is parsed.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _tfDlWrapError);
    } else {
        _tfDlWrapError();
    }
}

async function tfDlStart() {
    var who = ((document.getElementById('login-user') || {}).value || '').trim();
    if (!who) return;

    tfDlShowWaiting(null, 'Asking your phone…');

    var data = null;
    try {
        var r = await fetch('/api/auth/device-request/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier: who })
        });
        data = await r.json().catch(function () { return null; });
        if (!r.ok || !data || !data.code) throw new Error('no attempt');
    } catch (e) {
        tfDlClose();
        if (typeof showToast === 'function') showToast('Could not reach the server');
        return;
    }

    tfDlShowWaiting(data.code, null);
    tfDlPoll(data.attempt, Date.now() + TF_DL_GIVE_UP_MS);
}

function tfDlShowWaiting(code, note) {
    var page = document.getElementById('tfDlWaiting');
    if (!page) {
        page = document.createElement('div');
        page.id = 'tfDlWaiting';
        page.style.cssText = 'position:fixed;inset:0;z-index:100001;background:var(--bg-primary,#fff);' +
            'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
            'padding:32px;text-align:center;';
        document.body.appendChild(page);
    }

    page.innerHTML =
        '<div style="max-width:420px;">' +
            '<div style="font-size:13px;color:#888;margin-bottom:6px;">TrustFirst</div>' +
            '<h2 style="font-size:26px;font-weight:800;margin:0 0 8px;color:var(--text-primary,#000);">' +
                'Check your other device</h2>' +
            '<p style="font-size:15px;color:#888;margin:0 0 26px;line-height:1.5;">' +
                (code
                    ? 'Open the notification on your phone, then tap <b style="color:var(--text-primary,#000);">' + code + '</b> to confirm it is you.'
                    : (note || 'One moment…')) +
            '</p>' +
            '<div id="tfDlQr" style="display:flex;justify-content:center;margin-bottom:22px;"></div>' +
            (code
                ? '<div style="font-size:54px;font-weight:800;letter-spacing:10px;' +
                  'color:var(--text-primary,#000);margin-bottom:24px;">' + code + '</div>'
                : '') +
            '<div style="display:flex;align-items:center;justify-content:center;gap:10px;color:#888;font-size:14px;">' +
                '<i class="fa-solid fa-circle-notch fa-spin"></i>' +
                '<span id="tfDlState">Waiting for approval</span>' +
            '</div>' +
            '<p style="font-size:12px;color:#aaa;margin:8px 0 0;">' +
                'It may take a few moments to reach your phone.</p>' +
            '<button onclick="tfDlClose()" style="margin-top:26px;padding:11px 22px;border-radius:11px;' +
                'border:none;background:none;color:#007AFF;font-size:14px;font-weight:700;cursor:pointer;">' +
                'Try another way</button>' +
        '</div>';

    // A code to scan, for reaching the app on a phone that is not already open.
    // Only drawn if the library actually loaded; a missing QR is not a reason
    // to fail, because the number alone is enough.
    if (code && typeof QRCode !== 'undefined') {
        try {
            new QRCode(document.getElementById('tfDlQr'), {
                text: location.origin + '/?approve=1',
                width: 148, height: 148,
                correctLevel: QRCode.CorrectLevel.M
            });
        } catch (e) { /* the number carries it */ }
    }
}

function tfDlClose() {
    clearTimeout(window._tfDlTimer);
    var p = document.getElementById('tfDlWaiting');
    if (p) p.remove();
}

async function tfDlPoll(attempt, deadline) {
    if (!document.getElementById('tfDlWaiting')) return;

    if (Date.now() > deadline) {
        tfDlSetState('That request expired. Try again.');
        return;
    }

    try {
        var r = await fetch('/api/auth/device-status/?attempt=' + encodeURIComponent(attempt));
        var d = await r.json().catch(function () { return {}; });

        if (d.status === 'approved' && d.grant) {
            tfDlSetState('Approved, signing you in…');
            return tfDlRedeem(d.grant);
        }
        if (d.status === 'denied') {
            tfDlSetState('That sign-in was refused on your phone.');
            return;
        }
        if (d.status === 'expired') {
            tfDlSetState('That request expired. Try again.');
            return;
        }
    } catch (e) { /* keep waiting; a dropped poll is not a failure */ }

    window._tfDlTimer = setTimeout(function () {
        tfDlPoll(attempt, deadline);
    }, TF_DL_POLL_MS);
}

function tfDlSetState(text) {
    var el = document.getElementById('tfDlState');
    if (el) el.textContent = text;
    var spin = document.querySelector('#tfDlWaiting .fa-circle-notch');
    if (spin && text.indexOf('signing') < 0) spin.style.display = 'none';
}

// Turn the grant into a real session.
//
// Supabase has no "approved elsewhere" grant, so the server minted a magic link
// token and this redeems it. Reloading afterwards rather than hand-rolling the
// post-login path means the app boots the way it always does: splash, restore,
// feed. One path in, so this cannot drift from the password one.
async function tfDlRedeem(grant) {
    try {
        var res = await sb.auth.verifyOtp({ token_hash: grant, type: 'magiclink' });
        if (res.error) throw res.error;
        location.replace(location.origin + '/');
    } catch (e) {
        console.warn('[DeviceLogin] redeem', e && e.message);
        tfDlSetState('Could not finish signing in. Try again.');
    }
}

// ----------------------------------------------------------------- phone --

// Is somebody trying to sign in as me right now?
async function tfDlCheckPending(force) {
    if (typeof tfMe === 'function' ? !tfMe() : !window.currentUser) return;
    if (document.getElementById('tfDlApprove')) return;

    try {
        var tok = await _tfAccessToken();
        if (!tok) return;
        var r = await fetch('/api/auth/device-pending/', {
            headers: { 'Authorization': 'Bearer ' + tok }
        });
        var d = await r.json().catch(function () { return {}; });
        if (d && d.pending) tfDlShowApprove(d.pending);
    } catch (e) { /* nothing to show */ }
}

function tfDlShowApprove(a) {
    var page = document.createElement('div');
    page.id = 'tfDlApprove';
    page.style.cssText = 'position:fixed;inset:0;z-index:100002;background:var(--bg-primary,#fff);' +
        'display:flex;flex-direction:column;overflow-y:auto;' +
        'padding:calc(env(safe-area-inset-top,0px) + 18px) 22px 30px;';

    var where = [a.city, a.country].filter(Boolean).join(', ') || 'an unknown place';
    var when = a.created_at ? new Date(a.created_at).toLocaleTimeString([], {
        hour: '2-digit', minute: '2-digit'
    }) : '';

    var buttons = (a.choices || []).map(function (n) {
        return '<button onclick="tfDlAnswer(\'' + a.id + '\',' + n + ')" ' +
            'style="flex:1;padding:26px 0;border-radius:14px;border:none;' +
            'background:var(--bg-secondary,#f0f2f5);color:var(--text-primary,#000);' +
            'font-size:30px;font-weight:800;cursor:pointer;font-family:inherit;">' + n + '</button>';
    }).join('');

    page.innerHTML =
        '<i class="fa-solid fa-xmark" onclick="tfDlAnswer(\'' + a.id + '\',null,true)" ' +
            'style="font-size:24px;color:var(--text-primary,#000);cursor:pointer;margin-bottom:18px;"></i>' +
        '<div style="font-size:14px;color:#888;margin-bottom:6px;">TrustFirst</div>' +
        '<h2 style="font-size:27px;font-weight:800;margin:0 0 10px;line-height:1.25;' +
            'color:var(--text-primary,#000);">Is this you trying to log in?</h2>' +
        '<p style="font-size:15px;color:#888;margin:0 0 20px;line-height:1.5;">' +
            'Check the details carefully and confirm only if this is you.</p>' +

        // What is actually being approved. Somebody who did not start this
        // should be able to tell at a glance, which is the point of showing it.
        '<div style="border:1px solid var(--border-color,#e6e8ea);border-radius:14px;' +
            'padding:16px;margin-bottom:22px;display:flex;gap:14px;align-items:center;">' +
            '<i class="fa-solid fa-laptop" style="font-size:24px;color:#8b95a5;"></i>' +
            '<div style="min-width:0;text-align:left;">' +
                '<div style="font-size:15px;font-weight:700;color:var(--text-primary,#000);">' +
                    'Login attempt from ' + escapeHtml(a.device_label || 'a device') + '</div>' +
                '<div style="font-size:14px;color:#888;">' + escapeHtml(where) +
                    (when ? ' · ' + escapeHtml(when) : '') + '</div>' +
            '</div>' +
        '</div>' +

        '<div style="display:flex;gap:10px;align-items:flex-start;margin-bottom:20px;">' +
            '<i class="fa-solid fa-shield-halved" style="color:#8b95a5;margin-top:2px;"></i>' +
            '<span style="font-size:14px;color:#888;line-height:1.5;text-align:left;">' +
                'If you are not sure, choose <b>No, it is not me</b>.</span>' +
        '</div>' +

        '<div style="font-size:15px;font-weight:700;color:var(--text-primary,#000);' +
            'margin-bottom:12px;text-align:left;">Tap the number shown on your other device</div>' +
        '<div style="display:flex;gap:10px;margin-bottom:24px;">' + buttons + '</div>' +

        '<button onclick="tfDlAnswer(\'' + a.id + '\',null,true)" ' +
            'style="width:100%;padding:16px;border-radius:999px;border:none;background:#007AFF;' +
            'color:#fff;font-size:16px;font-weight:700;cursor:pointer;font-family:inherit;">' +
            'No, it is not me</button>';

    document.body.appendChild(page);
}

async function tfDlAnswer(attempt, choice, refuse) {
    var page = document.getElementById('tfDlApprove');
    try {
        var tok = await _tfAccessToken();
        var r = await fetch('/api/auth/device-decide/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok },
            body: JSON.stringify({ attempt: attempt, choice: choice, refuse: !!refuse })
        });
        var d = await r.json().catch(function () { return {}; });
        if (page) page.remove();

        if (refuse) {
            if (typeof showToast === 'function') showToast('That sign-in was refused');
            return;
        }
        if (d && d.ok) {
            if (typeof showToast === 'function') showToast('Approved. You are signed in on the other device.');
            if (typeof triggerHaptic === 'function') triggerHaptic(40);
        } else {
            // A wrong number ends the attempt. Said plainly, because somebody
            // who guessed should understand nothing was let through.
            if (typeof showToast === 'function') {
                showToast(d && d.reason === 'wrong_number'
                    ? 'That was not the right number, so the sign-in was refused.'
                    : 'That sign-in is no longer waiting.');
            }
        }
    } catch (e) {
        if (page) page.remove();
        if (typeof showToast === 'function') showToast('Could not reach the server');
    }
}

// ------------------------------------------------------------------ boot --

if (typeof window !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
        // A pending approval is worth knowing about as soon as the app opens,
        // and again now and then while it is open, because the push may not
        // have arrived or may have been swiped away.
        setTimeout(tfDlCheckPending, 2500);
        setInterval(tfDlCheckPending, 20000);

        // Coming in from the QR or the notification.
        try {
            var p = new URLSearchParams(location.search);
            if (p.get('approve')) setTimeout(tfDlCheckPending, 1200);
        } catch (e) {}
    });

    // Back from the background is exactly when somebody has just tapped the
    // notification, so it is worth another look.
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) tfDlCheckPending();
    });
}
