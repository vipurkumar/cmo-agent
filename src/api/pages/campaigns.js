/**
 * Campaigns page for CMO Agent Dashboard.
 * Renders campaign list, create form, detail view, and qualification trigger.
 *
 * Usage: renderCampaigns(containerElement, apiFn)
 *   - container: DOM element to render into
 *   - api: async function(path, options?) that handles auth headers and returns parsed JSON
 */

// eslint-disable-next-line no-unused-vars
function renderCampaignsPage(container, api) {
    let currentPage = 1;
    const pageSize = 10;
    let totalPages = 1;

    // ── Status badge colors ──────────────────────────────────────────
    const STATUS_STYLES = {
        draft:     { bg: 'rgba(100,116,139,0.15)', color: '#94a3b8', label: 'Draft' },
        active:    { bg: 'rgba(34,197,94,0.15)',   color: '#4ade80', label: 'Active' },
        completed: { bg: 'rgba(96,165,250,0.15)',  color: '#60a5fa', label: 'Completed' },
        paused:    { bg: 'rgba(250,204,21,0.15)',  color: '#facc15', label: 'Paused' },
    };

    function statusBadge(status) {
        const s = STATUS_STYLES[status] || STATUS_STYLES.draft;
        return `<span style="
            display:inline-block;padding:2px 10px;border-radius:9999px;font-size:0.75rem;
            font-weight:600;background:${s.bg};color:${s.color};text-transform:capitalize;
        ">${s.label}</span>`;
    }

    function fmtDate(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    }

    // ── Toast notification ───────────────────────────────────────────
    function showToast(message, type = 'success') {
        const bg = type === 'success' ? 'rgba(34,197,94,0.9)' : 'rgba(239,68,68,0.9)';
        const toast = document.createElement('div');
        toast.textContent = message;
        Object.assign(toast.style, {
            position: 'fixed', bottom: '24px', right: '24px', padding: '12px 24px',
            background: bg, color: '#fff', borderRadius: '8px', fontSize: '0.875rem',
            fontWeight: '500', zIndex: '10000', boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
            transition: 'opacity 0.3s',
        });
        document.body.appendChild(toast);
        setTimeout(() => { toast.style.opacity = '0'; }, 2500);
        setTimeout(() => { toast.remove(); }, 3000);
    }

    // ── Styles (injected once) ───────────────────────────────────────
    const STYLE_ID = 'cmo-campaigns-styles';
    if (!document.getElementById(STYLE_ID)) {
        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            .cmo-campaigns-table { width:100%; border-collapse:collapse; }
            .cmo-campaigns-table th {
                text-align:left; padding:10px 14px; font-size:0.75rem; font-weight:600;
                text-transform:uppercase; letter-spacing:0.05em;
                background:#334155; color:#94a3b8; border-bottom:1px solid #1e293b;
            }
            .cmo-campaigns-table td {
                padding:12px 14px; font-size:0.875rem; color:#e2e8f0;
                border-bottom:1px solid rgba(51,65,85,0.5);
            }
            .cmo-campaigns-table tr:hover td { background:rgba(129,140,248,0.05); }
            .cmo-campaigns-table tr { cursor:pointer; }

            .cmo-btn-sm {
                padding:5px 14px; font-size:0.75rem; font-weight:600; border-radius:6px;
                border:1px solid #6366f1; color:#a5b4fc; background:transparent;
                cursor:pointer; transition:all 0.15s;
            }
            .cmo-btn-sm:hover { background:rgba(99,102,241,0.15); color:#c7d2fe; }
            .cmo-btn-sm:disabled { opacity:0.4; cursor:not-allowed; }

            .cmo-btn-primary {
                padding:8px 20px; font-size:0.875rem; font-weight:600; border-radius:8px;
                border:none; background:#6366f1; color:#fff; cursor:pointer;
                transition:background 0.15s;
            }
            .cmo-btn-primary:hover { background:#4f46e5; }
            .cmo-btn-primary:disabled { opacity:0.5; cursor:not-allowed; }

            .cmo-modal-overlay {
                position:fixed; inset:0; background:rgba(0,0,0,0.6); z-index:9000;
                display:flex; align-items:center; justify-content:center;
            }
            .cmo-modal-card {
                background:#1e293b; border:1px solid #334155; border-radius:12px;
                padding:28px 32px; width:100%; max-width:480px;
                box-shadow:0 8px 32px rgba(0,0,0,0.5);
            }
            .cmo-modal-card h3 {
                margin:0 0 20px; font-size:1.125rem; font-weight:700; color:#f1f5f9;
            }
            .cmo-form-group { margin-bottom:16px; }
            .cmo-form-group label {
                display:block; margin-bottom:4px; font-size:0.75rem;
                font-weight:600; color:#94a3b8; text-transform:uppercase;
                letter-spacing:0.04em;
            }
            .cmo-form-group input {
                width:100%; padding:8px 12px; font-size:0.875rem; border-radius:6px;
                border:1px solid #334155; background:#0f172a; color:#e2e8f0;
                outline:none; box-sizing:border-box;
            }
            .cmo-form-group input:focus { border-color:#6366f1; }

            .cmo-pagination {
                display:flex; align-items:center; justify-content:center;
                gap:12px; margin-top:16px;
            }
            .cmo-pagination span { font-size:0.8125rem; color:#94a3b8; }

            .cmo-detail-back {
                display:inline-flex; align-items:center; gap:6px;
                font-size:0.8125rem; color:#818cf8; cursor:pointer;
                margin-bottom:16px; border:none; background:none; font-weight:600;
            }
            .cmo-detail-back:hover { color:#a5b4fc; }
        `;
        document.head.appendChild(style);
    }

    // ── Render: campaign list ────────────────────────────────────────
    async function loadCampaigns() {
        container.innerHTML = `
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;">
                <h2 style="margin:0;font-size:1.25rem;font-weight:700;color:#f1f5f9;">Campaigns</h2>
                <button class="cmo-btn-primary" id="cmo-create-btn">+ New Campaign</button>
            </div>
            <div id="cmo-campaigns-body" style="color:#94a3b8;font-size:0.875rem;">Loading...</div>
        `;

        container.querySelector('#cmo-create-btn').addEventListener('click', openCreateModal);

        try {
            const data = await api(`/campaigns?page=${currentPage}&page_size=${pageSize}`);

            const campaigns = data.campaigns || data.items || data.data || [];
            const total = data.total || campaigns.length;
            totalPages = Math.max(1, Math.ceil(total / pageSize));

            const body = container.querySelector('#cmo-campaigns-body');

            if (campaigns.length === 0) {
                body.innerHTML = `
                    <div style="text-align:center;padding:48px 0;color:#64748b;">
                        <div style="font-size:2rem;margin-bottom:8px;">&#128203;</div>
                        <p style="margin:0;">No campaigns yet. Create your first campaign to get started.</p>
                    </div>
                `;
                return;
            }

            body.innerHTML = `
                <div style="overflow-x:auto;border-radius:8px;border:1px solid #334155;">
                    <table class="cmo-campaigns-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Status</th>
                                <th>Created</th>
                                <th style="text-align:right;">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="cmo-campaigns-tbody"></tbody>
                    </table>
                </div>
                <div class="cmo-pagination" id="cmo-pagination"></div>
            `;

            const tbody = body.querySelector('#cmo-campaigns-tbody');
            campaigns.forEach((c) => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="font-weight:600;color:#e2e8f0;">${escapeHtml(c.name || '—')}</td>
                    <td>${statusBadge(c.status || 'draft')}</td>
                    <td>${fmtDate(c.created_at || c.created)}</td>
                    <td style="text-align:right;">
                        <button class="cmo-btn-sm cmo-qualify-btn" data-id="${c.id}"
                            title="Trigger account qualification">Qualify</button>
                    </td>
                `;
                // Click row (but not the button) to see details
                tr.addEventListener('click', (e) => {
                    if (e.target.closest('.cmo-qualify-btn')) return;
                    loadDetail(c.id);
                });
                tbody.appendChild(tr);
            });

            // Qualify buttons
            tbody.querySelectorAll('.cmo-qualify-btn').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    triggerQualification(btn.dataset.id);
                });
            });

            renderPagination();
        } catch (err) {
            container.querySelector('#cmo-campaigns-body').innerHTML =
                `<p style="color:#f87171;">Failed to load campaigns: ${escapeHtml(String(err.message || err))}</p>`;
        }
    }

    // ── Render: pagination ───────────────────────────────────────────
    function renderPagination() {
        const pag = container.querySelector('#cmo-pagination');
        if (!pag) return;
        pag.innerHTML = `
            <button class="cmo-btn-sm" id="cmo-prev" ${currentPage <= 1 ? 'disabled' : ''}>&#8592; Prev</button>
            <span>Page ${currentPage} of ${totalPages}</span>
            <button class="cmo-btn-sm" id="cmo-next" ${currentPage >= totalPages ? 'disabled' : ''}>Next &#8594;</button>
        `;
        pag.querySelector('#cmo-prev').addEventListener('click', () => {
            if (currentPage > 1) { currentPage--; loadCampaigns(); }
        });
        pag.querySelector('#cmo-next').addEventListener('click', () => {
            if (currentPage < totalPages) { currentPage++; loadCampaigns(); }
        });
    }

    // ── Create campaign modal ────────────────────────────────────────
    function openCreateModal() {
        const overlay = document.createElement('div');
        overlay.className = 'cmo-modal-overlay';
        overlay.innerHTML = `
            <div class="cmo-modal-card">
                <h3>Create Campaign</h3>
                <form id="cmo-create-form">
                    <div class="cmo-form-group">
                        <label for="cmo-f-name">Campaign Name</label>
                        <input id="cmo-f-name" type="text" placeholder="e.g. Q2 SaaS Outbound" required />
                    </div>
                    <div class="cmo-form-group">
                        <label for="cmo-f-industries">ICP Industries (comma-separated)</label>
                        <input id="cmo-f-industries" type="text" placeholder="e.g. SaaS, FinTech, HealthTech" />
                    </div>
                    <div style="display:flex;gap:12px;">
                        <div class="cmo-form-group" style="flex:1;">
                            <label for="cmo-f-emp-min">Employee Min</label>
                            <input id="cmo-f-emp-min" type="number" min="1" placeholder="50" />
                        </div>
                        <div class="cmo-form-group" style="flex:1;">
                            <label for="cmo-f-emp-max">Employee Max</label>
                            <input id="cmo-f-emp-max" type="number" min="1" placeholder="500" />
                        </div>
                    </div>
                    <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:8px;">
                        <button type="button" class="cmo-btn-sm" id="cmo-cancel-create">Cancel</button>
                        <button type="submit" class="cmo-btn-primary" id="cmo-submit-create">Create</button>
                    </div>
                </form>
            </div>
        `;

        // Close on overlay click (outside card)
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });

        document.body.appendChild(overlay);

        overlay.querySelector('#cmo-cancel-create').addEventListener('click', () => overlay.remove());

        overlay.querySelector('#cmo-create-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const submitBtn = overlay.querySelector('#cmo-submit-create');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Creating...';

            const name = overlay.querySelector('#cmo-f-name').value.trim();
            const industriesRaw = overlay.querySelector('#cmo-f-industries').value.trim();
            const empMin = overlay.querySelector('#cmo-f-emp-min').value;
            const empMax = overlay.querySelector('#cmo-f-emp-max').value;

            const industries = industriesRaw
                ? industriesRaw.split(',').map((s) => s.trim()).filter(Boolean)
                : [];

            const payload = { name };
            if (industries.length > 0) {
                payload.icp = { industries };
                if (empMin) payload.icp.employee_range_min = parseInt(empMin, 10);
                if (empMax) payload.icp.employee_range_max = parseInt(empMax, 10);
            }

            try {
                await createCampaign(payload);
                overlay.remove();
                showToast('Campaign created successfully');
            } catch (err) {
                showToast('Failed to create campaign: ' + (err.message || err), 'error');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Create';
            }
        });
    }

    // ── API: create campaign ─────────────────────────────────────────
    async function createCampaign(formData) {
        await api('/campaigns', {
            method: 'POST',
            body: JSON.stringify(formData),
        });
        currentPage = 1;
        await loadCampaigns();
    }

    // ── API: trigger qualification ───────────────────────────────────
    async function triggerQualification(campaignId) {
        try {
            await api(`/api/v1/campaigns/${campaignId}/qualify`, {
                method: 'POST',
                body: JSON.stringify({ max_accounts: 20 }),
            });
            showToast('Qualification triggered');
        } catch (err) {
            showToast('Qualification failed: ' + (err.message || err), 'error');
        }
    }

    // ── Render: campaign detail ──────────────────────────────────────
    async function loadDetail(campaignId) {
        container.innerHTML = `
            <button class="cmo-detail-back" id="cmo-back-btn">&#8592; Back to campaigns</button>
            <div id="cmo-detail-body" style="color:#94a3b8;font-size:0.875rem;">Loading campaign...</div>
        `;
        container.querySelector('#cmo-back-btn').addEventListener('click', () => {
            loadCampaigns();
        });

        try {
            const c = await api(`/campaigns/${campaignId}`);
            const detailBody = container.querySelector('#cmo-detail-body');

            const icpHtml = c.icp ? `
                <div style="margin-top:20px;">
                    <h4 style="margin:0 0 8px;font-size:0.875rem;font-weight:700;color:#cbd5e1;">ICP Criteria</h4>
                    <div style="display:flex;flex-wrap:wrap;gap:8px;">
                        ${(c.icp.industries || []).map((ind) =>
                            `<span style="padding:3px 10px;border-radius:9999px;font-size:0.75rem;
                                background:rgba(99,102,241,0.15);color:#a5b4fc;">${escapeHtml(ind)}</span>`
                        ).join('')}
                    </div>
                    ${c.icp.employee_range_min || c.icp.employee_range_max ? `
                        <p style="margin:8px 0 0;font-size:0.8125rem;color:#94a3b8;">
                            Employees: ${c.icp.employee_range_min || '—'} &ndash; ${c.icp.employee_range_max || '—'}
                        </p>
                    ` : ''}
                </div>
            ` : '';

            const accountsHtml = (c.accounts && c.accounts.length > 0) ? `
                <div style="margin-top:20px;">
                    <h4 style="margin:0 0 8px;font-size:0.875rem;font-weight:700;color:#cbd5e1;">
                        Accounts (${c.accounts.length})
                    </h4>
                    <div style="overflow-x:auto;border-radius:8px;border:1px solid #334155;">
                        <table class="cmo-campaigns-table">
                            <thead>
                                <tr>
                                    <th>Company</th>
                                    <th>Domain</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${c.accounts.map((a) => `
                                    <tr style="cursor:default;">
                                        <td>${escapeHtml(a.company || a.name || '—')}</td>
                                        <td style="color:#94a3b8;">${escapeHtml(a.domain || '—')}</td>
                                        <td>${statusBadge(a.status || 'draft')}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            ` : '';

            detailBody.innerHTML = `
                <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:24px;">
                    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
                        <h2 style="margin:0;font-size:1.25rem;font-weight:700;color:#f1f5f9;">
                            ${escapeHtml(c.name || '—')}
                        </h2>
                        ${statusBadge(c.status || 'draft')}
                    </div>
                    <p style="margin:4px 0 0;font-size:0.8125rem;color:#64748b;">
                        Created ${fmtDate(c.created_at || c.created)}
                        ${c.workspace_id ? ' &middot; Workspace ' + escapeHtml(c.workspace_id) : ''}
                    </p>
                    ${icpHtml}
                    ${accountsHtml}
                    <div style="margin-top:20px;display:flex;gap:10px;">
                        <button class="cmo-btn-primary" id="cmo-detail-qualify">Trigger Qualification</button>
                    </div>
                </div>
            `;

            detailBody.querySelector('#cmo-detail-qualify').addEventListener('click', () => {
                triggerQualification(campaignId);
            });
        } catch (err) {
            container.querySelector('#cmo-detail-body').innerHTML =
                `<p style="color:#f87171;">Failed to load campaign: ${escapeHtml(String(err.message || err))}</p>`;
        }
    }

    // ── Utility: escape HTML ─────────────────────────────────────────
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // ── Initial load ─────────────────────────────────────────────────
    loadCampaigns();
}
