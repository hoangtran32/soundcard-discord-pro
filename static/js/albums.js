function initAlbums() {
    const byId = id => document.getElementById(id);
    const panel = byId('tab-albums');
    const feedback = byId('album-feedback');
    const profileForm = byId('album-profile-form');
    const logout = byId('album-logout');
    const picker = byId('album-picker');
    const select = byId('album-select');
    const details = byId('album-details');
    const play = byId('album-play');
    const list = byId('album-tracks');
    let username = null;
    let album = null;
    let busy = false;

    function post(path, body = {}) {
        return API.request(path, { method: 'POST', body: JSON.stringify(body) });
    }

    function albumPath(id) {
        return `/api/albums/${encodeURIComponent(id)}`;
    }

    function notify(message) {
        feedback.textContent = message || '';
        feedback.hidden = !message;
    }

    async function run(action) {
        if (busy) return;
        busy = true;
        const controls = panel.querySelectorAll('button:enabled, input:enabled, select:enabled');
        controls.forEach(control => { control.disabled = true; });
        notify('Đang xử lý…');
        try {
            notify(await action());
        } catch (error) {
            notify(error.message);
        } finally {
            controls.forEach(control => { control.disabled = false; });
            play.disabled = !album?.tracks.length;
            busy = false;
        }
    }

    function button(label, style, action, trackName) {
        const element = document.createElement('button');
        element.type = 'button';
        element.className = style;
        element.textContent = label;
        element.setAttribute('aria-label', `${label} ${trackName}`);
        element.addEventListener('click', () => run(action));
        return element;
    }

    async function playAlbum(trackId) {
        await post(`${albumPath(album.id)}/play`, { track_id: trackId });
        showToast(`Đang phát album “${album.name}”`, 'success');
        byId('tab-btn-playing').click();
    }

    function renderAlbum(selected) {
        album = selected;
        details.hidden = !album;
        list.replaceChildren();
        byId('album-empty').hidden = Boolean(album?.tracks.length);
        for (const track of album?.tracks || []) {
            const entry = document.createElement('li');
            const row = document.createElement('div');
            row.className = 'album-track-row';
            const title = document.createElement('span');
            title.textContent = track.title || 'Bài hát chưa có tên';
            const actions = document.createElement('div');
            actions.className = 'album-actions';
            actions.append(
                button('Phát từ bài', 'btn-xs btn-outline-glass', () => playAlbum(track.id), title.textContent),
                button('Xóa bài', 'btn-xs btn-glass-danger', async () => {
                    renderAlbum(await API.request(`${albumPath(album.id)}/tracks/${track.id}`, { method: 'DELETE' }));
                    select.selectedOptions[0].textContent = albumLabel(album.name, album.tracks.length);
                    return 'Đã xóa bài khỏi album.';
                }, title.textContent)
            );
            row.append(title, actions);
            entry.append(row);
            list.append(entry);
        }
    }

    function albumLabel(name, count) {
        return `${name} · ${count} bài`;
    }

    async function refreshAlbums(preferredId) {
        const albums = await API.request('/api/albums');
        select.replaceChildren(...albums.map(item => new Option(albumLabel(item.name, item.track_count), item.id)));
        picker.hidden = !albums.length;
        const preferred = albums.find(item => item.id === preferredId) || albums[0];
        if (!preferred) {
            renderAlbum(null);
            return;
        }
        select.value = preferred.id;
        renderAlbum(await API.request(albumPath(preferred.id)));
    }

    async function loadProfile(profile) {
        const preferredId = username === profile.username ? album?.id : undefined;
        username = profile.username;
        profileForm.hidden = Boolean(username);
        byId('album-library').hidden = !username;
        logout.hidden = !username;
        byId('album-profile-name').textContent = username ? `Hồ sơ: ${username}` : '';
        if (username) await refreshAlbums(preferredId);
        else {
            select.replaceChildren();
            picker.hidden = true;
            renderAlbum(null);
        }
    }

    function savedTracks(result) {
        renderAlbum(result.album);
        select.selectedOptions[0].textContent = albumLabel(album.name, album.tracks.length);
        return result.added ? `Đã lưu ${result.added} bài vào album.` : 'Các bài này đã có trong album.';
    }

    byId('tab-btn-albums').addEventListener('click', () => run(async () => {
        await loadProfile(await API.request('/api/profile'));
    }));

    profileForm.addEventListener('submit', event => {
        event.preventDefault();
        const action = event.submitter?.value === 'register' ? 'register' : 'login';
        const payload = Object.fromEntries(new FormData(profileForm));
        run(async () => {
            const profile = await post(`/api/profile/${action}`, payload);
            profileForm.reset();
            await loadProfile(profile);
        });
    });

    logout.addEventListener('click', () => run(async () => {
        await loadProfile(await post('/api/profile/logout'));
    }));

    const createForm = byId('album-create-form');
    createForm.addEventListener('submit', event => {
        event.preventDefault();
        const name = byId('album-name').value.trim();
        run(async () => {
            const created = await post('/api/albums', { name });
            createForm.reset();
            await refreshAlbums(created.id);
            return 'Đã tạo album.';
        });
    });

    select.addEventListener('change', () => run(async () => {
        try {
            renderAlbum(await API.request(albumPath(select.value)));
        } catch (error) {
            select.value = album?.id || '';
            throw error;
        }
    }));

    const trackForm = byId('album-track-form');
    trackForm.addEventListener('submit', event => {
        event.preventDefault();
        const query = byId('album-track-query').value.trim();
        run(async () => {
            const result = await post(`${albumPath(album.id)}/tracks/search`, { query });
            trackForm.reset();
            return savedTracks(result);
        });
    });

    byId('album-copy-tracks').addEventListener('click', () => run(async () => {
        const tracks = await API.getPlaylist();
        const ids = tracks.filter(track => track.selected).map(track => track.id);
        if (!ids.length) return 'Hãy tích chọn bài trong tab Danh Sách Nhạc trước.';
        return savedTracks(await post(`${albumPath(album.id)}/tracks/from-playlist`, { ids }));
    }));

    play.addEventListener('click', () => run(() => playAlbum()));
    byId('album-delete').addEventListener('click', () => {
        if (album && window.confirm(`Xóa album “${album.name}” và các bài đã lưu trong đó?`)) {
            run(async () => {
                await API.request(albumPath(album.id), { method: 'DELETE' });
                await refreshAlbums();
                return 'Đã xóa album.';
            });
        }
    });
}
