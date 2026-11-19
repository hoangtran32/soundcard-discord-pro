/**
 * SoundCard Discord API & WebSocket Client
 */
const API = {
    async request(url, options = {}) {
        try {
            const res = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                const detail = typeof err.detail === 'string' ? err.detail : err.detail?.[0]?.msg;
                throw new Error(detail || 'Không thực hiện được yêu cầu.');
            }
            return await res.json();
        } catch (e) {
            console.error(`[API Error] ${url}:`, e);
            throw e;
        }
    },

    // Search Multi-Platform (YouTube, SoundCloud, Spotify)
    search: (query, platform = 'youtube', limit = 8) => 
        API.request('/api/search', { method: 'POST', body: JSON.stringify({ query, platform, limit }) }),

    // Player
    getState: () => API.request('/api/state'),
    play: (id = null) => API.request('/api/player/play', { method: 'POST', body: JSON.stringify({ id }) }),
    playSearchResult: (track) => API.request('/api/player/play-search-result', { method: 'POST', body: JSON.stringify({ track }) }),
    saveSearchResult: (albumId, track) => API.request(`/api/albums/${encodeURIComponent(albumId)}/tracks/from-search`, { method: 'POST', body: JSON.stringify({ track }) }),
    pause: () => API.request('/api/player/pause', { method: 'POST' }),
    resume: () => API.request('/api/player/resume', { method: 'POST' }),
    stop: () => API.request('/api/player/stop', { method: 'POST' }),
    next: () => API.request('/api/player/next', { method: 'POST' }),
    prev: () => API.request('/api/player/prev', { method: 'POST' }),
    seek: (seconds) => API.request('/api/player/seek', { method: 'POST', body: JSON.stringify({ seconds }) }),
    setVolume: (volume) => API.request('/api/player/volume', { method: 'POST', body: JSON.stringify({ volume }) }),
    setRepeat: (mode) => API.request('/api/player/repeat', { method: 'POST', body: JSON.stringify({ mode }) }),
    setShuffle: (shuffle) => API.request('/api/player/shuffle', { method: 'POST', body: JSON.stringify({ shuffle }) }),

    // Playlist
    getPlaylist: () => API.request('/api/playlist'),
    addTrack: (url, platform = 'youtube') => 
        API.request('/api/playlist/add', { method: 'POST', body: JSON.stringify({ url, platform }) }),
    addDirectTrack: (track) => 
        API.request('/api/playlist/add-direct', { method: 'POST', body: JSON.stringify({ track }) }),
    selectTrack: (id, selected) => API.request('/api/playlist/select', { method: 'POST', body: JSON.stringify({ id, selected }) }),
    selectAllTracks: (selected) => API.request('/api/playlist/select-all', { method: 'POST', body: JSON.stringify({ selected }) }),
    deleteTrack: (id) => API.request(`/api/playlist/${id}`, { method: 'DELETE' }),
    clearPlaylist: () => API.request('/api/playlist/clear', { method: 'POST' }),
    reorderPlaylist: (ids) => API.request('/api/playlist/reorder', { method: 'POST', body: JSON.stringify({ ids }) }),

    // Voice Rooms
    getRooms: () => API.request('/api/rooms'),
    addRoom: (data) => API.request('/api/rooms/add', { method: 'POST', body: JSON.stringify(data) }),
    updateRoom: (id, data) => API.request(`/api/rooms/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteRoom: (id) => API.request(`/api/rooms/${id}`, { method: 'DELETE' }),
    selectRoom: (id, selected) => API.request('/api/rooms/select', { method: 'POST', body: JSON.stringify({ id, selected }) }),
    selectAllRooms: (selected) => API.request('/api/rooms/select-all', { method: 'POST', body: JSON.stringify({ selected }) }),
    connectRoom: (id) => API.request(`/api/rooms/${id}/connect`, { method: 'POST' }),
    disconnectRoom: (id) => API.request(`/api/rooms/${id}/disconnect`, { method: 'POST' }),
    connectAllSelectedRooms: () => API.request('/api/rooms/connect-all', { method: 'POST' }),
    disconnectAllRooms: () => API.request('/api/rooms/disconnect-all', { method: 'POST' }),

    // Background & Settings
    getBackgrounds: () => API.request('/api/backgrounds'),
    selectBackground: (filename) => API.request('/api/backgrounds/select', { method: 'POST', body: JSON.stringify({ filename }) }),
    getConfig: () => API.request('/api/config'),
    updateConfig: (data) => API.request('/api/config', { method: 'POST', body: JSON.stringify(data) })
};

class SoundCardWebSocket {
    constructor() {
        this.ws = null;
        this.listeners = [];
        this.reconnectTimer = null;
        this.init();
    }

    init() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/player`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('[WS] Connected to SoundCard Engine');
            const dot = document.getElementById('server-status-dot');
            const txt = document.getElementById('server-status-text');
            if (dot) dot.className = 'dot-online';
            if (txt) txt.innerText = 'Máy chủ kết nối';
            if (this.reconnectTimer) {
                clearTimeout(this.reconnectTimer);
                this.reconnectTimer = null;
            }
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.listeners.forEach(fn => fn(data));
            } catch (e) {
                console.error('[WS Parse Error]', e);
            }
        };

        this.ws.onclose = () => {
            const dot = document.getElementById('server-status-dot');
            const txt = document.getElementById('server-status-text');
            if (dot) dot.className = 'dot-offline';
            if (txt) txt.innerText = 'Mất kết nối...';
            this.reconnectTimer = setTimeout(() => this.init(), 2000);
        };

        this.ws.onerror = (e) => {
            console.warn('[WS Error]', e);
        };
    }

    onUpdate(callback) {
        this.listeners.push(callback);
    }
}

const soundCardWS = window.location.protocol === 'file:' ? null : new SoundCardWebSocket();
