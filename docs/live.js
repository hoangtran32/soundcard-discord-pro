const statusText = document.getElementById('status');
const openPlayer = document.getElementById('open-player');
const retry = document.getElementById('retry');
const repo = document.documentElement.dataset.repo;
const liveFile = `https://api.github.com/repos/${repo}/contents/live.json?ref=soundcard-live`;
const invite = new URLSearchParams(location.hash.slice(1)).get('invite');
let checking = false;

function fetchLive(url, headers) {
    return fetch(url, {
        cache: 'no-store',
        credentials: 'omit',
        redirect: 'error',
        headers,
        signal: AbortSignal.timeout(6000)
    });
}

async function checkStatus() {
    if (checking) return;
    checking = true;
    try {
        const manifest = await fetchLive(liveFile, { Accept: 'application/vnd.github.raw+json' });
        if (!manifest.ok) throw new Error('Address unavailable');
        const { url } = await manifest.json();
        if (typeof url !== 'string' || !/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(url)) {
            throw new Error('Invalid address');
        }
        const health = await fetchLive(`${url}/healthz`);
        if (health.status !== 204) throw new Error('Player offline');
        if (invite && health.headers.get('X-SoundCard-Guest-Link') !== '1') {
            statusText.textContent = 'Link mời sẽ dùng được khi chủ phòng mở lại SoundCard.';
            openPlayer.hidden = true;
            openPlayer.removeAttribute('href');
            retry.hidden = false;
            return;
        }
        statusText.textContent = 'Máy chủ đang chạy. Bạn có thể mở trình phát.';
        const destination = new URL(invite ? '/join' : '/', url);
        if (invite) destination.hash = new URLSearchParams({ invite }).toString();
        openPlayer.href = destination.href;
        openPlayer.hidden = false;
        retry.hidden = true;
    } catch {
        statusText.textContent = 'Chưa kết nối được. Bạn có thể quay lại khi chủ phòng bật SoundCard.';
        openPlayer.hidden = true;
        openPlayer.removeAttribute('href');
        retry.hidden = false;
    } finally {
        checking = false;
    }
}

retry.addEventListener('click', checkStatus);
checkStatus();
setInterval(checkStatus, 75000);
