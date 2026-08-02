// ============================================================
// GET VERIFIED — badge applications (blue=Didit ID, red=gov,
// silver=business, gold=creator). Green is set at registration.
// Loaded after feed.js (uses showToast, sb, currentUser globals).
// ============================================================
// Settings entry — GOLD creator verification ONLY. The other badges (blue ID,
// red gov, silver business, green child) get their requirements at registration,
// and the white kids-creator badge is applied for in Family Center.
function openGetVerified() {
    var followers = (currentUser && currentUser.follower_count) || 0;
    if (followers < 500000) { showToast('Gold verification unlocks at 500,000 followers'); return; }
    openBadgeForm('gold');
}

window.applyForBadge = function(type) {
    // Blue is reviewed by a human. The paid KYC provider (startIdVerification) stays
    // available for when it is funded, but manual review is what runs today.
    if (type === 'blue' && window.TF_USE_DIDIT_KYC) return startIdVerification();
    if (type === 'gold') {
        var followers = (currentUser && currentUser.follower_count) || 0;
        if (followers < 500000) { showToast('Gold verification unlocks at 500,000 followers'); return; }
    }
    return openBadgeForm(type);
};

// Show the settings "Gold Verification" row only once the account hits 500k followers.
(function() {
    var _origOpenSettings = window.openSettings;
    if (typeof _origOpenSettings === 'function') {
        window.openSettings = function() {
            _origOpenSettings.apply(this, arguments);
            var row = document.getElementById('settingsGoldVerifyRow');
            var followers = (currentUser && currentUser.follower_count) || 0;
            if (row) row.style.display = (followers >= 500000) ? 'flex' : 'none';
        };
    }
})();

async function startIdVerification() {
    showToast('Starting ID verification...');
    try {
        var token = '';
        try { var s = await sb.auth.getSession(); token = (s.data && s.data.session) ? s.data.session.access_token : ''; } catch (e) {}
        if (!token) { showToast('Please sign in again'); return; }
        var resp = await fetch('/api/didit/create-verification/', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: '{}'
        });
        var data = await resp.json();
        if (resp.ok && data.session_url) {
            try { await sb.from('verification_applications').insert({ user_id: currentUser.id, badge_type: 'blue', provider: 'didit', provider_ref: data.session_id, status: 'pending' }); } catch (e) {}
            window.open(data.session_url, '_blank');
        } else {
            // Don't leak server config hints (e.g. "set DIDIT_WORKFLOW_ID") to users.
            var msg = /not configured|misconfigured/i.test(data.error || '')
                ? 'Identity verification is being set up — please check back soon.'
                : (data.error || 'Could not start verification');
            showToast(msg);
        }
    } catch (e) { showToast('Verification error'); }
}

function openBadgeForm(type) {
    var cfg = {
        blue: { title: 'Identity verification', fields: [
            { id: 'legal_name', label: 'Full name (as it appears on your ID)', type: 'text', ph: 'e.g. Naledi Mokoena' },
            { id: 'issuing_country', label: 'Country that issued the document', type: 'text', ph: 'e.g. South Africa' }
        ], doc: 'Photo of your government ID, with the ID number covered', docRequired: true,
           notice: '<b style="color:#FF9500;">Cover your ID number before you take the photo.</b> A reviewer only needs your photo, your name and the document type, never the number.<br><br>' +
                   'Your document is uploaded to private storage that only a reviewer can open, and it is <b>deleted the moment your application is decided</b>. Anything left unreviewed is deleted automatically after 7 days.<br><br>' +
                   'We keep the result of the check, never your ID.' },
        red: { title: 'Government verification', fields: [
            { id: 'gov_email', label: 'Official government email', type: 'email', ph: 'name@gov.example' },
            { id: 'department', label: 'Department / agency', type: 'text', ph: 'e.g. Police, Health, Office of the President' }
        ], doc: 'Stamped department letterhead (PDF or image)', docRequired: true },
        silver: { title: 'Business verification', fields: [
            { id: 'legal_entity_name', label: 'Legal entity name', type: 'text', ph: 'Registered company name' },
            { id: 'corp_number', label: 'Official company number', type: 'text', ph: 'Registration number' },
            { id: 'company_email', label: 'Company email', type: 'email', ph: 'you@company.com' }
        ], doc: 'Utility bill or tax document (optional)', docRequired: false },
        gold: { title: 'Public figure verification', fields: [
            { id: 'article1', label: 'Press article URL 1', type: 'url', ph: 'https://...' },
            { id: 'article2', label: 'Press article URL 2', type: 'url', ph: 'https://...' },
            { id: 'article3', label: 'Press article URL 3', type: 'url', ph: 'https://...' }
        ], doc: null, docRequired: false }
    }[type];
    if (!cfg) return;
    var existing = document.getElementById('badgeFormOverlay'); if (existing) existing.remove();
    var ov = document.createElement('div');
    ov.id = 'badgeFormOverlay';
    ov.className = 'white-overlay';
    ov.style.cssText = 'position:absolute;inset:0;z-index:9750;display:flex;flex-direction:column;background:var(--bg-primary,#fff);animation:slideUpOverlay 0.3s cubic-bezier(0.32,0.72,0,1);overflow-y:auto;';
    var fieldsHtml = cfg.fields.map(function(f) {
        return '<label style="display:block;font-size:12px;font-weight:700;color:#888;margin:14px 4px 6px;">' + f.label + '</label>' +
            '<input id="bf_' + f.id + '" type="' + f.type + '" placeholder="' + f.ph + '" style="width:100%;padding:13px 16px;border-radius:12px;border:1px solid var(--border-color,#e5e5e5);background:var(--input-bg,#f7f7f7);font-size:15px;color:var(--text-primary,#000);outline:none;box-sizing:border-box;">';
    }).join('');
    var docHtml = cfg.doc ? '<label style="display:block;font-size:12px;font-weight:700;color:#888;margin:16px 4px 6px;">' + cfg.doc + '</label><input id="bf_doc" type="file" accept="image/*,application/pdf" style="width:100%;font-size:13px;color:#888;">' : '';
    var noticeHtml = cfg.notice
        ? '<div style="background:rgba(255,149,0,0.08);border:1px solid rgba(255,149,0,0.25);border-radius:14px;padding:14px;margin-bottom:6px;font-size:13px;line-height:1.6;color:var(--text-primary,#000);">' +
              '<i class="fa-solid fa-shield-halved" style="color:#FF9500;margin-right:6px;"></i>' + cfg.notice +
          '</div>'
        : '';
    ov.innerHTML =
        '<div class="header-container" style="flex-shrink:0;"><div class="liquid-glass-btn" onclick="document.getElementById(\'badgeFormOverlay\').remove()" style="cursor:pointer;"><i class="fa-solid fa-chevron-left"></i></div><b>' + cfg.title + '</b></div>' +
        '<div style="padding:18px 18px 40px;">' + noticeHtml + fieldsHtml + docHtml +
            '<button onclick="submitBadgeApplication(\'' + type + '\',' + cfg.docRequired + ')" style="width:100%;padding:15px;border-radius:14px;border:none;background:#007AFF;color:#fff;font-size:16px;font-weight:700;cursor:pointer;margin-top:22px;">Submit for review</button>' +
            '<p style="font-size:11px;color:#aaa;text-align:center;margin-top:12px;line-height:1.5;">Our team reviews applications within a few days. You will be notified of the result.</p>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(ov);
}

window.submitBadgeApplication = async function(type, docRequired) {
    if (!window.sb || !currentUser) { showToast('Please sign in'); return; }
    var data = {};
    document.querySelectorAll('#badgeFormOverlay input[id^="bf_"]').forEach(function(inp) {
        if (inp.type !== 'file') data[inp.id.replace('bf_', '')] = (inp.value || '').trim();
    });
    var empties = Object.keys(data).filter(function(k) { return !data[k]; });
    if (empties.length) { showToast('Please fill all fields'); return; }

    var fileInp = document.getElementById('bf_doc');
    var hasFile = fileInp && fileInp.files && fileInp.files[0];
    if (docRequired && !hasFile) { showToast('Please attach the required document'); return; }

    showToast('Submitting...');
    var documents = [];
    if (hasFile) {
        try {
            var file = fileInp.files[0];
            var ext = (file.name.split('.').pop() || 'pdf').toLowerCase();
            var path = currentUser.id + '/' + type + '_' + Date.now() + '.' + ext;
            var up = await sb.storage.from('verification_docs').upload(path, file, { upsert: true });
            if (up.error) { showToast('Document upload failed: ' + up.error.message); return; }
            documents.push(up.data.path); // private bucket: store path; admin reads via signed URL
        } catch (e) { showToast('Upload error'); return; }
    }
    try {
        var res = await sb.from('verification_applications').insert({
            user_id: currentUser.id, badge_type: type, status: 'pending',
            data: data, documents: documents,
            provider: (type === 'silver' ? 'opencorporates' : null)
        });
        if (res.error) { showToast('Could not submit: ' + res.error.message); return; }
        var bf = document.getElementById('badgeFormOverlay'); if (bf) bf.remove();
        var gv = document.getElementById('getVerifiedOverlay'); if (gv) gv.remove();
        showToast('Application submitted for review');
    } catch (e) { showToast('Submit failed'); }
};

// ============================================================
// TRANSLATE CLIP TO ENGLISH (ElevenLabs dubbing, server-side)
// ============================================================
window.translateClipToEnglish = async function(videoUrl) {
    if (!videoUrl) { showToast('No video to translate'); return; }
    var menu = document.getElementById('reelLongPressMenu'); if (menu) menu.remove();
    showToast('Translating to English... this can take a minute');
    try {
        var token = '';
        try { var s = await sb.auth.getSession(); token = (s.data && s.data.session) ? s.data.session.access_token : ''; } catch (e) {}
        if (!token) { showToast('Please sign in'); return; }
        var startRes = await fetch('/api/translate/start/', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_url: videoUrl, target_lang: 'en' })
        });
        var startData = await startRes.json();
        if (!startRes.ok || !startData.dubbing_id) { showToast(startData.error || 'Translation could not start'); return; }
        var dubbingId = startData.dubbing_id;
        var tries = 0;
        var poll = setInterval(async function() {
            tries++;
            if (tries > 75) { clearInterval(poll); showToast('Translation timed out'); return; }
            try {
                var st = await fetch('/api/translate/status/?id=' + encodeURIComponent(dubbingId), { headers: { 'Authorization': 'Bearer ' + token } });
                var sd = await st.json();
                if (sd.status === 'dubbed' && sd.result_url) {
                    clearInterval(poll);
                    showToast('Translation ready');
                    var rv = document.getElementById('reelVideo');
                    if (rv) { rv.src = sd.result_url; rv.play().catch(function() {}); }
                } else if (sd.status === 'failed') {
                    clearInterval(poll); showToast('Translation failed');
                }
            } catch (e) {}
        }, 4000);
    } catch (e) { showToast('Translation error'); }
};

// ============================================================
// FAMILY CENTER — apply to create a censored kids-content account.
// Only verified (blue badge) adults; on approval -> white badge, posts to kids feed.
// ============================================================
window.openKidsCreatorApplication = function() {
    if (!currentUser) { showToast('Please sign in'); return; }
    var tier = currentUser.badge_tier || '';
    if (tier !== 'verify-blue' && !currentUser.verified) {
        showToast('Only verified (blue badge) accounts can apply to create for kids');
        return;
    }
    var existing = document.getElementById('kidsCreatorApp'); if (existing) existing.remove();
    var ov = document.createElement('div');
    ov.id = 'kidsCreatorApp';
    ov.className = 'white-overlay';
    ov.style.cssText = 'position:absolute;inset:0;z-index:9760;display:flex;flex-direction:column;background:var(--bg-primary,#fff);animation:slideUpOverlay 0.3s cubic-bezier(0.32,0.72,0,1);overflow-y:auto;';
    ov.innerHTML =
        '<div class="header-container" style="flex-shrink:0;"><div class="liquid-glass-btn" onclick="document.getElementById(\'kidsCreatorApp\').remove()" style="cursor:pointer;"><i class="fa-solid fa-chevron-left"></i></div><b>Create for Kids</b></div>' +
        '<div style="padding:18px 18px 40px;">' +
            '<div style="background:rgba(52,199,89,0.08);border:1px solid rgba(52,199,89,0.2);border-radius:14px;padding:14px;margin-bottom:18px;font-size:13px;color:#34C759;line-height:1.5;"><i class="fa-solid fa-shield-halved"></i> Approved kids creators get a white badge. Everything you post goes to the Kids feed and is <b>heavily moderated for child safety</b>.</div>' +
            '<label style="display:block;font-size:12px;font-weight:700;color:#888;margin:0 4px 6px;">Why do you want to create for kids?</label>' +
            '<textarea id="kca_reason" rows="3" style="width:100%;padding:13px 16px;border-radius:12px;border:1px solid var(--border-color,#e5e5e5);background:var(--input-bg,#f7f7f7);font-size:15px;color:var(--text-primary,#000);outline:none;box-sizing:border-box;resize:none;font-family:inherit;"></textarea>' +
            '<label style="display:block;font-size:12px;font-weight:700;color:#888;margin:14px 4px 6px;">What kind of content will you create?</label>' +
            '<textarea id="kca_content" rows="3" style="width:100%;padding:13px 16px;border-radius:12px;border:1px solid var(--border-color,#e5e5e5);background:var(--input-bg,#f7f7f7);font-size:15px;color:var(--text-primary,#000);outline:none;box-sizing:border-box;resize:none;font-family:inherit;"></textarea>' +
            '<label style="display:flex;align-items:flex-start;gap:10px;margin:18px 4px;font-size:13px;color:var(--text-primary,#000);cursor:pointer;"><input type="checkbox" id="kca_ack" style="margin-top:3px;"> I understand this account will be heavily censored for child safety.</label>' +
            '<button onclick="submitKidsCreatorApplication()" style="width:100%;padding:15px;border-radius:14px;border:none;background:#34C759;color:#fff;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px;">Submit application</button>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(ov);
};

window.submitKidsCreatorApplication = async function() {
    if (!window.sb || !currentUser) { showToast('Please sign in'); return; }
    var reason = (document.getElementById('kca_reason') || {}).value || '';
    var content = (document.getElementById('kca_content') || {}).value || '';
    var ack = (document.getElementById('kca_ack') || {}).checked;
    if (!reason.trim() || !content.trim()) { showToast('Please answer both questions'); return; }
    if (!ack) { showToast('Please acknowledge the censorship notice'); return; }
    showToast('Submitting...');
    try {
        var res = await sb.from('kids_account_applications').insert({
            applicant_id: currentUser.id, reason: reason.trim(), content_type: content.trim(),
            acknowledged_censorship: true, status: 'pending'
        });
        if (res.error) { showToast('Could not submit: ' + res.error.message); return; }
        var ov = document.getElementById('kidsCreatorApp'); if (ov) ov.remove();
        showToast('Application submitted for review');
    } catch (e) { showToast('Submit failed'); }
};
