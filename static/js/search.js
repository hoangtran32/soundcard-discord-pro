function initMultiPlatformSearch() {
    const form = document.getElementById('music-search-form');
    const input = document.getElementById('quick-url-input');
    const submit = document.getElementById('btn-quick-search');
    const drawer = document.getElementById('search-results-drawer');
    const results = document.getElementById('search-results-list');
    const heading = document.getElementById('search-results-heading');
    const feedback = document.getElementById('search-feedback');
    const saveOptions = document.getElementById('search-save-options');
    const destination = document.getElementById('search-save-destination');
    const openAlbums = document.getElementById('search-open-albums');
    const more = document.getElementById('search-more');
    const pills = [...document.querySelectorAll('.platform-pill')];
    const viewFormat = new Intl.NumberFormat('vi-VN', { notation: 'compact', maximumFractionDigits: 1 });
    const sourceNames = { youtube: 'YouTube', soundcloud: 'SoundCloud', spotify: 'Spotify', url: 'Link nhạc' };
    const placeholders = {
        youtube: 'Tìm bài hoặc kênh trên YouTube…',
        soundcloud: 'Tìm bài trên SoundCloud…',
        spotify: 'Tìm bài hoặc dán link Spotify…',
        url: 'Dán link video hoặc bài hát…'
    };
    const isLink = query => /^(?:https?:\/\/|(?:(?:www|m|music|open|api)\.)?(?:youtube\.com|youtu\.be|soundcloud\.com|spotify\.com)\/)/i.test(query);
    const shown = new Set();
    let platform = 'youtube';
    let lastSearch;
    let searching = false;

    function toggleDrawer(visible, restoreFocus = false) {
        drawer.classList.toggle('active', visible);
        submit.setAttribute('aria-expanded', String(visible));
        if (restoreFocus) input.focus();
    }

    function report(message = '') {
        feedback.textContent = message;
        feedback.hidden = !message;
    }

    async function loadDestinations() {
        const wanted = destination.value;
        destination.replaceChildren(new Option('Danh sách chung', ''));
        saveOptions.hidden = !AppState.config.search_actions_enabled;
        if (saveOptions.hidden) return;
        destination.disabled = true;
        try {
            const profile = await API.request('/api/profile');
            const albums = profile.username ? await API.request('/api/albums') : [];
            if (albums.length) {
                const group = document.createElement('optgroup');
                group.label = 'Album cá nhân';
                albums.forEach(album => group.append(new Option(album.name, album.id)));
                destination.append(group);
                if (albums.some(album => album.id === wanted)) destination.value = wanted;
            }
            openAlbums.textContent = profile.username ? 'Quản lý album' : 'Đăng nhập album';
        } catch {
            openAlbums.textContent = 'Album cá nhân';
        } finally {
            destination.disabled = false;
        }
    }

    function bindAction(button, action) {
        button.addEventListener('click', async () => {
            button.disabled = true;
            try {
                await action();
            } catch (error) {
                showToast(error.message, 'error');
            } finally {
                button.disabled = false;
            }
        });
    }

    function addResult(item) {
        if (!item.url || shown.has(item.url)) return;
        shown.add(item.url);
        const card = document.createElement('li');
        card.className = 'search-result-card';
        const source = item.platform === 'spotify' ? 'YouTube' : sourceNames[item.platform] || sourceNames.url;
        const views = Number.isFinite(item.view_count) && item.view_count > 0
            ? ` · ${viewFormat.format(item.view_count)} lượt xem` : '';
        const duration = item.duration > 0 ? item.duration_str : '';
        const title = item.title || 'Video chưa có tên';
        const thumbnail = item.thumbnail || '/static/icons/default_cover.png';
        const enhanced = Boolean(AppState.config.search_actions_enabled);

        card.innerHTML = `
            <div class="res-left">
                <div class="res-thumb">
                    <img src="${escapeHtml(thumbnail)}" alt="" loading="lazy" data-cover>
                    ${duration ? `<span class="res-duration">${escapeHtml(duration)}</span>` : ''}
                </div>
                <div class="res-info">
                    <div class="res-title">${escapeHtml(title)}</div>
                    <div class="res-meta">${escapeHtml(item.uploader || source)}${escapeHtml(views)}</div>
                    <div class="res-meta">${escapeHtml(source)}</div>
                </div>
            </div>
            <div class="res-actions">
                <button type="button" class="btn-xs btn-glass-accent btn-play-now" aria-label="Phát ${escapeHtml(title)}">
                    <i class="fa-solid fa-play" aria-hidden="true"></i> ${enhanced ? 'Phát ngay' : 'Phát và lưu'}
                </button>
                <button type="button" class="btn-xs btn-glass-primary btn-add-queue" aria-label="Lưu ${escapeHtml(title)}">
                    <i class="fa-solid fa-plus" aria-hidden="true"></i> Lưu
                </button>
            </div>`;

        bindAction(card.querySelector('.btn-play-now'), async () => {
            if (enhanced) {
                await API.playSearchResult(item);
            } else {
                const added = await API.addDirectTrack(item);
                await API.play(added.track.id);
                refreshPlaylist().catch(console.error);
            }
            showToast(`Đang phát “${title}”`, 'success');
            toggleDrawer(false, true);
        });
        bindAction(card.querySelector('.btn-add-queue'), async () => {
            const albumId = destination.value;
            const label = destination.selectedOptions[0]?.textContent || 'Danh sách chung';
            if (albumId) {
                const { added } = await API.saveSearchResult(albumId, item);
                showToast(added ? `Đã lưu vào “${label}”.` : `Bài này đã có trong “${label}”.`, 'success');
            } else {
                await API.addDirectTrack(item);
                refreshPlaylist().catch(console.error);
                showToast('Đã lưu vào danh sách chung.', 'success');
            }
        });
        results.append(card);
    }

    async function search(loadMore = false) {
        if (searching) return;
        const query = loadMore ? lastSearch.query : input.value.trim();
        if (!query) {
            input.focus();
            return;
        }
        if (!loadMore) {
            if (platform === 'url' && !isLink(query)) {
                showToast('Hãy dán link bài hát hoặc chọn nguồn để tìm theo tên.', 'error');
                return;
            }
            lastSearch = { query, platform };
            heading.textContent = `Kết quả cho “${query}”`;
            shown.clear();
            results.replaceChildren();
            more.hidden = true;
        }

        const limit = loadMore ? 24 : 12;
        searching = true;
        submit.disabled = true;
        more.disabled = true;
        pills.forEach(pill => { pill.disabled = true; });
        results.setAttribute('aria-busy', 'true');
        toggleDrawer(true);
        report(loadMore ? 'Đang tải thêm video…' : 'Đang tìm kiếm…');
        try {
            const [{ results: found }] = await Promise.all([
                API.search(query, lastSearch.platform, limit),
                loadMore ? null : loadDestinations()
            ]);
            const previousCount = shown.size;
            found.forEach(addResult);
            if (!shown.size) report('Chưa tìm thấy bài. Thử thêm tên nghệ sĩ hoặc tên kênh.');
            else if (loadMore && shown.size === previousCount) report('Đã hết kết quả cho từ khóa này.');
            else report(`${shown.size} kết quả`);
            more.hidden = loadMore || !AppState.config.search_actions_enabled || isLink(query) || found.length < limit;
        } catch (error) {
            report(`Tìm kiếm lỗi: ${error.message}`);
        } finally {
            searching = false;
            submit.disabled = false;
            more.disabled = false;
            pills.forEach(pill => { pill.disabled = false; });
            results.removeAttribute('aria-busy');
        }
    }

    pills.forEach(pill => pill.addEventListener('click', () => {
        platform = pill.dataset.platform;
        pills.forEach(item => {
            item.classList.toggle('active', item === pill);
            item.setAttribute('aria-pressed', String(item === pill));
        });
        input.placeholder = placeholders[platform];
        toggleDrawer(false, true);
    }));
    form.addEventListener('submit', event => {
        event.preventDefault();
        search();
    });
    more.addEventListener('click', () => search(true));
    document.getElementById('btn-close-drawer').addEventListener('click', () => toggleDrawer(false, true));
    openAlbums.addEventListener('click', () => {
        toggleDrawer(false);
        document.getElementById('tab-btn-albums').click();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && drawer.classList.contains('active')) toggleDrawer(false, true);
    });
    document.addEventListener('click', event => {
        if (!drawer.parentElement.contains(event.target)) toggleDrawer(false);
    });
}
