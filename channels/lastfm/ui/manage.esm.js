const BASE_URL = () => window.mimirServerBaseUrl || window.location.origin;
const API = () => `${BASE_URL()}/api/channels/com.lastfm.nowplaying`;

const STYLES = `
  :host { display: block; font-family: var(--font-base, system-ui, sans-serif); color: var(--color-text, #e8e8e8); }
  .panel { max-width: 560px; }
  h2 { font-size: 1.1rem; margin: 0 0 4px; color: var(--color-text, #e8e8e8); }
  .sub { font-size: 0.82rem; color: var(--color-text-secondary, #888); margin: 0 0 20px; }
  .form-group { margin-bottom: 14px; }
  label { display: block; font-size: 0.82rem; margin-bottom: 4px; color: var(--color-text-secondary, #888); }
  input[type=text], input[type=password], select {
    width: 100%; box-sizing: border-box;
    background: var(--color-surface, #1a1a1a); border: 1px solid var(--color-border, #333);
    color: var(--color-text, #e8e8e8); border-radius: var(--radius-sm, 4px);
    padding: 8px 10px; font-size: 0.9rem;
  }
  .checkbox-row { display: flex; align-items: center; gap: 8px; font-size: 0.9rem; }
  .actions { display: flex; gap: 10px; align-items: center; margin-top: 18px; }
  .btn { padding: 8px 18px; border: none; border-radius: var(--radius-sm, 4px); cursor: pointer; font-size: 0.9rem; }
  .btn-primary { background: #ba0000; color: #fff; }
  .btn-primary:hover { background: #d40000; }
  .btn-primary:disabled { opacity: 0.5; cursor: default; }
  .now-playing { display: flex; gap: 14px; align-items: center; padding: 14px;
    background: var(--color-surface, #1a1a1a); border-radius: var(--radius-md, 8px); margin-bottom: 20px; }
  .art { width: 64px; height: 64px; border-radius: 4px; object-fit: cover; background: #222; flex-shrink: 0; }
  .art-placeholder { width: 64px; height: 64px; border-radius: 4px; background: #2a2a2a;
    display: flex; align-items: center; justify-content: center; font-size: 1.8rem; color: #555; flex-shrink: 0; }
  .track-name { font-weight: 600; font-size: 0.95rem; margin-bottom: 2px; }
  .track-artist { font-size: 0.85rem; color: var(--color-text-secondary, #888); }
  .track-album { font-size: 0.78rem; color: var(--color-text-tertiary, #666); margin-top: 2px; }
  .badge { display: inline-flex; align-items: center; gap: 5px; font-size: 0.72rem;
    padding: 2px 7px; border-radius: 99px; background: #ba0000; color: #fff; margin-bottom: 6px; }
  .badge-idle { background: #444; color: #aaa; }
  .error { color: var(--color-error, #f87171); font-size: 0.82rem; margin-top: 8px; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #ba0000;
    border-top-color: transparent; border-radius: 50%; animation: spin .7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .link { font-size: 0.78rem; color: var(--color-accent, #00c851); text-decoration: none; }
  .link:hover { text-decoration: underline; }
  .divider { border: none; border-top: 1px solid var(--color-border, #333); margin: 20px 0; }
`;

class LastfmManager extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._state = {
      loading: true, saving: false, error: null,
      username: '', apiKey: '', showLastPlayed: true, theme: 'dark', squareStyle: 'art_only',
      configured: false, track: null, trackStatus: null,
    };
    this._pollTimer = null;
  }

  connectedCallback() {
    this._load().then(() => {
      if (this._state.configured) this._pollTrack();
    });
  }

  disconnectedCallback() {
    clearInterval(this._pollTimer);
  }

  _set(updates) {
    Object.assign(this._state, updates);
    this._render();
  }

  async _load() {
    try {
      const resp = await fetch(`${API()}/settings`);
      const data = await resp.json();
      if (data.success) {
        const s = data.settings || {};
        this._set({
          loading: false,
          username: s.username || '',
          apiKey: '',                        // never pre-fill masked key
          showLastPlayed: s.show_last_played !== false,
          theme: s.theme || 'dark',
          squareStyle: s.square_style || 'art_only',
          configured: s.configured || false,
        });
      }
    } catch (e) {
      this._set({ loading: false, error: 'Could not load settings.' });
    }
  }

  async _save() {
    const s = this._state;
    const body = {
      username: s.username.trim(),
      show_last_played: s.showLastPlayed,
      theme: s.theme,
    };
    if (s.apiKey.trim()) body.api_key = s.apiKey.trim();
    body.square_style = s.squareStyle;

    this._set({ saving: true, error: null });
    try {
      const resp = await fetch(`${API()}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (data.success) {
        this._set({ saving: false, apiKey: '', configured: data.settings?.configured || false });
        if (this._state.configured) this._pollTrack();
      } else {
        this._set({ saving: false, error: 'Save failed.' });
      }
    } catch (e) {
      this._set({ saving: false, error: String(e) });
    }
  }

  async _pollTrack() {
    clearInterval(this._pollTimer);
    const fetch_track = async () => {
      try {
        const resp = await fetch(`${API()}/status`);
        const data = await resp.json();
        this._set({ track: data.track || null, trackStatus: data.status || null });
      } catch (_) {}
    };
    await fetch_track();
    this._pollTimer = setInterval(fetch_track, 30000);
  }

  _render() {
    const s = this._state;
    const shadow = this.shadowRoot;

    shadow.innerHTML = `
      <style>${STYLES}</style>
      <div class="panel">
        <h2>Last.fm Now Playing</h2>
        <p class="sub">Displays your scrobbling track. Works with Apple Music, Spotify, or any scrobbler.
          <a class="link" href="https://www.last.fm/api/account/create" target="_blank">Get a free API key →</a>
        </p>

        ${s.loading ? '<div><span class="spinner"></span> Loading…</div>' : ''}

        ${!s.loading && s.configured && s.track ? this._nowPlayingHtml(s.track, s.trackStatus) : ''}

        ${!s.loading ? `
          <hr class="divider">
          <div class="form-group">
            <label>Last.fm Username</label>
            <input id="username" type="text" value="${s.username}" placeholder="your_username" autocomplete="off">
          </div>
          <div class="form-group">
            <label>API Key ${s.configured ? '(leave blank to keep existing)' : ''}</label>
            <input id="apikey" type="password" value="${s.apiKey}" placeholder="${s.configured ? '••••••••' : 'Paste API key here'}" autocomplete="off">
          </div>
          <div class="form-group">
            <div class="checkbox-row">
              <input id="showlast" type="checkbox" ${s.showLastPlayed ? 'checked' : ''}>
              <label for="showlast" style="margin:0">Show last played track when idle</label>
            </div>
          </div>
          <div class="form-group">
            <label>Display Theme</label>
            <select id="theme">
              <option value="dark" ${s.theme === 'dark' ? 'selected' : ''}>Dark</option>
              <option value="light" ${s.theme === 'light' ? 'selected' : ''}>Light</option>
            </select>
          </div>
          <div class="form-group">
            <label>Square Display Style</label>
            <select id="squarestyle">
              <option value="art_only" ${s.squareStyle === 'art_only' ? 'selected' : ''}>Album art only</option>
              <option value="with_details" ${s.squareStyle === 'with_details' ? 'selected' : ''}>Album art + track details</option>
            </select>
          </div>
          <div class="actions">
            <button class="btn btn-primary" id="save" ${s.saving ? 'disabled' : ''}>
              ${s.saving ? '<span class="spinner"></span> Saving…' : 'Save Settings'}
            </button>
          </div>
          ${s.error ? `<div class="error">${s.error}</div>` : ''}
        ` : ''}
      </div>
    `;

    shadow.getElementById('save')?.addEventListener('click', () => this._save());
    shadow.getElementById('username')?.addEventListener('input', e => { this._state.username = e.target.value; });
    shadow.getElementById('apikey')?.addEventListener('input', e => { this._state.apiKey = e.target.value; });
    shadow.getElementById('showlast')?.addEventListener('change', e => { this._state.showLastPlayed = e.target.checked; });
    shadow.getElementById('theme')?.addEventListener('change', e => { this._state.theme = e.target.value; });
    shadow.getElementById('squarestyle')?.addEventListener('change', e => { this._state.squareStyle = e.target.value; });
  }

  _nowPlayingHtml(track, status) {
    const playing = track?.is_playing;
    const artUrl = track?.art_url || '';
    const artHtml = artUrl
      ? `<img class="art" src="${artUrl}" alt="album art">`
      : `<div class="art-placeholder">♫</div>`;

    return `
      <div class="now-playing">
        ${artHtml}
        <div>
          <div class="badge ${playing ? '' : 'badge-idle'}">
            ${playing ? '▶ NOW PLAYING' : '⏹ LAST PLAYED'}
          </div>
          <div class="track-name">${track?.track || '—'}</div>
          <div class="track-artist">${track?.artist || ''}</div>
          ${track?.album ? `<div class="track-album">${track.album}</div>` : ''}
        </div>
      </div>
    `;
  }
}

customElements.define('x-lastfm-manager', LastfmManager);
