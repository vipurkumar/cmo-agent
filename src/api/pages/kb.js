/**
 * Knowledge Base page for CMO Agent dashboard.
 * Upload, search, and manage KB documents (battlecards, case studies, messaging, objection handling).
 *
 * @param {HTMLElement} container - DOM element to render into
 * @param {object} api - API helper with get/post methods that handle auth headers
 */
function renderKnowledgeBase(container, api) {
  // ── Styles ──────────────────────────────────────────────────────────
  const styles = `
    .kb-page { max-width: 960px; margin: 0 auto; padding: 2rem 1rem; }
    .kb-page h2 {
      font-size: 1.8rem;
      background: linear-gradient(to right, #818cf8, #22d3ee);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 1.5rem;
    }
    .kb-section {
      background: rgba(30, 41, 59, 0.8);
      border: 1px solid rgba(148, 163, 184, 0.1);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }
    .kb-section-title {
      font-size: 1.1rem;
      font-weight: 600;
      color: #e2e8f0;
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .kb-form-group { margin-bottom: 1rem; }
    .kb-form-group label {
      display: block;
      font-size: 0.85rem;
      color: #94a3b8;
      margin-bottom: 0.35rem;
    }
    .kb-input, .kb-select, .kb-textarea {
      width: 100%;
      padding: 0.6rem 0.75rem;
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(148, 163, 184, 0.15);
      border-radius: 8px;
      color: #e2e8f0;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.2s;
    }
    .kb-input:focus, .kb-select:focus, .kb-textarea:focus {
      border-color: rgba(129, 140, 248, 0.5);
    }
    .kb-textarea {
      font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
      min-height: 160px;
      resize: vertical;
      line-height: 1.5;
    }
    .kb-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.55rem 1.1rem;
      border: none;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }
    .kb-btn-primary {
      background: linear-gradient(135deg, #6366f1, #818cf8);
      color: #fff;
    }
    .kb-btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }
    .kb-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .kb-btn-secondary {
      background: rgba(148, 163, 184, 0.15);
      color: #94a3b8;
    }
    .kb-btn-secondary:hover { background: rgba(148, 163, 184, 0.25); color: #e2e8f0; }
    .kb-btn-row { display: flex; gap: 0.75rem; margin-top: 0.5rem; }

    /* Search */
    .kb-search-wrap {
      display: flex;
      gap: 0.75rem;
      align-items: center;
    }
    .kb-search-wrap .kb-input { flex: 1; }

    /* Results */
    .kb-results { margin-top: 1rem; }
    .kb-result-card {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(148, 163, 184, 0.1);
      border-radius: 8px;
      padding: 1rem;
      margin-bottom: 0.75rem;
      transition: border-color 0.2s;
    }
    .kb-result-card:hover { border-color: rgba(129, 140, 248, 0.3); }
    .kb-result-title {
      font-weight: 600;
      color: #e2e8f0;
      margin-bottom: 0.25rem;
    }
    .kb-result-type {
      display: inline-block;
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.15rem 0.5rem;
      border-radius: 4px;
      background: rgba(129, 140, 248, 0.15);
      color: #a5b4fc;
      margin-bottom: 0.5rem;
    }
    .kb-result-preview {
      font-size: 0.85rem;
      color: #94a3b8;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .kb-result-preview mark {
      background: rgba(250, 204, 21, 0.25);
      color: #fde68a;
      border-radius: 2px;
      padding: 0 2px;
    }
    .kb-result-score {
      font-size: 0.75rem;
      color: #64748b;
      margin-top: 0.4rem;
    }
    .kb-empty {
      text-align: center;
      color: #64748b;
      padding: 2rem;
      font-size: 0.9rem;
    }

    /* Toast */
    .kb-toast {
      position: fixed;
      top: 1.5rem;
      right: 1.5rem;
      padding: 0.75rem 1.25rem;
      border-radius: 8px;
      font-size: 0.85rem;
      color: #fff;
      z-index: 9999;
      opacity: 0;
      transform: translateY(-12px);
      transition: all 0.3s ease;
      max-width: 380px;
      word-break: break-word;
    }
    .kb-toast.visible { opacity: 1; transform: translateY(0); }
    .kb-toast.success { background: rgba(34, 197, 94, 0.9); }
    .kb-toast.error { background: rgba(239, 68, 68, 0.9); }

    /* Spinner */
    .kb-spinner {
      display: inline-block;
      width: 14px; height: 14px;
      border: 2px solid rgba(255,255,255,0.3);
      border-top-color: #fff;
      border-radius: 50%;
      animation: kb-spin 0.6s linear infinite;
    }
    @keyframes kb-spin { to { transform: rotate(360deg); } }
  `;

  // ── HTML ────────────────────────────────────────────────────────────
  container.innerHTML = `
    <style>${styles}</style>
    <div class="kb-page">
      <h2>Knowledge Base</h2>

      <!-- Upload Section -->
      <div class="kb-section">
        <div class="kb-section-title">
          <span>&#128218;</span> Upload Document
        </div>
        <form id="kb-upload-form" autocomplete="off">
          <div class="kb-form-group">
            <label for="kb-title">Title</label>
            <input id="kb-title" class="kb-input" type="text" placeholder="e.g. Q1 Enterprise Battlecard" required />
          </div>
          <div class="kb-form-group">
            <label for="kb-type">Type</label>
            <select id="kb-type" class="kb-select" required>
              <option value="">Select type...</option>
              <option value="battlecard">Battlecard</option>
              <option value="case_study">Case Study</option>
              <option value="messaging">Messaging</option>
              <option value="objection_handling">Objection Handling</option>
            </select>
          </div>
          <div class="kb-form-group">
            <label for="kb-content">Content</label>
            <textarea id="kb-content" class="kb-textarea" placeholder="Paste or type document content here..." required></textarea>
          </div>
          <div class="kb-btn-row">
            <button type="submit" class="kb-btn kb-btn-primary" id="kb-upload-btn">Upload</button>
          </div>
        </form>
      </div>

      <!-- Search Section -->
      <div class="kb-section">
        <div class="kb-section-title">
          <span>&#128269;</span> Search Knowledge Base
        </div>
        <div class="kb-search-wrap">
          <input id="kb-search-input" class="kb-input" type="text" placeholder="Search documents..." />
          <button class="kb-btn kb-btn-primary" id="kb-search-btn">Search</button>
        </div>
        <div class="kb-results" id="kb-results"></div>
      </div>

      <!-- Reload Section -->
      <div class="kb-section">
        <div class="kb-section-title">
          <span>&#128260;</span> Reload Static Files
        </div>
        <p style="color:#94a3b8;font-size:0.85rem;margin-bottom:0.75rem;">
          Re-index static KB files from disk into the vector store.
        </p>
        <button class="kb-btn kb-btn-secondary" id="kb-reload-btn">Reload KB Files</button>
      </div>
    </div>
  `;

  // ── Toast helper ────────────────────────────────────────────────────
  function showToast(message, type) {
    var existing = document.querySelector('.kb-toast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.className = 'kb-toast ' + type;
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(function () {
      toast.classList.add('visible');
    });

    setTimeout(function () {
      toast.classList.remove('visible');
      setTimeout(function () { toast.remove(); }, 300);
    }, 3500);
  }

  // ── Upload handler ──────────────────────────────────────────────────
  var uploadForm = container.querySelector('#kb-upload-form');
  var uploadBtn = container.querySelector('#kb-upload-btn');

  uploadForm.addEventListener('submit', async function (e) {
    e.preventDefault();

    var title = container.querySelector('#kb-title').value.trim();
    var type = container.querySelector('#kb-type').value;
    var content = container.querySelector('#kb-content').value.trim();

    if (!title || !type || !content) {
      showToast('Please fill in all fields.', 'error');
      return;
    }

    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<span class="kb-spinner"></span> Uploading...';

    try {
      var formData = new FormData();
      formData.append('title', title);
      formData.append('type', type);
      formData.append('content', content);

      await api.post('/api/v1/kb/upload', formData);

      showToast('Document "' + title + '" uploaded successfully.', 'success');
      uploadForm.reset();
    } catch (err) {
      var msg = (err && err.message) ? err.message : 'Upload failed. Please try again.';
      showToast(msg, 'error');
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = 'Upload';
    }
  });

  // ── Search handler ──────────────────────────────────────────────────
  var searchInput = container.querySelector('#kb-search-input');
  var searchBtn = container.querySelector('#kb-search-btn');
  var resultsContainer = container.querySelector('#kb-results');

  function highlightText(text, query) {
    if (!query) return escapeHtml(text);
    var escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    var regex = new RegExp('(' + escaped + ')', 'gi');
    return escapeHtml(text).replace(regex, '<mark>$1</mark>');
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  function truncate(str, len) {
    if (str.length <= len) return str;
    return str.substring(0, len) + '...';
  }

  async function doSearch() {
    var query = searchInput.value.trim();
    if (!query) {
      resultsContainer.innerHTML = '<div class="kb-empty">Enter a search term above.</div>';
      return;
    }

    searchBtn.disabled = true;
    searchBtn.innerHTML = '<span class="kb-spinner"></span>';

    try {
      var data = await api.get('/api/v1/kb/search?query=' + encodeURIComponent(query) + '&limit=5');
      var results = data.results || data || [];

      if (!results.length) {
        resultsContainer.innerHTML = '<div class="kb-empty">No results found for "' + escapeHtml(query) + '".</div>';
        return;
      }

      var html = '';
      for (var i = 0; i < results.length; i++) {
        var r = results[i];
        var preview = truncate(r.content || r.text || '', 300);
        var score = r.score != null ? r.score.toFixed(3) : null;
        html += '<div class="kb-result-card">';
        html += '  <div class="kb-result-title">' + escapeHtml(r.title || 'Untitled') + '</div>';
        if (r.type) {
          html += '  <span class="kb-result-type">' + escapeHtml(r.type.replace(/_/g, ' ')) + '</span>';
        }
        html += '  <div class="kb-result-preview">' + highlightText(preview, query) + '</div>';
        if (score !== null) {
          html += '  <div class="kb-result-score">Relevance: ' + score + '</div>';
        }
        html += '</div>';
      }
      resultsContainer.innerHTML = html;
    } catch (err) {
      resultsContainer.innerHTML = '<div class="kb-empty" style="color:#ef4444;">Search failed. Please try again.</div>';
    } finally {
      searchBtn.disabled = false;
      searchBtn.textContent = 'Search';
    }
  }

  searchBtn.addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') doSearch();
  });

  // ── Reload handler ──────────────────────────────────────────────────
  var reloadBtn = container.querySelector('#kb-reload-btn');

  reloadBtn.addEventListener('click', async function () {
    reloadBtn.disabled = true;
    reloadBtn.innerHTML = '<span class="kb-spinner"></span> Reloading...';

    try {
      await api.post('/api/v1/kb/reload');
      showToast('Knowledge base files reloaded successfully.', 'success');
    } catch (err) {
      showToast('Reload failed. Please try again.', 'error');
    } finally {
      reloadBtn.disabled = false;
      reloadBtn.textContent = 'Reload KB Files';
    }
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { renderKnowledgeBase: renderKnowledgeBase };
}
