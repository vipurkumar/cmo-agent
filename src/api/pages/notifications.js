/**
 * Notifications page for CMO Agent Dashboard.
 */
function renderNotificationsPage(container, api) {
    let unreadOnly = false;

    const typeIcons = {
        automation_paused: '\u23F8\uFE0F',
        automation_resumed: '\u25B6\uFE0F',
        brief_ready: '\uD83D\uDCCB',
        high_error_rate: '\u26A0\uFE0F',
        send_cap_reached: '\uD83D\uDEAB',
        kill_switch_triggered: '\uD83D\uDED1',
        evaluation_complete: '\u2705',
        qualification_complete: '\u2705',
    };

    const priorityColors = {
        critical: '#ef4444',
        high: '#f97316',
        medium: '#3b82f6',
        low: '#94a3b8',
    };

    function timeAgo(iso) {
        if (!iso) return '';
        const diff = (Date.now() - new Date(iso).getTime()) / 1000;
        if (diff < 60) return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
        return new Date(iso).toLocaleDateString();
    }

    async function load() {
        container.innerHTML = '<div class="loading"><div class="spinner"></div> Loading...</div>';
        try {
            const params = unreadOnly ? '?unread_only=true&limit=50' : '?limit=50';
            const data = await api('/api/v1/notifications' + params);
            const notifs = data.notifications || [];
            const unreadCount = data.unread_count || 0;
            render(notifs, unreadCount);
        } catch (e) {
            container.innerHTML = '<div class="empty-state"><p>Could not load notifications.</p></div>';
        }
    }

    function render(notifs, unreadCount) {
        let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">';
        html += '<div style="display:flex;gap:8px">';
        html += '<button onclick="window._notifFilter(false)" style="border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;' + (!unreadOnly ? 'background:#818cf8;color:#fff' : 'background:rgba(148,163,184,0.1);color:#94a3b8') + '">All</button>';
        html += '<button onclick="window._notifFilter(true)" style="border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;' + (unreadOnly ? 'background:#818cf8;color:#fff' : 'background:rgba(148,163,184,0.1);color:#94a3b8') + '">Unread (' + unreadCount + ')</button>';
        html += '</div></div>';

        if (notifs.length === 0) {
            html += '<div class="empty-state"><p>No notifications yet.</p></div>';
            container.innerHTML = html;
            return;
        }

        notifs.forEach(n => {
            const icon = typeIcons[n.notification_type] || '\uD83D\uDD14';
            const pColor = priorityColors[n.priority] || '#94a3b8';
            const unread = !n.read;
            const bg = unread ? 'rgba(129,140,248,0.05)' : 'transparent';
            const border = unread ? 'rgba(129,140,248,0.2)' : 'rgba(148,163,184,0.1)';

            html += '<div onclick="window._markRead(\'' + n.id + '\',this)" style="background:' + bg + ';border:1px solid ' + border + ';border-radius:8px;padding:14px;margin-bottom:8px;cursor:pointer;transition:all 0.2s">';
            html += '<div style="display:flex;align-items:start;gap:12px">';
            html += '<span style="font-size:20px">' + icon + '</span>';
            html += '<div style="flex:1">';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">';
            html += '<span style="font-weight:' + (unread ? '600' : '400') + ';color:#e2e8f0;font-size:14px">' + (n.title || '') + '</span>';
            html += '<div style="display:flex;gap:8px;align-items:center">';
            html += '<span style="background:' + pColor + '20;color:' + pColor + ';padding:1px 6px;border-radius:3px;font-size:10px">' + (n.priority || '') + '</span>';
            html += '<span style="color:#64748b;font-size:11px">' + timeAgo(n.created_at) + '</span>';
            html += '</div></div>';
            html += '<p style="color:#94a3b8;font-size:13px;margin:0;line-height:1.4">' + (n.message || '') + '</p>';
            html += '</div></div></div>';
        });

        container.innerHTML = html;
    }

    window._notifFilter = function(uo) { unreadOnly = uo; load(); };
    window._markRead = async function(id, el) {
        try {
            await api('/api/v1/notifications/' + id + '/read', { method: 'POST' });
            el.style.background = 'transparent';
            el.style.borderColor = 'rgba(148,163,184,0.1)';
            const title = el.querySelector('span[style*="font-weight"]');
            if (title) title.style.fontWeight = '400';
        } catch (e) { /* ignore */ }
    };

    load();
}
