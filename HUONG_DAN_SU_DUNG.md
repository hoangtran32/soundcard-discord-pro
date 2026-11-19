# HƯỚNG DẪN SỬ DỤNG - SOUNDCARD DISCORD PRO 🎵

**SoundCard Discord Pro** là phần mềm phát nhạc trực tiếp vào các kênh thoại (Voice Channels) Discord chất lượng cao, hỗ trợ nhiều phòng đồng thời (Multi-Room), playlist chọn nhiều bài, giao diện kính mờ Translucent / Glassmorphism tuyệt đẹp và khả năng tùy chỉnh hình nền từ thư mục `background/`.

---

## ⚡ Khởi Chạy 1-Click

1. **Nhấp đúp chuột vào file**:
   - `Chay_SoundCard_Discord.bat` hoặc `SoundCard_Discord.bat`.
   - Hoặc chạy `Tao_Shortcut_Desktop.bat` để tạo biểu tượng icon tiện lợi ngoài màn hình chính Desktop.
2. Ứng dụng sẽ tự động khởi động máy chủ âm thanh nội bộ và mở ngay cửa sổ ứng dụng Desktop độc lập.

Để điều khiển bot trong trình duyệt, mở địa chỉ ứng dụng do máy chủ cung cấp. Mở `static/index.html` trực tiếp chỉ hiển thị bản xem trước.

---

## Chia sẻ web cho bạn bè

### Dùng trang GitHub Pages

- Link gửi bạn bè: [SoundCard Discord](https://hoangtran32.github.io/soundcard-discord-pro/).
- Trên máy Windows đã cấu hình Discord, chạy `Chay_SoundCard_Web.bat` và giữ cửa sổ mở. File này chạy Python, mở tunnel HTTPS và cập nhật địa chỉ tunnel trên GitHub. Khi tắt hoặc mất kết nối, trang GitHub hiển thị trạng thái chưa kết nối.
- Chọn **Mở trình phát**, rồi đăng nhập bằng `music` và mật khẩu trong `data/share-password.txt`.
- Mỗi máy chạy cần quyền ghi repo qua Git Credential Manager và tệp cục bộ `data/pages-repo.txt` chứa `hoangtran32/soundcard-discord-pro`. Nhánh `soundcard-live` chỉ cập nhật địa chỉ tunnel công khai. Trang GitHub Pages phục vụ từ `main/docs`.

### Chia sẻ bằng link tunnel trực tiếp

Chế độ này dùng máy Windows của bạn để chạy web và bot. Cloudflare Quick Tunnel cấp một link HTTPS miễn phí. Link đổi mỗi lần chạy lại và chỉ hoạt động khi máy cùng tiến trình chia sẻ còn chạy.

1. Cài [cloudflared](https://developers.cloudflare.com/tunnel/downloads/) và thêm vào PATH. Máy cần có FFmpeg và Node.js 22 trở lên trong PATH để phát nhạc YouTube.
2. Đóng bản SoundCard desktop nếu đang chạy. Trong thư mục dự án, chạy `py -m pip install -r requirements.txt` rồi `py share_web.py`.
3. Gửi bạn bè link `trycloudflare.com` do cloudflared in ra. Tên đăng nhập là `music`. Mật khẩu nằm trong `data/share-password.txt`. Để đổi mật khẩu, dừng phiên chia sẻ, xóa tệp mật khẩu rồi chạy lại.
4. Trên web, tìm bài rồi bấm **Phát Ngay**. Bot sẽ tự kết nối vào kênh thoại đã chọn trong cấu hình SoundCard. Bạn bè có thể quản lý hàng đợi chung và bật/tắt kết nối với các kênh đã cấu hình. Hàng đợi web được lưu riêng trong `data/shared-playlist.json`.

Để dừng chia sẻ, chạy `py share_web.py --stop` hoặc bấm **Ctrl+C** trong cửa sổ chạy lệnh. Muốn đổi bot hoặc kênh, dừng chia sẻ, sửa trong bản desktop rồi chạy lại chế độ web.

## Chạy web và bot trên máy chủ Linux

GitHub có thể lưu mã nguồn. GitHub Pages chỉ phục vụ file tĩnh. Bản triển khai Linux chạy cả giao diện, FastAPI, Discord Voice, FFmpeg và Node.js trong một container, với Caddy cấp HTTPS. Có thể dùng máy ảo Oracle Cloud Always Free nếu tài khoản và vùng còn tài nguyên.

1. Cài Docker Engine và Docker Compose trên máy ảo. Máy ảo cần có IP công khai, mở TCP 80 và 443 cho web, đồng thời cho phép lưu lượng UDP đi ra và gói trả lời từ Discord Voice.
2. Chuyển gói mã nguồn sạch lên máy ảo. Dùng SSH/SCP để chuyển riêng `data/config.json`, `data/rooms.json` và `data/share-password.txt` từ máy Windows vào thư mục `deploy-state/` trên máy ảo. Có thể chuyển thêm `data/shared-playlist.json` để giữ hàng đợi web. Các tệp này chứa dữ liệu riêng và thuộc thư mục lưu trữ của dịch vụ.
3. Chạy các lệnh sau trong thư mục mã nguồn trên máy ảo. Thay IP ví dụ bằng IPv4 công khai thật hoặc tên miền đã trỏ về máy ảo.

   ```sh
   sudo chown -R 10001:10001 deploy-state
   sudo chmod -R go-rwx deploy-state
   sudo env SOUNDCARD_HOST=203.0.113.10 docker compose up -d --build
   ```

4. Khi Caddy cấp xong chứng chỉ, mở `https://IP-hoặc-tên-miền`, đăng nhập bằng `music` và mật khẩu đã chuyển. Thử phát một bài trong kênh đã cấu hình. Dừng bản Windows trước khi dùng cùng bot và cùng kênh trên máy ảo. Dữ liệu runtime nằm trong `deploy-state/` và được giữ qua các lần khởi động container.

## 🚀 Các Tính Năng Nổi Bật

### 1. 🎵 Trình Phát Nhạc & Bộ Điều Khiển (Now Playing)

- Chọn **YouTube** rồi gõ tên bài, nghệ sĩ hoặc tên kênh ngay trong SoundCard. Kết quả hiện tên video, kênh, ảnh và thời lượng khi có dữ liệu. Có thể dán link video hoặc chọn **SoundCloud** để tìm ở nguồn đó.
- Dùng **Phát ngay** để bot phát video đã chọn. Để lưu, chọn **Danh sách chung** hoặc một album ở ô **Lưu vào**, rồi bấm **Lưu** trên bài muốn cất. Nút **Đăng nhập album** mở nơi tạo hồ sơ và album cá nhân.
- Đĩa nhạc Vinyl xoay tròn chuyển động theo điệu nhạc.
- Hiệu ứng sóng nhạc **Spectrum Visualizer** chuyển động theo dải tần số âm thanh thời gian thực.
- Đầy đủ nút điều khiển: Phát / Tạm dừng, Dừng hẳn, Chuyển bài trước / sau, Phát ngẫu nhiên (Shuffle), Chế độ lặp lại (Tắt / Lặp 1 bài / Lặp danh sách).
- Thanh trượt **Âm Lượng SoundCard** tùy chỉnh từ 0% đến 200%.
- Bảng hiển thị trực tiếp danh sách các phòng thoại đang nhận luồng âm thanh phát trực tuyến.

### 2. 📋 Danh Sách Nhạc & Quản Lý Link (Playlist)

- Danh sách chung trên web tự lưu vào `data/shared-playlist.json` trên máy chạy bot và được tải lại khi mở file `.bat` lần sau.
- Trong **Album cá nhân**, tạo hồ sơ riêng, tạo album rồi thêm bài theo tên hoặc link nhạc. Bạn cũng có thể tích chọn các bài ở **Danh Sách Nhạc** rồi lưu bản sao vào album.
- Chọn **Phát album** để phát từ đầu hoặc **Phát từ bài** để bắt đầu ở một bài cụ thể. Nút phát tiếp, quay lại và tự chuyển bài dùng danh sách của album đang phát. Trình phát Discord dùng chung trong phòng.
- Hồ sơ và album nằm trong `data/albums.sqlite3` trên máy chạy bot. Khi tunnel đổi địa chỉ, đăng nhập lại bằng cùng tên và mật khẩu riêng để mở các album đã lưu.
- Dán link nhạc từ **YouTube, SoundCloud, URL âm thanh trực tiếp (MP3/WAV/AAC)** hoặc từ khóa tìm kiếm vào ô trên cùng và nhấn **Thêm Bài**.
- Hệ thống tự động trích xuất tên bài, tác giả, ảnh bìa, thời lượng và lưu trữ vào danh sách phát.
- **Tích chọn nhiều bài**: Tích vào ô checkbox ở từng bài để chọn danh sách phát theo ý muốn.
- Nhấn nút **"Phát Các Bài Đã Chọn"** để phát các bài vừa tích.
- Hỗ trợ **Chọn tất cả**, **Bỏ chọn**, **Xóa bài**, **Xóa toàn bộ** và **Tìm kiếm bài hát nhanh**.

### 3. 🎙️ Quản Lý Phòng Thoại Discord (Voice Rooms - Multi-Streaming)
- Thêm kênh thoại bằng cách nhấn **"Thêm Kênh Thoại Mới"**:
  - **Tên Kênh**: Tên gợi nhớ (Ví dụ: Kênh Nghe Nhạc 1).
  - **Guild ID**: ID máy chủ Discord.
  - **Voice Channel ID**: ID kênh thoại muốn phát nhạc vào.
  - **Bot Token riêng** (Tùy chọn): Nếu muốn phát đồng thời vào nhiều kênh trong *cùng 1 máy chủ*, nhập token của các bot khác nhau cho từng kênh.
- **Tích chọn nhiều phòng**: Tích chọn 1 hoặc nhiều phòng để phát trực tiếp cùng một lúc (Multi-Room Streaming).
- Nhấn **"Kết Nối Phòng Đã Chọn"** để toàn bộ các bot tham gia vào các phòng thoại đã chọn ngay lập tức.
- Hiển thị trạng thái kết nối trực quan (Đang Phát, Đã Kết Nối, Đang Kết Nối, Chưa Kết Nối) kèm độ trễ Ping (ms).

### 4. 🎨 Tùy Biến Giao Diện Kính Mờ (Translucent Glassmorphism) & Thư Mục `background/`
- Thư mục `background/` chứa sẵn các hình nền nghệ thuật chất lượng cao (Cyberpunk, Lofi Cozy Room, Synthwave Sunset...).
- Bạn có thể **thêm bất kỳ ảnh nào** (`.jpg`, `.png`, `.webp`, `.gif`) vào thư mục `background/`, ứng dụng sẽ tự động nhận diện và hiển thị trong bộ sưu tập.
- Thanh trượt điều chỉnh:
  - **Độ mờ hình nền (Blur)**: 0px &rarr; 40px.
  - **Độ sáng hình nền (Brightness)**: 20% &rarr; 100%.
  - **Độ trong suốt của kính (Glass Opacity)**: 20% &rarr; 95%.

---

## 🤖 Hướng Dẫn Thiết Lập Discord Bot Token

Để bot có thể kết nối vào kênh thoại Discord của bạn:
1. Truy cập [Discord Developer Portal](https://discord.com/developers/applications).
2. Nhấn **New Application** &rarr; đặt tên ứng dụng (Ví dụ: `SoundCard Bot`).
3. Vào tab **Bot** &rarr; nhấn **Reset Token** &rarr; Copy đoạn Token.
4. Kéo xuống mục **Privileged Gateway Intents** và bật xanh cả 3 mục:
   - *Presence Intent*
   - *Server Members Intent*
   - *Message Content Intent*
5. Vào tab **OAuth2 &rarr; URL Generator**:
   - Mục **SCOPES**: tích chọn `bot`.
   - Mục **BOT PERMISSIONS**: tích chọn `Connect`, `Speak`, `Use Voice Activity`, `Send Messages`, `Read Message History`.
   - Copy đường link bên dưới và dán vào trình duyệt để mời Bot vào Discord Server của bạn.
6. Mở SoundCard Discord &rarr; vào mục **Hình Nền & Cài Đặt** &rarr; Dán Token vào ô **Discord Bot Token (Chính)** &rarr; nhấn **Lưu Cấu Hình**.
