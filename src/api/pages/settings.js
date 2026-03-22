/**
 * Settings page for CMO Agent Dashboard.
 */
function renderSettingsPage(container, api) {

    async function load() {
        container.innerHTML = '<div class="loading"><div class="spinner"></div> Loading...</div>';

        const [automationRes, usersRes, webhooksRes] = await Promise.allSettled([
            api('/api/v1/automation/status'),
            api('/api/v1/users'),
            api('/api/v1/webhooks'),
        ]);

        const automation = automationRes.status === 'fulfilled' ? automationRes.value : null;
        const usersData = usersRes.status === 'fulfilled' ? usersRes.value : null;
        const webhooksData = webhooksRes.status === 'fulfilled' ? webhooksRes.value : null;

        render(automation, usersData, webhooksData);
    }

    function render(automation, usersData, webhooksData) {
        let html = '';

        // ── API Keys ──
        html += '<div style="background:rgba(30,41,59,0.8);border:1px solid rgba(148,163,184,0.1);border-radius:10px;padding:20px;margin-bottom:16px">';
        html += '<h3 style="color:#c7d2fe;font-size:15px;margin:0 0 12px">API Keys</h3>';
        const maskedKey = localStorage.getItem('cmo_api_key') || '';
        const display = maskedKey.length > 12 ? maskedKey.slice(0, 8) + '...' + maskedKey.slice(-4) : maskedKey;
        html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">';
        html += '<code style="background:rgba(15,23,42,0.8);padding:8px 12px;border-radius:6px;color:#a5b4fc;font-size:13px;flex:1">' + display + '</code>';
        html += '<button onclick="navigator.clipboard.writeText(\'' + maskedKey + '\').then(()=>alert(\'Copied!\'))" style="background:rgba(129,140,248,0.15);color:#818cf8;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px">Copy</button>';
        html += '</div>';
        html += '<div style="display:flex;gap:8px">';
        html += '<input type="text" id="new-key-name" placeholder="Key name (e.g. CI/CD)" style="background:rgba(15,23,42,0.6);color:#e2e8f0;border:1px solid rgba(148,163,184,0.2);padding:6px 10px;border-radius:4px;font-size:12px;flex:1">';
        html += '<button onclick="window._createKey()" style="background:#818cf8;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px">Create New Key</button>';
        html += '</div>';
        html += '<div id="new-key-result" style="margin-top:8px"></div>';
        html += '</div>';

        // ── Team Members ──
        html += '<div style="background:rgba(30,41,59,0.8);border:1px solid rgba(148,163,184,0.1);border-radius:10px;padding:20px;margin-bottom:16px">';
        html += '<h3 style="color:#c7d2fe;font-size:15px;margin:0 0 12px">Team Members</h3>';
        const users = usersData && usersData.users ? usersData.users : [];
        if (users.length > 0) {
            html += '<table style="width:100%;border-collapse:collapse;margin-bottom:12px">';
            html += '<tr><th style="text-align:left;padding:6px 8px;color:#94a3b8;font-size:12px;border-bottom:1px solid rgba(148,163,184,0.1)">Email</th><th style="text-align:left;padding:6px 8px;color:#94a3b8;font-size:12px;border-bottom:1px solid rgba(148,163,184,0.1)">Name</th><th style="text-align:left;padding:6px 8px;color:#94a3b8;font-size:12px;border-bottom:1px solid rgba(148,163,184,0.1)">Role</th></tr>';
            const roleColors = { admin: '#a78bfa', operator: '#3b82f6', viewer: '#94a3b8' };
            users.forEach(u => {
                const rc = roleColors[u.role] || '#94a3b8';
                html += '<tr><td style="padding:8px;color:#e2e8f0;font-size:13px;border-bottom:1px solid rgba(148,163,184,0.05)">' + u.email + '</td>';
                html += '<td style="padding:8px;color:#e2e8f0;font-size:13px;border-bottom:1px solid rgba(148,163,184,0.05)">' + u.name + '</td>';
                html += '<td style="padding:8px;border-bottom:1px solid rgba(148,163,184,0.05)"><span style="background:' + rc + '20;color:' + rc + ';padding:2px 8px;border-radius:4px;font-size:11px">' + u.role + '</span></td></tr>';
            });
            html += '</table>';
        }
        html += '<div style="display:flex;gap:8px">';
        html += '<input type="email" id="invite-email" placeholder="Email" style="background:rgba(15,23,42,0.6);color:#e2e8f0;border:1px solid rgba(148,163,184,0.2);padding:6px 10px;border-radius:4px;font-size:12px;flex:1">';
        html += '<input type="text" id="invite-name" placeholder="Name" style="background:rgba(15,23,42,0.6);color:#e2e8f0;border:1px solid rgba(148,163,184,0.2);padding:6px 10px;border-radius:4px;font-size:12px;flex:1">';
        html += '<select id="invite-role" style="background:rgba(15,23,42,0.6);color:#e2e8f0;border:1px solid rgba(148,163,184,0.2);padding:6px 10px;border-radius:4px;font-size:12px"><option>viewer</option><option>operator</option><option>admin</option></select>';
        html += '<button onclick="window._addUser()" style="background:#818cf8;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px">Add</button>';
        html += '</div></div>';

        // ── Webhooks ──
        html += '<div style="background:rgba(30,41,59,0.8);border:1px solid rgba(148,163,184,0.1);border-radius:10px;padding:20px;margin-bottom:16px">';
        html += '<h3 style="color:#c7d2fe;font-size:15px;margin:0 0 12px">Webhook Subscriptions</h3>';
        const webhooks = webhooksData && webhooksData.webhooks ? webhooksData.webhooks : [];
        webhooks.forEach(w => {
            html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px;border-bottom:1px solid rgba(148,163,184,0.05)">';
            html += '<div><span style="color:#e2e8f0;font-size:13px">' + w.url + '</span>';
            html += '<div style="margin-top:2px">' + (w.events || []).map(function(e) { return '<span style="background:rgba(129,140,248,0.1);color:#818cf8;padding:1px 5px;border-radius:3px;font-size:10px;margin-right:4px">' + e + '</span>'; }).join('') + '</div></div>';
            html += '<div style="display:flex;gap:6px">';
            html += '<button onclick="window._testWebhook(\'' + w.id + '\')" style="background:rgba(34,197,94,0.15);color:#22c55e;border:none;padding:4px 8px;border-radius:4px;cursor:pointer;font-size:11px">Test</button>';
            html += '<button onclick="window._deleteWebhook(\'' + w.id + '\')" style="background:rgba(239,68,68,0.15);color:#ef4444;border:none;padding:4px 8px;border-radius:4px;cursor:pointer;font-size:11px">Delete</button>';
            html += '</div></div>';
        });
        html += '<div style="display:flex;gap:8px;margin-top:12px">';
        html += '<input type="url" id="webhook-url" placeholder="https://your-app.com/webhook" style="background:rgba(15,23,42,0.6);color:#e2e8f0;border:1px solid rgba(148,163,184,0.2);padding:6px 10px;border-radius:4px;font-size:12px;flex:1">';
        html += '<button onclick="window._createWebhook()" style="background:#818cf8;color:#fff;border:none;padding:6px 14px;border-radius:4px;cursor:pointer;font-size:12px">Add Webhook</button>';
        html += '</div></div>';

        // ── Automation ──
        if (automation) {
            html += '<div style="background:rgba(30,41,59,0.8);border:1px solid rgba(148,163,184,0.1);border-radius:10px;padding:20px">';
            html += '<h3 style="color:#c7d2fe;font-size:15px;margin:0 0 12px">Automation Control</h3>';
            const statusColor = automation.is_paused ? '#ef4444' : '#22c55e';
            const statusText = automation.is_paused ? 'Paused' : 'Active';
            html += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">';
            html += '<div style="width:10px;height:10px;border-radius:50%;background:' + statusColor + '"></div>';
            html += '<span style="color:#e2e8f0;font-size:14px;font-weight:600">' + statusText + '</span>';
            if (automation.reason) html += '<span style="color:#94a3b8;font-size:12px">(' + automation.reason + ')</span>';
            html += '</div>';

            // Send cap bars
            const dailyPct = automation.daily_remaining != null ? Math.round(((automation.daily_used || 0) / ((automation.daily_used || 0) + (automation.daily_remaining || 1))) * 100) : 0;
            const weeklyPct = automation.weekly_remaining != null ? Math.round(((automation.weekly_used || 0) / ((automation.weekly_used || 0) + (automation.weekly_remaining || 1))) * 100) : 0;

            [['Daily', dailyPct, automation.daily_used, automation.daily_remaining], ['Weekly', weeklyPct, automation.weekly_used, automation.weekly_remaining]].forEach(([label, pct, used, rem]) => {
                const barColor = pct > 80 ? '#ef4444' : pct > 50 ? '#eab308' : '#22c55e';
                html += '<div style="margin-bottom:8px"><div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="color:#94a3b8;font-size:12px">' + label + '</span><span style="color:#94a3b8;font-size:12px">' + used + ' used / ' + rem + ' remaining</span></div>';
                html += '<div style="height:6px;background:rgba(148,163,184,0.1);border-radius:3px;overflow:hidden"><div style="width:' + pct + '%;height:100%;background:' + barColor + ';border-radius:3px"></div></div></div>';
            });

            html += '<div style="display:flex;gap:8px;margin-top:12px">';
            if (automation.is_paused) {
                html += '<button onclick="window._resumeAutomation()" style="background:#22c55e;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px">Resume Automation</button>';
            } else {
                html += '<button onclick="window._pauseAutomation()" style="background:#ef4444;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:13px">Pause Automation</button>';
            }
            html += '</div></div>';
        }

        container.innerHTML = html;
    }

    // Global handlers
    window._createKey = async function() {
        const name = document.getElementById('new-key-name').value || 'default';
        const wsId = ''; // workspace_id is extracted from API key by backend
        try {
            // We need workspace_id — extract from automation status or similar
            const status = await api('/api/v1/automation/status');
            const wsId = status.workspace_id;
            const result = await api('/api/v1/workspaces/' + wsId + '/api-keys', {
                method: 'POST',
                body: JSON.stringify({ name: name }),
            });
            document.getElementById('new-key-result').innerHTML = '<div style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.2);border-radius:6px;padding:10px;color:#22c55e;font-size:12px">New key created: <code style="user-select:all">' + result.api_key + '</code> (copy it now, it won\'t be shown again)</div>';
        } catch (e) {
            document.getElementById('new-key-result').innerHTML = '<div style="color:#ef4444;font-size:12px">Failed: ' + e.message + '</div>';
        }
    };

    window._addUser = async function() {
        const email = document.getElementById('invite-email').value;
        const name = document.getElementById('invite-name').value;
        const role = document.getElementById('invite-role').value;
        if (!email || !name) return alert('Email and name required');
        try {
            await api('/api/v1/users', { method: 'POST', body: JSON.stringify({ email, name, role }) });
            load();
        } catch (e) { alert('Failed: ' + e.message); }
    };

    window._testWebhook = async function(id) {
        try {
            const result = await api('/api/v1/webhooks/' + id + '/test', { method: 'POST' });
            alert('Test sent! Status: ' + JSON.stringify(result.delivery));
        } catch (e) { alert('Test failed: ' + e.message); }
    };

    window._deleteWebhook = async function(id) {
        if (!confirm('Delete this webhook?')) return;
        try {
            await api('/api/v1/webhooks/' + id, { method: 'DELETE' });
            load();
        } catch (e) { alert('Failed: ' + e.message); }
    };

    window._createWebhook = async function() {
        const url = document.getElementById('webhook-url').value;
        if (!url) return alert('URL required');
        try {
            const result = await api('/api/v1/webhooks', {
                method: 'POST',
                body: JSON.stringify({ url: url, events: ['brief_ready', 'automation_paused', 'qualification_complete'] }),
            });
            alert('Webhook created! Secret: ' + result.secret);
            load();
        } catch (e) { alert('Failed: ' + e.message); }
    };

    window._pauseAutomation = async function() {
        const reason = prompt('Reason for pausing?') || 'Manual pause from dashboard';
        try {
            await api('/api/v1/automation/pause', { method: 'POST', body: JSON.stringify({ reason }) });
            load();
        } catch (e) { alert('Failed: ' + e.message); }
    };

    window._resumeAutomation = async function() {
        try {
            await api('/api/v1/automation/resume', { method: 'POST' });
            load();
        } catch (e) { alert('Failed: ' + e.message); }
    };

    load();
}
