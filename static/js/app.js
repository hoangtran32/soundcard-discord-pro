/**
 * Main Application Logic for SoundCard Discord
 */
const AppState = {
    playlist: [],
    rooms: [],
    config: {},
    playerState: {},
    isDraggingSeek: false
};

function escapeHtml(value) {
    const chars = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return String(value ?? '').replace(/[&<>"']/g, char => chars[char]);
}

// --- Toast Notifications ---
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'fa-circle-info';
    if (type === 'success') icon = 'fa-circle-check';
    if (type === 'error') icon = 'fa-triangle-exclamation';

    toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// --- Duration Formatter ---
function formatTime(seconds) {
    if (!seconds || isNaN(seconds) || seconds < 0) return '00:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m < 10 ? '0' : ''}${m}:${s < 10 ? '0' : ''}${s}`;
}

// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
    if (window.location.protocol === 'file:') {
        document.getElementById('file-preview-notice').hidden = false;
        document.getElementById('server-status-text').textContent = 'Chế độ xem trước';
        document.querySelectorAll('.app-container button, .app-container input, .app-container select')
            .forEach(control => { control.disabled = true; });
        return;
    }

    document.addEventListener('error', (event) => {
        const img = event.target;
        const fallback = '/static/icons/default_cover.png';
        if (img instanceof HTMLImageElement && img.hasAttribute('data-cover') && img.getAttribute('src') !== fallback) {
            img.src = fallback;
        }
    }, true);
    initNavigation();
    initPlayerControls();
    initMultiPlatformSearch();
    initPlaylistActions();
    initAlbums();
    initRoomActions();
    initSettingsAndBackgrounds();

    // Initial Data Fetch
    await loadInitialData();

    // WebSocket Listener
    soundCardWS.onUpdate((payload) => {
        if (payload.type === 'tick' || payload.type === 'state_update') {
            if (payload.state) {
                updatePlayerUI(payload.state);
            }
            if (payload.rooms) {
                updateRoomsState(payload.rooms);
            }
            if (payload.config && !AppState.config.loaded) {
                applyConfigToUI(payload.config);
                AppState.config = { ...payload.config, loaded: true };
            }
        }
    });
});

async function loadInitialData() {
    try {
        const [config, playlist, rooms, state] = await Promise.all([
            API.getConfig(),
            API.getPlaylist(),
            API.getRooms(),
            API.getState()
        ]);

        AppState.config = config;
        AppState.playlist = playlist;
        AppState.rooms = rooms;
        AppState.playerState = state;

        applyConfigToUI(config);
        renderPlaylist();
        renderRooms();
        updatePlayerUI(state);
        loadBackgroundGallery();
    } catch (e) {
        console.error('Initial data load error:', e);
    }
}

// --- Navigation ---
function initNavigation() {
    const navButtons = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.getAttribute('data-tab');
            navButtons.forEach(b => b.classList.remove('active'));
            tabContents.forEach(t => t.classList.remove('active'));

            btn.classList.add('active');
            const targetEl = document.getElementById(`tab-${targetTab}`);
            if (targetEl) targetEl.classList.add('active');

            if (targetTab === 'now-playing' && visualizerInstance) {
                setTimeout(() => visualizerInstance.resize(), 50);
            }
        });
    });
}

// --- Multi-Platform Search & Quick Add ---
function initMultiPlatformSearch() {
    const input = document.getElementById('quick-url-input');
    const btn = document.getElementById('btn-quick-search');
    const pills = document.querySelectorAll('.platform-pill');
    const searchIcon = document.getElementById('search-input-icon');
    const drawer = document.getElementById('search-results-drawer');
    const drawerList = document.getElementById('search-results-list');
    const drawerHeading = document.getElementById('search-results-heading');
    const btnCloseDrawer = document.getElementById('btn-close-drawer');

    let currentPlatform = 'youtube';

    const placeholders = {
        youtube: 'Tìm bài hát trên YouTube hoặc dán link video...',
        soundcloud: 'Tìm kiếm bản nhạc, remix trên SoundCloud...',
        spotify: 'Tìm bài hát phong cách Spotify hoặc dán link track/playlist...',
        url: 'Dán link trực tiếp YouTube, SoundCloud, Spotify, MP3...'
    };

    const icons = {
        youtube: 'fa-brands fa-youtube',
        soundcloud: 'fa-brands fa-soundcloud',
        spotify: 'fa-brands fa-spotify',
        url: 'fa-solid fa-link'
    };

    // Platform pill switching
    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            pills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            currentPlatform = pill.getAttribute('data-platform');
            input.placeholder = placeholders[currentPlatform] || 'Tìm kiếm âm nhạc...';
            searchIcon.className = `${icons[currentPlatform] || 'fa-solid fa-magnifying-glass'} search-bar-icon`;
            input.focus();
        });
    });

    // Close drawer
    btnCloseDrawer.addEventListener('click', () => {
        drawer.classList.remove('active');
    });

    document.addEventListener('click', (e) => {
        if (!drawer.contains(e.target) && !document.querySelector('.header-search-wrap').contains(e.target)) {
            drawer.classList.remove('active');
        }
    });

    const handleSearchOrAdd = async () => {
        const query = input.value.trim();
        if (!query) {
            showToast('Vui lòng nhập từ khóa hoặc dán link bài hát!', 'error');
            return;
        }

        const isDirectUrl = query.startsWith('http://') || query.startsWith('https://');

        // If it's a direct URL or URL mode is chosen, add to playlist directly
        if (isDirectUrl || currentPlatform === 'url') {
            const originalBtnHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tải...';
            btn.disabled = true;

            try {
                const res = await API.addTrack(query, currentPlatform);
                input.value = '';
                showToast(`Đã thêm ${res.added.length} bài hát vào danh sách phát!`, 'success');
                await refreshPlaylist();
                drawer.classList.remove('active');
            } catch (e) {
                showToast(`Lỗi thêm bài: ${e.message}`, 'error');
            } finally {
                btn.innerHTML = originalBtnHTML;
                btn.disabled = false;
            }
            return;
        }

        // Otherwise, perform multi-platform search
        const originalBtnHTML = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang tìm...';
        btn.disabled = true;

        try {
            const res = await API.search(query, currentPlatform, 8);
            const results = res.results || [];
            
            drawerHeading.innerText = `Kết Quả Tìm Kiếm: "${query}" (${results.length} bài)`;
            drawerList.innerHTML = '';

            if (!results.length) {
                drawerList.innerHTML = `<div class="empty-state" style="padding: 16px;"><p>Không tìm thấy kết quả phù hợp trên ${currentPlatform.toUpperCase()}.</p></div>`;
            } else {
                results.forEach(item => {
                    const card = document.createElement('div');
                    card.className = 'search-result-card';
                    const thumb = item.thumbnail || 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=120&auto=format&fit=crop&q=60';

                    card.innerHTML = `
                        <div class="res-left">
                            <div class="res-thumb">
                                <img src="${escapeHtml(thumb)}" alt="" data-cover>
                            </div>
                            <div class="res-info">
                                <div class="res-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                                <div class="res-meta">
                                    <span class="res-platform-tag tag-${escapeHtml(item.platform)}">${escapeHtml(item.platform)}</span>
                                    <span>${escapeHtml(item.uploader)} &bull; ${escapeHtml(item.duration_str)}</span>
                                </div>
                            </div>
                        </div>
                        <div class="res-actions">
                            <button class="btn-xs btn-glass-accent btn-play-now" title="Phát bài này ngay lập tức">
                                <i class="fa-solid fa-play"></i> Phát Ngay
                            </button>
                            <button class="btn-xs btn-glass-primary btn-add-queue" title="Thêm bài này vào danh sách phát">
                                <i class="fa-solid fa-plus"></i> Thêm Bài
                            </button>
                        </div>
                    `;

                    // Play Now button
                    card.querySelector('.btn-play-now').addEventListener('click', async () => {
                        const button = card.querySelector('.btn-play-now');
                        button.disabled = true;
                        try {
                            showToast('Đang chuẩn bị phát nhạc…', 'info');
                            const added = await API.addDirectTrack(item);
                            await refreshPlaylist();
                            await API.play(added.track.id);
                            drawer.classList.remove('active');
                        } catch (error) {
                            showToast(error.message, 'error');
                        } finally {
                            button.disabled = false;
                        }
                    });

                    // Add to Playlist button
                    card.querySelector('.btn-add-queue').addEventListener('click', async () => {
                        await API.addDirectTrack(item);
                        await refreshPlaylist();
                        showToast(`Đã thêm "${item.title}" vào danh sách phát!`, 'success');
                    });

                    drawerList.appendChild(card);
                });
            }

            drawer.classList.add('active');
        } catch (e) {
            showToast(`Lỗi tìm kiếm: ${e.message}`, 'error');
        } finally {
            btn.innerHTML = originalBtnHTML;
            btn.disabled = false;
        }
    };

    btn.addEventListener('click', handleSearchOrAdd);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleSearchOrAdd();
    });
}

// --- Player Controls UI & Logic ---
function initPlayerControls() {
    const btnPlayPause = document.getElementById('btn-play-pause');
    const btnStop = document.getElementById('btn-stop');
    const btnNext = document.getElementById('btn-next');
    const btnPrev = document.getElementById('btn-prev');
    const btnRepeat = document.getElementById('btn-repeat');
    const btnShuffle = document.getElementById('btn-shuffle');
    const volSlider = document.getElementById('vol-slider');
    const volText = document.getElementById('vol-text');
    const progressWrap = document.getElementById('progress-bar-wrap');

    // Play / Pause
    btnPlayPause.addEventListener('click', async () => {
        if (AppState.playerState.is_playing && !AppState.playerState.is_paused) {
            try {
                await API.pause();
                showToast('Đã tạm dừng', 'info');
            } catch (e) {
                showToast(`Lỗi tạm dừng: ${e.message}`, 'error');
            }
        } else {
            const hasTracks = AppState.playlist && AppState.playlist.length > 0;
            if (!hasTracks) {
                showToast('Danh sách phát trống! Hãy dán link hoặc tìm bài hát ở trên.', 'error');
                return;
            }

            try {
                document.getElementById('icon-play-pause').className = 'fa-solid fa-spinner fa-spin';
                const res = await API.play();
                if (res.status === 'ok') {
                    showToast(`Đang phát: ${res.playing ? res.playing.title : 'Âm nhạc'}`, 'success');
                } else if (res.status === 'resumed') {
                    showToast('Tiếp tục phát nhạc', 'info');
                } else if (res.status === 'empty_playlist') {
                    showToast('Chưa có bài hát nào được chọn trong playlist!', 'error');
                }
            } catch (e) {
                showToast(`Lỗi phát nhạc: ${e.message}`, 'error');
            }
        }
    });

    // Stop
    btnStop.addEventListener('click', async () => {
        await API.stop();
        showToast('Đã dừng phát nhạc', 'info');
    });

    // Next / Prev
    btnNext.addEventListener('click', async () => {
        await API.next();
    });
    btnPrev.addEventListener('click', async () => {
        await API.prev();
    });

    // Repeat Mode
    btnRepeat.addEventListener('click', async () => {
        const modes = ['off', 'one', 'all'];
        const currentMode = AppState.playerState.repeat_mode || 'off';
        const nextIdx = (modes.indexOf(currentMode) + 1) % modes.length;
        const nextMode = modes[nextIdx];
        await API.setRepeat(nextMode);
        AppState.playerState.repeat_mode = nextMode;
        updateRepeatUI(nextMode);
    });

    // Shuffle
    btnShuffle.addEventListener('click', async () => {
        const nextShuffle = !AppState.playerState.shuffle;
        await API.setShuffle(nextShuffle);
        AppState.playerState.shuffle = nextShuffle;
        btnShuffle.classList.toggle('active', nextShuffle);
    });

    // Volume
    volSlider.addEventListener('input', async (e) => {
        const val = parseFloat(e.target.value);
        volText.innerText = `${Math.round(val)}%`;
        await API.setVolume(val / 100);
    });

    // Progress Seek Bar
    progressWrap.addEventListener('click', async (e) => {
        if (!AppState.playerState.current_track) return;
        const rect = progressWrap.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const ratio = Math.max(0, Math.min(1, clickX / rect.width));
        const duration = AppState.playerState.current_track.duration || 180;
        const seekSeconds = ratio * duration;
        await API.seek(seekSeconds);
    });

    // Refresh rooms live button
    document.getElementById('btn-refresh-rooms-live').addEventListener('click', async () => {
        AppState.rooms = await API.getRooms();
        renderRooms();
        updateActiveChannelsLiveList();
    });
}

function updatePlayerUI(state) {
    AppState.playerState = state;

    const iconPlayPause = document.getElementById('icon-play-pause');
    const discVinyl = document.getElementById('disc-vinyl');
    const titleEl = document.getElementById('now-playing-title');
    const artistEl = document.getElementById('now-playing-artist');
    const coverImg = document.getElementById('now-playing-cover');
    const timeCurrent = document.getElementById('time-current');
    const timeTotal = document.getElementById('time-total');
    const progressFill = document.getElementById('progress-fill');
    const progressThumb = document.getElementById('progress-thumb');
    const headerVuFill = document.getElementById('header-vu-fill');

    const isPlaying = state.is_playing && !state.is_paused;

    // Play/Pause icon & vinyl spin
    if (isPlaying) {
        iconPlayPause.className = 'fa-solid fa-pause';
        discVinyl.classList.add('spinning');
    } else {
        iconPlayPause.className = 'fa-solid fa-play';
        discVinyl.classList.remove('spinning');
    }

    // Track Metadata
    if (state.current_track) {
        titleEl.innerText = state.current_track.title || 'Unknown Title';
        artistEl.innerText = state.current_track.uploader || 'Unknown Artist';
        if (state.current_track.thumbnail) {
            coverImg.src = state.current_track.thumbnail;
        }

        const duration = state.current_track.duration || 0;
        const pos = state.position || 0;

        timeCurrent.innerText = formatTime(pos);
        timeTotal.innerText = formatTime(duration);

        const ratio = duration > 0 ? Math.min(100, (pos / duration) * 100) : 0;
        progressFill.style.width = `${ratio}%`;
        progressThumb.style.left = `${ratio}%`;
    } else {
        titleEl.innerText = 'Chưa phát bài hát nào';
        artistEl.innerText = 'Chọn bài từ danh sách hoặc dán link';
        timeCurrent.innerText = '00:00';
        timeTotal.innerText = '00:00';
        progressFill.style.width = '0%';
        progressThumb.style.left = '0%';
    }

    // Visualizer data
    if (visualizerInstance && state.spectrum) {
        visualizerInstance.updateData(state.spectrum, state.vu_meter);
    }

    // Top VU Meter
    const vuPercent = Math.min(100, (state.vu_meter || 0) * 100);
    if (headerVuFill) {
        headerVuFill.style.width = `${vuPercent}%`;
    }

    // Repeat & Shuffle UI
    updateRepeatUI(state.repeat_mode);
    const btnShuffle = document.getElementById('btn-shuffle');
    if (btnShuffle) {
        btnShuffle.classList.toggle('active', !!state.shuffle);
    }

    // Badges & Counters
    document.getElementById('playlist-count-badge').innerText = state.total_tracks_count || 0;
    document.getElementById('pl-selected-count').innerText = state.selected_tracks_count || 0;
    document.getElementById('pl-total-count').innerText = state.total_tracks_count || 0;
    document.getElementById('sb-selected-rooms').innerText = state.selected_rooms_count || 0;
    document.getElementById('sb-active-rooms').innerText = state.connected_rooms_count || 0;
    document.getElementById('rooms-count-badge').innerText = state.connected_rooms_count || 0;
    document.getElementById('room-selected-stat').innerText = state.selected_rooms_count || 0;

    // Highlight currently playing item in playlist list
    highlightActivePlaylistItem(state.current_track ? state.current_track.id : null);
    updateActiveChannelsLiveList();
    updateQueuePreviewList();
}

function updateRepeatUI(mode) {
    const badge = document.getElementById('repeat-badge');
    const btn = document.getElementById('btn-repeat');
    if (!badge || !btn) return;
    
    if (mode === 'one') {
        badge.innerText = '1';
        btn.classList.add('active');
    } else if (mode === 'all') {
        badge.innerText = 'ALL';
        btn.classList.add('active');
    } else {
        badge.innerText = 'OFF';
        btn.classList.remove('active');
    }
}

// --- Playlist Management ---
function initPlaylistActions() {
    // Play selected
    document.getElementById('btn-play-selected').addEventListener('click', async () => {
        const selected = AppState.playlist.filter(p => p.selected);
        if (!selected.length) {
            showToast('Hãy tích chọn ít nhất 1 bài hát để phát!', 'error');
            return;
        }
        await API.play(selected[0].id);
        showToast(`Bắt đầu phát ${selected.length} bài hát đã chọn!`, 'success');
    });

    // Select All
    document.getElementById('btn-select-all-tracks').addEventListener('click', async () => {
        await API.selectAllTracks(true);
        AppState.playlist.forEach(p => p.selected = true);
        renderPlaylist();
    });

    // Deselect All
    document.getElementById('btn-deselect-all-tracks').addEventListener('click', async () => {
        await API.selectAllTracks(false);
        AppState.playlist.forEach(p => p.selected = false);
        renderPlaylist();
    });

    // Clear All
    document.getElementById('btn-clear-playlist').addEventListener('click', async () => {
        if (!confirm('Bạn có chắc muốn xóa toàn bộ danh sách phát?')) return;
        await API.clearPlaylist();
        AppState.playlist = [];
        renderPlaylist();
        showToast('Đã xóa danh sách phát', 'info');
    });

    // Search filter
    const searchInput = document.getElementById('playlist-search-input');
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        renderPlaylist(query);
    });
}

async function refreshPlaylist() {
    AppState.playlist = await API.getPlaylist();
    renderPlaylist();
}

function renderPlaylist(searchQuery = '') {
    const container = document.getElementById('playlist-items-list');
    container.innerHTML = '';

    const filtered = AppState.playlist.filter(item => {
        if (!searchQuery) return true;
        return (item.title || '').toLowerCase().includes(searchQuery) ||
               (item.uploader || '').toLowerCase().includes(searchQuery);
    });

    if (!filtered.length) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-music empty-icon"></i>
                <p>Danh sách bài hát trống.</p>
                <span class="empty-sub">Dán link YouTube / SoundCloud hoặc Audio URL ở thanh tìm kiếm phía trên để thêm bài!</span>
            </div>
        `;
        return;
    }

    filtered.forEach((track, index) => {
        const row = document.createElement('div');
        row.className = 'playlist-item-row';
        row.setAttribute('data-id', track.id);

        const isCurrentPlaying = AppState.playerState.current_track && AppState.playerState.current_track.id === track.id;
        if (isCurrentPlaying) row.classList.add('is-active');

        const thumb = track.thumbnail || 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=200&auto=format&fit=crop&q=60';

        row.innerHTML = `
            <div class="item-left">
                <input type="checkbox" class="custom-checkbox track-chk" ${track.selected ? 'checked' : ''} data-id="${escapeHtml(track.id)}">
                <div class="item-thumb">
                    <img src="${escapeHtml(thumb)}" alt="" data-cover>
                </div>
                <div class="item-info">
                    <div class="item-title" title="${escapeHtml(track.title)}">${escapeHtml(track.title)}</div>
                    <div class="item-sub">${escapeHtml(track.uploader || 'Audio')} &bull; ${escapeHtml(track.duration_str || formatTime(track.duration))}</div>
                </div>
            </div>
            <div class="item-right">
                <button class="btn-xs btn-outline-glass btn-play-track" data-id="${escapeHtml(track.id)}" title="Phát bài này ngay">
                    <i class="fa-solid fa-play"></i>
                </button>
                <button class="btn-xs btn-glass-danger btn-delete-track" data-id="${escapeHtml(track.id)}" title="Xóa bài">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;

        // Checkbox event
        const chk = row.querySelector('.track-chk');
        chk.addEventListener('change', async (e) => {
            const isChecked = e.target.checked;
            track.selected = isChecked;
            await API.selectTrack(track.id, isChecked);
            updateSelectedCounts();
        });

        // Play individual track
        row.querySelector('.btn-play-track').addEventListener('click', async () => {
            try {
                await API.play(track.id);
                showToast(`Đang phát: ${track.title}`, 'info');
            } catch (error) {
                showToast(error.message, 'error');
            }
        });

        // Delete track
        row.querySelector('.btn-delete-track').addEventListener('click', async () => {
            await API.deleteTrack(track.id);
            AppState.playlist = AppState.playlist.filter(p => p.id !== track.id);
            renderPlaylist(searchQuery);
            showToast('Đã xóa bài hát khỏi danh sách', 'info');
        });

        container.appendChild(row);
    });

    updateSelectedCounts();
}

function highlightActivePlaylistItem(currentTrackId) {
    const rows = document.querySelectorAll('.playlist-item-row');
    rows.forEach(row => {
        if (row.getAttribute('data-id') === currentTrackId) {
            row.classList.add('is-active');
        } else {
            row.classList.remove('is-active');
        }
    });
}

function updateSelectedCounts() {
    const selectedCount = AppState.playlist.filter(p => p.selected).length;
    document.getElementById('pl-selected-count').innerText = selectedCount;
    document.getElementById('pl-total-count').innerText = AppState.playlist.length;
}

// --- Voice Rooms Management ---
function initRoomActions() {
    const modal = document.getElementById('modal-room');
    const btnOpenAdd = document.getElementById('btn-open-add-room-modal');
    const btnCloseModal = document.getElementById('btn-close-modal-room');
    const btnCancelModal = document.getElementById('btn-cancel-modal-room');
    const btnSaveRoom = document.getElementById('btn-save-room');

    btnOpenAdd.addEventListener('click', () => {
        document.getElementById('modal-room-title').innerHTML = '<i class="fa-solid fa-tower-broadcast"></i> Thêm Kênh Thoại Mới';
        document.getElementById('room-edit-id').value = '';
        document.getElementById('room-input-name').value = '';
        document.getElementById('room-input-guild').value = '';
        document.getElementById('room-input-channel').value = '';
        document.getElementById('room-input-token').value = '';
        modal.classList.add('active');
    });

    const closeModal = () => modal.classList.remove('active');
    btnCloseModal.addEventListener('click', closeModal);
    btnCancelModal.addEventListener('click', closeModal);

    // Save Room
    btnSaveRoom.addEventListener('click', async () => {
        const id = document.getElementById('room-edit-id').value;
        const name = document.getElementById('room-input-name').value.trim();
        const guild_id = document.getElementById('room-input-guild').value.trim();
        const channel_id = document.getElementById('room-input-channel').value.trim();
        const bot_token = document.getElementById('room-input-token').value.trim();

        if (!guild_id || !channel_id) {
            showToast('Vui lòng nhập Guild ID và Voice Channel ID!', 'error');
            return;
        }

        try {
            if (id) {
                await API.updateRoom(id, { name, guild_id, channel_id, bot_token });
                showToast('Đã cập nhật kênh thoại!', 'success');
            } else {
                await API.addRoom({ name, guild_id, channel_id, bot_token });
                showToast('Đã thêm kênh thoại thành công!', 'success');
            }
            closeModal();
            AppState.rooms = await API.getRooms();
            renderRooms();
        } catch (e) {
            showToast(`Lỗi: ${e.message}`, 'error');
        }
    });

    // Select All Rooms
    document.getElementById('btn-select-all-rooms').addEventListener('click', async () => {
        await API.selectAllRooms(true);
        AppState.rooms.forEach(r => r.selected = true);
        renderRooms();
    });

    // Deselect All Rooms
    document.getElementById('btn-deselect-all-rooms').addEventListener('click', async () => {
        await API.selectAllRooms(false);
        AppState.rooms.forEach(r => r.selected = false);
        renderRooms();
    });

    // Connect All Selected
    const handleConnectAll = async () => {
        showToast('Đang kết nối tới tất cả kênh thoại đã chọn...', 'info');
        await API.connectAllSelectedRooms();
        AppState.rooms = await API.getRooms();
        renderRooms();
    };

    document.getElementById('btn-connect-all-selected').addEventListener('click', handleConnectAll);
    document.getElementById('sb-quick-connect-btn').addEventListener('click', handleConnectAll);

    // Disconnect All
    document.getElementById('btn-disconnect-all').addEventListener('click', async () => {
        await API.disconnectAllRooms();
        AppState.rooms = await API.getRooms();
        renderRooms();
        showToast('Đã ngắt kết nối tất cả kênh thoại!', 'info');
    });
}

function updateRoomsState(updatedRooms) {
    AppState.rooms = updatedRooms;
    // Update live badges, cards and action buttons
    updatedRooms.forEach(r => {
        const card = document.querySelector(`.room-card[data-id="${r.id}"]`);
        if (card) {
            card.className = `room-card status-${r.status || 'disconnected'}`;
            const badge = card.querySelector('.room-status-badge');
            if (badge) {
                badge.className = `room-status-badge badge-${r.status || 'disconnected'}`;
                badge.innerHTML = getStatusBadgeHTML(r.status, r.ping);
            }
            const btnsLeft = card.querySelector('.room-btns-left');
            if (btnsLeft) {
                const isOnline = r.status === 'connected' || r.status === 'playing';
                const hasDcBtn = btnsLeft.querySelector('.btn-dc-room');
                if (isOnline && !hasDcBtn) {
                    btnsLeft.innerHTML = `
                        <button class="btn-xs btn-glass-danger btn-dc-room" data-id="${r.id}">
                            <i class="fa-solid fa-power-off"></i> Ngắt Kết Nối
                        </button>
                    `;
                    btnsLeft.querySelector('.btn-dc-room').addEventListener('click', async () => {
                        await API.disconnectRoom(r.id);
                        showToast(`Đã ngắt kết nối ${r.name}`, 'info');
                    });
                } else if (!isOnline && hasDcBtn) {
                    btnsLeft.innerHTML = `
                        <button class="btn-xs btn-primary-glass btn-conn-room" data-id="${r.id}">
                            <i class="fa-solid fa-plug"></i> Kết Nối
                        </button>
                    `;
                    btnsLeft.querySelector('.btn-conn-room').addEventListener('click', async () => {
                        btnsLeft.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                        await API.connectRoom(r.id);
                    });
                }
            }
        }
    });
    updateActiveChannelsLiveList();
}

function getStatusBadgeHTML(status, ping) {
    if (status === 'playing') {
        return `<span class="pulse-dot"></span> Đang Phát (${ping || 20}ms)`;
    } else if (status === 'connected') {
        return `<i class="fa-solid fa-check"></i> Đã Kết Nối (${ping || 20}ms)`;
    } else if (status === 'connecting') {
        return `<i class="fa-solid fa-spinner fa-spin"></i> Đang Kết Nối...`;
    } else if (status.startsWith('error')) {
        return `<i class="fa-solid fa-triangle-exclamation"></i> Lỗi Kết Nối`;
    }
    return `<i class="fa-regular fa-circle"></i> Chưa Kết Nối`;
}

function renderRooms() {
    const grid = document.getElementById('rooms-grid');
    grid.innerHTML = '';

    if (!AppState.rooms.length) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <i class="fa-solid fa-tower-broadcast empty-icon"></i>
                <p>Chưa có kênh thoại Discord nào được thêm.</p>
                <span class="empty-sub">Nhấn <strong>Thêm Kênh Thoại Mới</strong> để kết nối vào Voice Channel của bạn!</span>
            </div>
        `;
        return;
    }

    AppState.rooms.forEach(room => {
        const card = document.createElement('div');
        card.className = `room-card status-${room.status || 'disconnected'}`;
        card.setAttribute('data-id', room.id);

        card.innerHTML = `
            <div class="room-card-header">
                <div class="room-name-wrap">
                    <input type="checkbox" class="custom-checkbox room-chk" ${room.selected ? 'checked' : ''} data-id="${room.id}" title="Tích chọn để phát nhạc vào phòng này">
                    <h4>${escapeHtml(room.name)}</h4>
                </div>
                <div class="room-status-badge badge-${room.status || 'disconnected'}">
                    ${getStatusBadgeHTML(room.status, room.ping)}
                </div>
            </div>

            <div class="room-card-meta">
                <span><i class="fa-solid fa-server"></i> Server ID: <code>${room.guild_id}</code></span>
                <span><i class="fa-solid fa-volume-high"></i> Voice ID: <code>${room.channel_id}</code></span>
            </div>

            <div class="room-card-actions">
                <div class="room-btns-left">
                    ${room.status === 'connected' || room.status === 'playing' ? `
                        <button class="btn-xs btn-glass-danger btn-dc-room" data-id="${room.id}">
                            <i class="fa-solid fa-power-off"></i> Ngắt Kết Nối
                        </button>
                    ` : `
                        <button class="btn-xs btn-primary-glass btn-conn-room" data-id="${room.id}">
                            <i class="fa-solid fa-plug"></i> Kết Nối
                        </button>
                    `}
                </div>
                <div class="room-btns-right" data-owner-only>
                    <button class="btn-xs btn-outline-glass btn-edit-room" data-id="${room.id}" title="Chỉnh sửa">
                        <i class="fa-solid fa-pen"></i>
                    </button>
                    <button class="btn-xs btn-glass-danger btn-del-room" data-id="${room.id}" title="Xóa phòng">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        `;

        // Checkbox toggle
        card.querySelector('.room-chk').addEventListener('change', async (e) => {
            const isChecked = e.target.checked;
            room.selected = isChecked;
            await API.selectRoom(room.id, isChecked);
            document.getElementById('room-selected-stat').innerText = AppState.rooms.filter(r => r.selected).length;
            document.getElementById('sb-selected-rooms').innerText = AppState.rooms.filter(r => r.selected).length;
        });

        // Connect room
        const connBtn = card.querySelector('.btn-conn-room');
        if (connBtn) {
            connBtn.addEventListener('click', async () => {
                connBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                const res = await API.connectRoom(room.id);
                if (res.status === 'ok') {
                    showToast(`Đã kết nối vào ${room.name}!`, 'success');
                } else {
                    showToast(`Kết nối thất bại vào ${room.name}. Kiểm tra lại Bot Token và Channel ID!`, 'error');
                }
                AppState.rooms = await API.getRooms();
                renderRooms();
            });
        }

        // Disconnect room
        const dcBtn = card.querySelector('.btn-dc-room');
        if (dcBtn) {
            dcBtn.addEventListener('click', async () => {
                await API.disconnectRoom(room.id);
                showToast(`Đã ngắt kết nối ${room.name}`, 'info');
                AppState.rooms = await API.getRooms();
                renderRooms();
            });
        }

        // Edit room
        card.querySelector('.btn-edit-room').addEventListener('click', () => {
            document.getElementById('modal-room-title').innerHTML = '<i class="fa-solid fa-pen"></i> Chỉnh Sửa Kênh Thoại';
            document.getElementById('room-edit-id').value = room.id;
            document.getElementById('room-input-name').value = room.name || '';
            document.getElementById('room-input-guild').value = room.guild_id || '';
            document.getElementById('room-input-channel').value = room.channel_id || '';
            document.getElementById('room-input-token').value = room.bot_token || '';
            document.getElementById('modal-room').classList.add('active');
        });

        // Delete room
        card.querySelector('.btn-del-room').addEventListener('click', async () => {
            if (!confirm(`Bạn có chắc muốn xóa kênh thoại "${room.name}"?`)) return;
            await API.deleteRoom(room.id);
            AppState.rooms = AppState.rooms.filter(r => r.id !== room.id);
            renderRooms();
            showToast('Đã xóa kênh thoại!', 'info');
        });

        grid.appendChild(card);
    });
}

function updateActiveChannelsLiveList() {
    const container = document.getElementById('active-rooms-live-list');
    if (!container) return;

    const activeRooms = AppState.rooms.filter(r => r.status === 'connected' || r.status === 'playing');
    if (!activeRooms.length) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-tower-broadcast empty-icon"></i>
                <p>Chưa có kênh thoại nào được kết nối.</p>
                <span class="empty-sub">Hãy vào mục <strong>Kênh Thoại</strong> để thêm và kết nối phòng!</span>
            </div>
        `;
        return;
    }

    container.innerHTML = activeRooms.map(r => `
        <div class="active-channel-card">
            <div class="channel-info-left">
                <span class="pulse-dot"></span>
                <div>
                    <strong style="font-size: 13px;">${escapeHtml(r.name)}</strong>
                    <div style="font-size: 11px; color: var(--text-dim);">Ch.ID: ${r.channel_id}</div>
                </div>
            </div>
            <div class="badge-playing" style="font-size: 10.5px; padding: 2px 8px; border-radius: 9999px;">
                ${r.status === 'playing' ? 'Đang Stream' : 'Sẵn Sàng'} (${r.ping || 20}ms)
            </div>
        </div>
    `).join('');
}

function updateQueuePreviewList() {
    const container = document.getElementById('queue-preview-list');
    const countEl = document.getElementById('queue-preview-count');
    if (!container) return;

    const albumQueue = AppState.playerState.album_queue;
    const selectedTracks = albumQueue ? albumQueue.upcoming : AppState.playlist.filter(p => p.selected);
    document.getElementById('queue-preview-heading').textContent = albumQueue ? `Album · ${albumQueue.name}` : 'Hàng Đợi Tiếp Theo';
    countEl.innerText = albumQueue ? `${albumQueue.remaining} bài tiếp theo` : `${selectedTracks.length} bài đã chọn`;

    if (!selectedTracks.length) {
        container.innerHTML = `<span style="font-size: 11px; color: var(--text-dim); text-align: center; display: block; padding: 8px;">${albumQueue ? 'Đã đến bài cuối của album' : 'Không có bài nào được chọn trong hàng đợi'}</span>`;
        return;
    }

    container.innerHTML = selectedTracks.slice(0, 5).map((t, idx) => `
        <div class="preview-item">
            <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80%;">
                ${idx + 1}. ${escapeHtml(t.title)}
            </span>
            <span style="color: var(--text-dim); font-size: 11px;">${escapeHtml(t.duration_str || formatTime(t.duration))}</span>
        </div>
    `).join('');
}

// --- Backgrounds & Settings ---
function initSettingsAndBackgrounds() {
    const sliderBlur = document.getElementById('slider-blur');
    const sliderBrightness = document.getElementById('slider-brightness');
    const sliderOpacity = document.getElementById('slider-opacity');
    const labelBlur = document.getElementById('label-blur-val');
    const labelBright = document.getElementById('label-bright-val');
    const labelOpacity = document.getElementById('label-opacity-val');

    // Blur slider
    sliderBlur.addEventListener('input', (e) => {
        const val = e.target.value;
        labelBlur.innerText = `${val}px`;
        document.documentElement.style.setProperty('--glass-blur', `${val}px`);
        API.updateConfig({ bg_blur: parseInt(val) });
    });

    // Brightness slider
    sliderBrightness.addEventListener('input', (e) => {
        const val = e.target.value;
        labelBright.innerText = `${val}%`;
        document.documentElement.style.setProperty('--glass-brightness', `${val / 100}`);
        API.updateConfig({ bg_brightness: parseInt(val) });
    });

    // Glass Opacity slider
    sliderOpacity.addEventListener('input', (e) => {
        const val = e.target.value;
        labelOpacity.innerText = `${val}%`;
        document.documentElement.style.setProperty('--glass-opacity', `${val / 100}`);
        API.updateConfig({ glass_opacity: parseInt(val) });
    });

    // Bot Token Eye Toggle
    const btnEye = document.getElementById('btn-toggle-token-eye');
    const tokenInput = document.getElementById('setting-global-token');
    btnEye.addEventListener('click', () => {
        if (tokenInput.type === 'password') {
            tokenInput.type = 'text';
            btnEye.innerHTML = '<i class="fa-regular fa-eye-slash"></i>';
        } else {
            tokenInput.type = 'password';
            btnEye.innerHTML = '<i class="fa-regular fa-eye"></i>';
        }
    });

    // Save Settings
    document.getElementById('btn-save-settings').addEventListener('click', async () => {
        const global_token = tokenInput.value.trim();
        const bitrate = parseInt(document.getElementById('setting-bitrate').value);

        try {
            await API.updateConfig({ global_token, bitrate });
            showToast('Đã lưu cấu hình Bot Token thành công!', 'success');
        } catch (e) {
            showToast(`Lỗi lưu cấu hình: ${e.message}`, 'error');
        }
    });
}

async function loadBackgroundGallery() {
    const gallery = document.getElementById('bg-gallery-grid');
    if (!gallery) return;

    try {
        const data = await API.getBackgrounds();
        gallery.innerHTML = '';

        data.files.forEach(filename => {
            const card = document.createElement('div');
            card.className = `bg-item-card ${data.current === filename ? 'active' : ''}`;
            card.innerHTML = `<img src="/background/${filename}" alt="${filename}">`;

            card.addEventListener('click', async () => {
                document.querySelectorAll('.bg-item-card').forEach(c => c.classList.remove('active'));
                card.classList.add('active');

                applyBackground(filename);
                await API.selectBackground(filename);
                showToast(`Đã đổi hình nền: ${filename}`, 'info');
            });

            gallery.appendChild(card);
        });
    } catch (e) {
        console.error('Error loading background gallery:', e);
    }
}

function applyBackground(filename) {
    const bgLayer = document.getElementById('bg-layer');
    if (bgLayer) {
        bgLayer.style.backgroundImage = `url('/background/${filename}')`;
    }
}

function applyConfigToUI(config) {
    if (!config) return;
    document.body.classList.toggle('shared-mode', Boolean(config.shared));
    document.getElementById('tab-btn-albums').hidden = !config.albums_enabled;

    if (config.current_background) {
        applyBackground(config.current_background);
    }

    if (config.bg_blur !== undefined) {
        document.documentElement.style.setProperty('--glass-blur', `${config.bg_blur}px`);
        document.getElementById('slider-blur').value = config.bg_blur;
        document.getElementById('label-blur-val').innerText = `${config.bg_blur}px`;
    }

    if (config.bg_brightness !== undefined) {
        document.documentElement.style.setProperty('--glass-brightness', `${config.bg_brightness / 100}`);
        document.getElementById('slider-brightness').value = config.bg_brightness;
        document.getElementById('label-bright-val').innerText = `${config.bg_brightness}%`;
    }

    if (config.glass_opacity !== undefined) {
        document.documentElement.style.setProperty('--glass-opacity', `${config.glass_opacity / 100}`);
        document.getElementById('slider-opacity').value = config.glass_opacity;
        document.getElementById('label-opacity-val').innerText = `${config.glass_opacity}%`;
    }

    if (config.global_token) {
        document.getElementById('setting-global-token').value = config.global_token;
    }

    if (config.bitrate) {
        document.getElementById('setting-bitrate').value = config.bitrate;
    }

    if (config.volume !== undefined) {
        const volVal = Math.round(config.volume * 100);
        document.getElementById('vol-slider').value = volVal;
        document.getElementById('vol-text').innerText = `${volVal}%`;
    }
}
