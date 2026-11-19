const statusText = document.getElementById('status');
const openPlayer = document.getElementById('open-player');
const retry = document.getElementById('retry');
const repo = document.documentElement.dataset.repo;
const liveFile = `https://raw.githubusercontent.com/${repo}/soundcard-live/live.json`;
let checking = false;

function fetchLive(url) {
    return fetch(url, {
        cache: 'no-store',
        credentials: 'omit',
        redirect: 'error',
        signal: AbortSignal.timeout(6000)
    });
}

async function checkStatus() {
    if (checking) return;
    checking = true;
    try {
        const manifest = await fetchLive(`${liveFile}?check=${Math.floor(Date.now() / 15000)}`);
        if (!manifest.ok) throw new Error('Address unavailable');
        const { url } = await manifest.json();
        if (typeof url !== 'string' || !/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(url)) {
            throw new Error('Invalid address');
        }
        const health = await fetchLive(`${url}/healthz`);
        if (health.status !== 204) throw new Error('Player offline');
        statusText.textContent = 'Máy chủ đang chạy. Bạn có thể mở trình phát.';
        openPlayer.href = url;
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
setInterval(checkStatus, 15000);
