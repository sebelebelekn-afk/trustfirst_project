// ============================================================
// ADMIN DASHBOARD — moderation & verification review.
// Visible only to is_admin users. Reads the moderation tables
// (RLS already restricts these to admins / owners).
// ============================================================
function openAdminDashboard() {
    if (!currentUser || !currentUser.is_admin) { showToast('Admins only'); return; }
    var existing = document.getElementById('adminDashOverlay');
    if (existing) existing.remove();
    var ov = document.createElement('div');
    ov.id = 'adminDashOverlay';
    ov.className = 'white-overlay';
    ov.style.cssText = 'position:absolute;inset:0;z-index:9800;display:flex;flex-direction:column;background:var(--bg-primary,#fff);animation:slideUpOverlay 0.3s cubic-bezier(0.32,0.72,0,1);';
    ov.innerHTML =
        '<div class="header-container" style="flex-shrink:0;">' +
            '<div class="liquid-glass-btn" onclick="document.getElementById(\'adminDashOverlay\').remove()" style="cursor:pointer;"><i class="fa-solid fa-chevron-left"></i></div>' +
            '<b>Admin Dashboard</b>' +
        '</div>' +
        '<div style="display:flex;border-bottom:0.5px solid var(--border-color,#eee);flex-shrink:0;overflow-x:auto;">' +
            ['applications', 'reports', 'feedback', 'kids'].map(function(t, i) {
                return '<button id="adminTab_' + t + '" onclick="adminSwitchTab(\'' + t + '\')" style="flex:1;min-width:90px;padding:13px 8px;background:none;border:none;border-bottom:2px solid ' + (i === 0 ? '#007AFF' : 'transparent') + ';color:' + (i === 0 ? 'var(--text-primary,#000)' : '#888') + ';font-size:13px;font-weight:700;cursor:pointer;text-transform:capitalize;">' + t + '</button>';
            }).join('') +
        '</div>' +
        '<div id="adminDashBody" style="flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:14px 16px 80px;">' +
            '<div style="text-align:center;padding:40px;color:#aaa;"><i class="fa-solid fa-spinner fa-spin"></i></div>' +
        '</div>';
    (document.getElementById('app') || document.body).appendChild(ov);
    adminSwitchTab('applications');
}

window.adminSwitchTab = function(tab) {
    ['applications', 'reports', 'feedback', 'kids'].forEach(function(t) {
        var b = document.getElementById('adminTab_' + t);
        if (b) { b.style.borderBottomColor = (t === tab) ? '#007AFF' : 'transparent'; b.style.color = (t === tab) ? 'var(--text-primary,#000)' : '#888'; }
    });
    var body = document.getElementById('adminDashBody');
    if (!body) return;
    body.innerHTML = '<div style="text-align:center;padding:40px;color:#aaa;"><i class="fa-solid fa-spinner fa-spin"></i></div>';
    if (tab === 'applications') return adminLoadApplications(body, 'verification');
    if (tab === 'kids') return adminLoadApplications(body, 'kids');
    if (tab === 'reports') return adminLoadReports(body);
    if (tab === 'feedback') return adminLoadFeedback(body);
};

function _adminEmpty(label) {
    return '<div style="text-align:center;padding:50px 20px;color:#aaa;"><i class="fa-solid fa-inbox" style="font-size:32px;display:block;margin-bottom:12px;opacity:0.5;"></i>' + label + '</div>';
}
function _adminCard(inner) {
    return '<div style="background:var(--card-bg,#f7f7f7);border-radius:14px;padding:14px 16px;margin-bottom:10px;border:0.5px solid var(--border-color,rgba(0,0,0,0.06));">' + inner + '</div>';
}

async function adminLoadApplications(body, mode) {
    try {
        var table = mode === 'kids' ? 'kids_account_applications' : 'verification_applications';
        var res = await sb.from(table).select('*').eq('status', 'pending').order('created_at', { ascending: false }).limit(50);
        var rows = res.data || [];
        if (!rows.length) { body.innerHTML = _adminEmpty(mode === 'kids' ? 'No kids-account applications' : 'No pending applications'); return; }
        body.innerHTML = rows.map(function(r) {
            if (mode === 'kids') {
                return _adminCard(
                    '<div style="font-size:14px;font-weight:700;color:var(--text-primary,#000);">Kids account request</div>' +
                    '<div style="font-size:12px;color:#888;margin:6px 0;">Reason: ' + escapeHtml(r.reason || '—') + '</div>' +
                    '<div style="font-size:12px;color:#888;margin-bottom:4px;">Content: ' + escapeHtml(r.content_type || '—') + '</div>' +
                    '<div style="font-size:11px;color:' + (r.acknowledged_censorship ? '#34C759' : '#FF3B30') + ';margin-bottom:12px;">' + (r.acknowledged_censorship ? '✔ Acknowledged censorship' : '✘ Did not acknowledge censorship') + '</div>' +
                    _adminActions("adminReviewKids('" + r.id + "','" + r.applicant_id + "'", true)
                );
            }
            var data = r.data || {};
            var details = Object.keys(data).map(function(k) { return '<div style="font-size:12px;color:#888;"><b style="color:var(--text-secondary,#555);">' + escapeHtml(k.replace(/_/g, ' ')) + ':</b> ' + escapeHtml(String(data[k])) + '</div>'; }).join('');
            var docs = (r.documents || []).length ? '<div style="font-size:11px;color:#007AFF;margin-top:6px;cursor:pointer;" onclick="adminViewDoc(\'' + escapeHtml((r.documents[0] || '')) + '\')"><i class="fa-solid fa-paperclip"></i> View document</div>' : '';
            return _adminCard(
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;"><span style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.04em;padding:3px 9px;border-radius:20px;background:' + _badgeColor(r.badge_type) + '22;color:' + _badgeColor(r.badge_type) + ';">' + escapeHtml(r.badge_type) + ' badge</span></div>' +
                details + docs +
                '<div style="margin-top:12px;">' + _adminActions("adminReviewVerif('" + r.id + "','" + r.user_id + "','" + r.badge_type + "'", true) + '</div>'
            );
        }).join('');
    } catch (e) { body.innerHTML = _adminEmpty('Could not load'); }
}

function _badgeColor(type) {
    return { blue: '#007AFF', red: '#FF3B30', silver: '#8E8E93', gold: '#FFB800', white: '#34C759' }[type] || '#888';
}
function _adminActions(prefix, withReject) {
    return '<div style="display:flex;gap:8px;">' +
        '<button onclick="' + prefix + ",'approved')\" style=\"flex:1;padding:11px;border-radius:11px;border:none;background:#34C759;color:#fff;font-size:13px;font-weight:700;cursor:pointer;\">Approve</button>" +
        (withReject ? '<button onclick="' + prefix + ",'rejected')\" style=\"flex:1;padding:11px;border-radius:11px;border:none;background:rgba(255,59,48,0.12);color:#FF3B30;font-size:13px;font-weight:700;cursor:pointer;\">Reject</button>" : '') +
        '</div>';
}

window.adminReviewVerif = async function(appId, userId, badgeType, decision) {
    try {
        await sb.from('verification_applications').update({ status: decision, reviewed_by: currentUser.id, updated_at: new Date().toISOString() }).eq('id', appId);
        if (decision === 'approved') {
            await sb.from('users').update({ verified: true, badge_status: 'verified', badge_tier: 'verify-' + badgeType }).eq('id', userId);
        }
        showToast(decision === 'approved' ? 'Approved & badge granted' : 'Application rejected');
        adminSwitchTab('applications');
    } catch (e) { showToast('Action failed'); }
};

window.adminReviewKids = async function(appId, applicantId, decision) {
    try {
        await sb.from('kids_account_applications').update({ status: decision, reviewed_by: currentUser.id }).eq('id', appId);
        if (decision === 'approved') {
            // Approving makes the applicant a kids-content creator (white badge); their posts go to the kids feed.
            await sb.from('users').update({ badge_status: 'verified', badge_tier: 'verify-white' }).eq('id', applicantId);
        }
        showToast(decision === 'approved' ? 'Approved — white badge granted' : 'Rejected');
        adminSwitchTab('kids');
    } catch (e) { showToast('Action failed'); }
};

window.adminViewDoc = async function(path) {
    if (!path) return;
    try {
        var s = await sb.storage.from('verification_docs').createSignedUrl(path, 300);
        if (s.data && s.data.signedUrl) window.open(s.data.signedUrl, '_blank');
        else showToast('Could not open document');
    } catch (e) { showToast('Could not open document'); }
};

async function adminLoadReports(body) {
    try {
        var res = await sb.from('reports').select('*').neq('status', 'resolved').neq('status', 'dismissed').order('created_at', { ascending: false }).limit(50);
        var rows = res.data || [];
        if (!rows.length) { body.innerHTML = _adminEmpty('No open reports'); return; }
        body.innerHTML = rows.map(function(r) {
            return _adminCard(
                '<div style="font-size:14px;font-weight:700;color:var(--text-primary,#000);text-transform:capitalize;">' + escapeHtml(r.target_type) + ' report</div>' +
                '<div style="font-size:13px;color:var(--text-secondary,#555);margin:6px 0;">Reason: ' + escapeHtml(r.reason) + '</div>' +
                (r.details ? '<div style="font-size:12px;color:#888;margin-bottom:10px;">' + escapeHtml(r.details) + '</div>' : '') +
                '<div style="display:flex;gap:8px;margin-top:10px;">' +
                    '<button onclick="adminResolveReport(\'' + r.id + '\',\'resolved\')" style="flex:1;padding:11px;border-radius:11px;border:none;background:#34C759;color:#fff;font-size:13px;font-weight:700;cursor:pointer;">Resolve</button>' +
                    '<button onclick="adminResolveReport(\'' + r.id + '\',\'dismissed\')" style="flex:1;padding:11px;border-radius:11px;border:none;background:var(--bg-secondary,#eee);color:#888;font-size:13px;font-weight:700;cursor:pointer;">Dismiss</button>' +
                '</div>'
            );
        }).join('');
    } catch (e) { body.innerHTML = _adminEmpty('Could not load'); }
}

window.adminResolveReport = async function(id, status) {
    try {
        await sb.from('reports').update({ status: status, reviewed_by: currentUser.id }).eq('id', id);
        showToast(status === 'resolved' ? 'Resolved' : 'Dismissed');
        adminSwitchTab('reports');
    } catch (e) { showToast('Action failed'); }
};

async function adminLoadFeedback(body) {
    try {
        var res = await sb.from('feedback').select('*').order('created_at', { ascending: false }).limit(60);
        var rows = res.data || [];
        if (!rows.length) { body.innerHTML = _adminEmpty('No feedback yet'); return; }
        body.innerHTML = rows.map(function(r) {
            var color = r.kind === 'bug' ? '#FF3B30' : '#007AFF';
            return _adminCard(
                '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;"><span style="font-size:11px;font-weight:800;text-transform:uppercase;padding:2px 8px;border-radius:20px;background:' + color + '22;color:' + color + ';">' + escapeHtml(r.kind) + '</span><span style="font-size:11px;color:#aaa;">' + (r.app_version ? 'v' + escapeHtml(r.app_version) : '') + '</span></div>' +
                '<div style="font-size:13px;color:var(--text-primary,#000);line-height:1.5;">' + escapeHtml(r.message) + '</div>'
            );
        }).join('');
    } catch (e) { body.innerHTML = _adminEmpty('Could not load'); }
}

// ============================================================
// BANNED USERS LIST (admin tool) — list & unban locked accounts
// ============================================================
async function openBannedUsersList() {
    if (!currentUser || !currentUser.is_admin) { showToast('Admins only'); return; }
    var existing = document.getElementById('bannedUsersOverlay'); if (existing) existing.remove();
    var ov = document.createElement('div');
    ov.id = 'bannedUsersOverlay';
    ov.className = 'white-overlay';
    ov.style.cssText = 'position:absolute;inset:0;z-index:9810;display:flex;flex-direction:column;background:var(--bg-primary,#fff);animation:slideUpOverlay 0.3s cubic-bezier(0.32,0.72,0,1);';
    ov.innerHTML =
        '<div class="header-container" style="flex-shrink:0;">' +
            '<div class="liquid-glass-btn" onclick="document.getElementById(\'bannedUsersOverlay\').remove()" style="cursor:pointer;"><i class="fa-solid fa-chevron-left"></i></div>' +
            '<b>Banned Users</b>' +
        '</div>' +
        '<div id="bannedUsersList" style="flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:14px 16px 80px;"><div style="text-align:center;padding:40px;color:#aaa;"><i class="fa-solid fa-spinner fa-spin"></i></div></div>';
    (document.getElementById('app') || document.body).appendChild(ov);
    loadBannedUsers();
}

async function loadBannedUsers() {
    var el = document.getElementById('bannedUsersList');
    if (!el) return;
    try {
        var res = await sb.from('users').select('id,username,full_name,avatar_url,lock_reason,locked_at')
            .eq('is_locked', true).order('locked_at', { ascending: false }).limit(100);
        var rows = res.data || [];
        if (!rows.length) {
            el.innerHTML = '<div style="text-align:center;padding:50px 20px;color:#aaa;"><i class="fa-solid fa-user-check" style="font-size:30px;display:block;margin-bottom:12px;opacity:0.5;"></i>No banned users</div>';
            return;
        }
        el.innerHTML = rows.map(function(u) {
            var av = u.avatar_url || ('https://ui-avatars.com/api/?name=' + encodeURIComponent(u.full_name || u.username || 'U') + '&background=FF3B30&color=fff&size=80');
            return '<div data-uid="' + u.id + '" style="display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:0.5px solid var(--border-color,#eee);">' +
                '<img src="' + escapeHtml(av) + '" style="width:46px;height:46px;border-radius:50%;object-fit:cover;flex-shrink:0;">' +
                '<div style="flex:1;min-width:0;"><b style="font-size:15px;color:var(--text-primary,#000);">' + escapeHtml(u.full_name || u.username || 'User') + '</b><br><small style="color:#888;">@' + escapeHtml(u.username || '') + (u.lock_reason ? ' · ' + escapeHtml(u.lock_reason) : '') + '</small></div>' +
                '<button onclick="unbanUserRow(\'' + u.id + '\',this)" style="padding:8px 16px;border-radius:18px;border:1px solid #34C759;background:transparent;color:#34C759;font-size:13px;font-weight:700;cursor:pointer;flex-shrink:0;">Unban</button>' +
            '</div>';
        }).join('');
    } catch(e) { el.innerHTML = '<div style="text-align:center;padding:40px;color:#aaa;">Could not load banned users</div>'; }
}

async function unbanUserRow(userId, btn) {
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
        var res = await sb.from('users').update({ is_locked: false, lock_reason: null, locked_at: null }).eq('id', userId);
        if (res && res.error) { showToast('Could not unban'); if (btn) { btn.disabled = false; btn.textContent = 'Unban'; } return; }
        var row = document.querySelector('#bannedUsersList [data-uid="' + userId + '"]');
        if (row) row.remove();
        var listEl = document.getElementById('bannedUsersList');
        if (listEl && !listEl.querySelector('[data-uid]')) loadBannedUsers();
        showToast('User unbanned');
        if (typeof triggerHaptic === 'function') triggerHaptic(20);
    } catch(e) { showToast('Could not unban'); if (btn) { btn.disabled = false; btn.textContent = 'Unban'; } }
}

// Reveal the Admin entry in settings only for admins (hooks openSettings).
(function() {
    var _origOpenSettings = window.openSettings;
    if (typeof _origOpenSettings === 'function') {
        window.openSettings = function() {
            _origOpenSettings.apply(this, arguments);
            var row = document.getElementById('settingsAdminRow');
            if (row) row.style.display = (currentUser && currentUser.is_admin) ? 'flex' : 'none';
        };
    }
})();
