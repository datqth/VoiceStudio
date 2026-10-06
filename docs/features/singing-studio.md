# Phòng thu giọng hát local

Trong Công cụ, chọn Phòng thu giọng hát. Nạp bài đầy đủ hoặc vocal sạch, chọn giọng clone đã có audio thật, rồi chạy đổi giọng. Có thể dùng audio tham chiếu riêng và liên kết HTTPS YouTube. Nếu chọn vocal sạch, có thể nạp thêm beat cùng tông.

Luồng đổi giọng: Demucs tách vocal và nhạc nền, Seed-VC SVC 44,1 kHz giữ cao độ nguồn rồi chuyển màu giọng, FFmpeg mix và xuất WAV 24 bit cùng MP3 320 kbps. Lỗi engine được báo rõ, không âm thầm trả vocal gốc. Audio tổng hợp đi qua `mark_synthetic` theo tùy chọn watermark của ứng dụng.

Luồng tạo bài: lời và phong cách tiếng Việt đi qua ACE-Step 1.5 turbo, sau đó tách stem và đổi sang giọng tham chiếu bằng Seed-VC. Giọng tham chiếu không bảo đảm độ giống tuyệt đối, cần nghe thử trước khi dùng bản đầy đủ. Cấu hình mặc định giữ tông 0; đổi tông khác quãng tám cần beat cùng tông.

Hiệu chỉnh giọng hát: worker nhận checkpoint và cấu hình Seed-VC đã tinh chỉnh riêng. Để bật cho một giọng, đặt `checkpoint.pth`, `config.yml` và `model.json` trong `<DATA_DIR>/singing-models/<profile_id>/`. Manifest gồm `reference_sha256` (SHA-256 của file tham chiếu đã lưu trong thư viện) và `cfg` (0-2, mặc định 0,7). Chỉ giọng có manifest mới dùng model riêng; giọng khác giữ model gốc. Nếu mẫu giọng đã thay, model thiếu file hoặc CFG không hợp lệ, công việc báo lỗi rõ. Không đưa checkpoint và audio cá nhân lên Git. Các model thử nghiệm chưa được bật mặc định trước khi nghe đối chiếu.

API nhận thêm `cfg` tùy chọn, ưu tiên giá trị gửi lên rồi đến manifest rồi mặc định 0,7. Worker CLI nhận `--cfg`, `--checkpoint`, `--config`; checkpoint và config phải đi cùng nhau. `pitch=-12` hoặc `12` đổi quãng tám và giữ bộ nốt của nhạc nền, được phép mix với beat. Các mức đổi tông khác vẫn cần hai stem đã chuẩn bị cùng tông; không tự động ép cao độ hát về trung vị giọng nói. Giao diện hiện giữ tông 0.

Mẫu nói 20-30 giây chỉ đủ thử zero-shot hoặc few-shot, chưa đủ bảo đảm nhận diện giọng khi hát. Tăng số bước, CFG hay rút ngắn mẫu không chắc cải thiện. Kiểm tra trên đoạn thực sự có vocal, so sánh bản cũ, model riêng và quãng hát phù hợp. Cosine của speaker embedding chỉ là tín hiệu phụ, có thiên lệch giữa nói và hát; quyết định độ giống cần nghe đối chiếu. Dữ liệu hát sạch của đúng giọng và nhiều quãng giúp tinh chỉnh đáng tin hơn.

Engine chạy trong môi trường Python riêng. Thiết lập `OMNIVOICE_SEED_VC_DIR` và `OMNIVOICE_ACE_STEP_DIR` nếu engine nằm ngoài thư mục cạnh ứng dụng. Chạy `scripts/install-singing-engines.ps1` để cài trên Windows; installer chọn Torch CUDA 12.8 tương thích RTX 5070. Trên hệ khác tạo `.venv` của engine bằng runtime phù hợp và cấu hình hai đường dẫn. Worker tự nhận diện CUDA/CPU và Seed-VC tự nhận diện MPS.

Launcher local `scripts/start-singing-studio.ps1` đặt một GPU worker, tắt torch compile cho cấu hình Windows hiện tại, sử dụng thư viện đã sao lưu tại `%APPDATA%/VoiceStudio-Singing`. Không sửa thư viện OmniVoice cũ. Backend lắng nghe loopback ở cổng 3900, giao diện web ở 3901.

Giao diện mở tại `http://localhost:3901/#/tools`. Trên máy Anh Đạt, lệnh `voice-start -Open` đã trỏ tới launcher mới. Bản desktop Electron cũng có thể gắn vào backend đang chạy qua `VOICESTUDIO_SKIP_BACKEND=1` rồi `bun run start`. Không chạy đồng thời backend cũ và mới trên cùng cổng.

API: `GET /singing/capabilities`, `POST /singing/jobs` (multipart), `GET /singing/jobs`, `GET /singing/jobs/{id}`, `POST /singing/jobs/{id}/cancel`, `GET /singing/jobs/{id}/files/{filename}`. API chỉ cho phép truy cập native loopback. Job được lưu bằng JSON cạnh audio; job đang chạy khi ứng dụng tắt được hiển thị là thất bại sau khởi động lại.

Giới hạn: file 200 MB, bài nguồn tối đa 10 phút, tạo bài tối đa 180 giây, 10-50 bước đổi giọng. Lần chạy đầu có thể tải model Hugging Face. API capabilities kiểm tra đường dẫn cài đặt, chưa thay thế inference thử tương thích runtime.

Kiểm chứng Windows RTX 5070: đổi giọng toàn bài 247,815 giây cho Kiên và Phương Anh; tạo bài tiếng Việt 20 giây bằng ACE-Step rồi chuyển sang giọng Phương Anh; TTS tiếng Việt của Kiên; hủy tiến trình và phục hồi theo dõi công việc; typecheck, build web và Electron; kiểm thử giao diện và backend của tính năng. Bộ test backend toàn repo gặp fixture FFprobe viết script Unix rồi yêu cầu chạy như executable trên Windows, ngoài thay đổi này.

Seed-VC dùng GPL-3.0, ACE-Step dùng MIT, VoiceStudio dùng AGPL-3.0. Giữ các thông báo giấy phép khi phân phối. Công cụ tạo và chuyển đổi local, không tự gửi audio giọng tham chiếu lên dịch vụ bên ngoài.
