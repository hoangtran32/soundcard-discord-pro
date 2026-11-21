async function useInvite() {
    const key = new URLSearchParams(location.hash.slice(1)).get('invite');
    history.replaceState(null, '', location.pathname);
    const status = document.getElementById('join-status');
    const login = document.getElementById('join-login');
    if (!key || !/^[A-Za-z0-9_-]{32,64}$/.test(key)) {
        status.textContent = 'Hãy mở lại link mời đầy đủ mà chủ phòng gửi.';
        login.hidden = false;
        return;
    }
    try {
        const response = await fetch('/api/join', {
            method: 'POST',
            headers: { 'X-SoundCard-Invite': key },
            cache: 'no-store',
            signal: AbortSignal.timeout(8000)
        });
        if (response.status === 204) {
            location.replace('/');
            return;
        }
        status.textContent = 'Link mời không còn dùng được. Hãy xin lại link từ chủ phòng.';
    } catch {
        status.textContent = 'Chưa kết nối được. Hãy thử mở lại link mời.';
    }
    login.hidden = false;
}

useInvite();
