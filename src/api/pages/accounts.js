/**
 * Accounts & Briefs page for CMO Agent Dashboard.
 */
function renderAccountsPage(container, api) {
    let filterAction = 'all';
    let sortBy = 'overall_priority_score';

    async function load() {
        container.innerHTML = '<div class="loading"><div class="spinner"></div> Loading...</div>';
        try {
            const data = await api('/api/v1/export/scores?format=json&limit=50');
            const scores = Array.isArray(data) ? data : (data.items || []);
            render(scores);
        } catch (e) {
            container.innerHTML = '<div class="empty-state"><p>Could not load accounts. ' + e.message + '</p></div>';
        }
    }

    function scoreColor(val) {
        if (val >= 70) return '#22c55e';
        if (val >= 40) return '#eab308';
        return '#ef4444';
    }

    function actionBadge(action) {
        const colors = { pursue_now: '#22c55e', nurture: '#eab308', disqualify: '#ef4444', human_review_required: '#3b82f6' };
        const color = colors[action] || '#94a3b8';
        return '<span style="background:' + color + '20;color:' + color + ';padding:2px 8px;border-radius:4px;font-size:12px">' + (action || 'N/A') + '</span>';
    }

    function render(scores) {
        let filtered = scores;
        if (filterAction !== 'all') {
            // Can't filter by action from scores endpoint, but we show all
        }
        filtered.sort((a, b) => (b[sortBy] || 0) - (a[sortBy] || 0));

        let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">';
        html += '<div style="display:flex;gap:8px">';
        ['all','pursue_now','nurture','disqualify'].forEach(f => {
            const active = filterAction === f ? 'background:#818cf8;color:#fff' : 'background:rgba(148,163,184,0.1);color:#94a3b8';
            html += '<button onclick="window._acctFilter(\'' + f + '\')" style="border:none;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px;' + active + '">' + f.replace('_', ' ') + '</button>';
        });
        html += '</div>';
        html += '<select onchange="window._acctSort(this.value)" style="background:#1e293b;color:#e2e8f0;border:1px solid rgba(148,163,184,0.2);padding:6px 10px;border-radius:6px;font-size:12px">';
        html += '<option value="overall_priority_score"' + (sortBy === 'overall_priority_score' ? ' selected' : '') + '>Priority Score</option>';
        html += '<option value="icp_fit_score"' + (sortBy === 'icp_fit_score' ? ' selected' : '') + '>ICP Fit</option>';
        html += '<option value="timing_score"' + (sortBy === 'timing_score' ? ' selected' : '') + '>Timing</option>';
        html += '</select></div>';

        if (filtered.length === 0) {
            html += '<div class="empty-state"><p>No accounts scored yet. Create a campaign and run qualification.</p></div>';
            container.innerHTML = html;
            return;
        }

        html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px">';
        filtered.forEach((s, i) => {
            const id = s.account_id || 'unknown';
            const shortId = id.length > 8 ? id.slice(0, 8) + '...' : id;
            html += '<div style="background:rgba(30,41,59,0.8);border:1px solid rgba(148,163,184,0.1);border-radius:10px;padding:16px;transition:border-color 0.2s" onmouseover="this.style.borderColor=\'rgba(129,140,248,0.3)\'" onmouseout="this.style.borderColor=\'rgba(148,163,184,0.1)\'">';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">';
            html += '<span style="color:#94a3b8;font-size:12px" title="' + id + '">' + shortId + '</span>';
            if (s.is_disqualified) html += '<span style="background:#ef444420;color:#ef4444;padding:2px 6px;border-radius:4px;font-size:11px">DQ</span>';
            html += '</div>';

            // Priority score (large)
            html += '<div style="text-align:center;margin-bottom:12px">';
            html += '<div style="font-size:36px;font-weight:700;color:' + scoreColor(s.overall_priority_score || 0) + '">' + (s.overall_priority_score || 0) + '</div>';
            html += '<div style="color:#94a3b8;font-size:12px">Priority Score</div>';
            html += '</div>';

            // Score bars
            [['ICP Fit', s.icp_fit_score], ['Pain Fit', s.pain_fit_score], ['Timing', s.timing_score]].forEach(([label, val]) => {
                val = val || 0;
                html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">';
                html += '<span style="color:#94a3b8;font-size:11px;width:55px">' + label + '</span>';
                html += '<div style="flex:1;height:6px;background:rgba(148,163,184,0.1);border-radius:3px;overflow:hidden">';
                html += '<div style="width:' + val + '%;height:100%;background:' + scoreColor(val) + ';border-radius:3px"></div>';
                html += '</div>';
                html += '<span style="color:#e2e8f0;font-size:11px;width:25px;text-align:right">' + val + '</span>';
                html += '</div>';
            });

            html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:10px;border-top:1px solid rgba(148,163,184,0.1)">';
            html += '<span style="color:#94a3b8;font-size:11px">Conf: ' + ((s.confidence_score || 0) * 100).toFixed(0) + '%</span>';
            html += '<button onclick="window._viewBrief(\'' + id + '\')" style="background:rgba(129,140,248,0.15);color:#818cf8;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px">View Brief</button>';
            html += '</div></div>';
        });
        html += '</div>';
        container.innerHTML = html;
    }

    window._acctFilter = function(f) { filterAction = f; load(); };
    window._acctSort = function(s) { sortBy = s; load(); };
    window._viewBrief = async function(accountId) {
        try {
            const brief = await api('/embed/' + accountId + '/json');
            showBriefModal(brief);
        } catch (e) {
            alert('No brief found for this account');
        }
    };

    function showBriefModal(brief) {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;display:flex;align-items:center;justify-content:center;padding:20px';
        overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };

        const b = brief.brief || {};
        let html = '<div style="background:#1e293b;border:1px solid rgba(148,163,184,0.2);border-radius:12px;padding:24px;max-width:800px;width:100%;max-height:80vh;overflow-y:auto;color:#e2e8f0">';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">';
        html += '<h2 style="margin:0;font-size:18px">Seller Brief</h2>';
        html += actionBadge(brief.action_type);
        html += '</div>';

        if (brief.scoring) {
            html += '<div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap">';
            ['icp_fit','pain_fit','timing','overall_priority'].forEach(k => {
                const val = brief.scoring[k] || 0;
                html += '<div style="background:rgba(15,23,42,0.6);padding:8px 14px;border-radius:8px;text-align:center">';
                html += '<div style="font-size:20px;font-weight:600;color:' + scoreColor(val) + '">' + val + '</div>';
                html += '<div style="font-size:10px;color:#94a3b8">' + k.replace(/_/g, ' ') + '</div></div>';
            });
            html += '</div>';
        }

        const sections = [
            ['Account Snapshot', b.account_snapshot],
            ['Why This Account', b.why_this_account],
            ['Why Now', b.why_now],
        ];
        sections.forEach(([title, content]) => {
            if (content) {
                html += '<div style="margin-bottom:12px"><h4 style="color:#c7d2fe;font-size:13px;margin-bottom:4px">' + title + '</h4>';
                html += '<p style="color:#94a3b8;font-size:13px;line-height:1.5">' + content + '</p></div>';
            }
        });

        if (b.risks_and_unknowns && b.risks_and_unknowns.length) {
            html += '<div style="margin-bottom:12px"><h4 style="color:#c7d2fe;font-size:13px;margin-bottom:4px">Risks & Unknowns</h4>';
            html += '<ul style="color:#94a3b8;font-size:13px;padding-left:16px">';
            b.risks_and_unknowns.forEach(r => { html += '<li>' + r + '</li>'; });
            html += '</ul></div>';
        }

        html += '<div style="text-align:right;margin-top:16px"><button onclick="this.closest(\'div[style*=fixed]\').remove()" style="background:#818cf8;color:#fff;border:none;padding:8px 20px;border-radius:6px;cursor:pointer">Close</button></div>';
        html += '</div>';
        overlay.innerHTML = html;
        document.body.appendChild(overlay);
    }

    load();
}
