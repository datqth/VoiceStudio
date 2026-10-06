---
name: SingingStudio
description: Bề mặt thao tác giọng hát local trong Công cụ của VoiceStudio.
---

# Thiết kế Phòng thu giọng hát

## Overview

Phòng thu giọng hát là bề mặt **Operate**: chọn nguồn, chọn giọng tham chiếu, chạy tác vụ rồi nghe và tải kết quả. Hướng thiết kế đã triển khai là biểu mẫu gọn, có nhãn rõ và phản hồi trạng thái ngay trong cùng màn hình. Bề mặt này kế thừa nhận diện studio của VoiceStudio.

Phạm vi tài liệu chỉ gồm `SingingStudio` và mục điều hướng tương ứng trong Công cụ. Đây không phải hệ thiết kế mới cho toàn ứng dụng. Khi ghi tài liệu, không tìm thấy `PRODUCT.md` hoặc `DESIGN.md` trong repository; token và thành phần hiện hữu vẫn là nguồn sự thật.

Các nguồn đối chiếu: `electron/src/renderer/src/features/tools/singing-studio.tsx`, `tools-page.tsx`, các thành phần `Button`, `Input`, `VoiceSelector`, stylesheet chung và [tài liệu tính năng](singing-studio.md). Không suy diễn chất lượng giọng hát từ giao diện.

## Colors

Bề mặt dùng trực tiếp các vai trò màu của theme VoiceStudio, không khai báo bảng màu riêng. `primary` dành cho nút chạy và thanh tiến trình; `secondary` đánh dấu chế độ hoặc công cụ đang chọn; `muted-foreground` dành cho mô tả và giới hạn; `destructive` báo lỗi; `border` chia kết quả và lịch sử khỏi biểu mẫu.

Nguồn màu là `electron/src/renderer/src/styles/t3-theme.css`, được ánh xạ trong `globals.css`. Giữ cơ chế theme sáng và tối; không chép giá trị màu riêng vào công cụ vì sẽ tạo nguồn cấu hình thứ hai.

## Typography

Kế thừa font sans chung của ứng dụng: Inter Variable với font hệ thống dự phòng. Tiêu đề công cụ dùng cỡ 1,5 rem, độ đậm 600; mô tả và nhãn dùng cỡ 0,875 rem; giới hạn số dùng cỡ 0,75 rem. Mô tả có chiều cao dòng 1,5 rem. Tiến trình dùng chữ số có bề rộng đồng nhất để tránh dịch chuyển khi phần trăm thay đổi.

Nhãn luôn hiện phía trên ô nhập. Placeholder không thay vai trò của nhãn. Nội dung hiển thị lấy qua hệ thống dịch của ứng dụng.

## Layout

Nội dung nằm trong khung tối đa 48 rem, căn giữa trong vùng Công cụ có cuộn dọc. Khoảng cách giữa các khối chính là 2 rem; nhóm biểu mẫu cách nhau 1,5 rem. Bề mặt giữ thứ tự: tiêu đề, thông báo khả năng engine, chế độ, giọng tham chiếu, nguồn hoặc lời bài hát, tham số, hành động, kết quả, lịch sử.

Ba ô bước xử lý, âm lượng vocal và âm lượng nhạc nền nằm trên ba cột từ breakpoint `sm` của Tailwind; màn hình hẹp xếp thành một cột. Nhóm nút chế độ, hành động và tải file được phép xuống dòng. Trình phát audio chiếm toàn chiều rộng. Trong Công cụ, điều hướng phụ chuyển lên trên khi chiều rộng container dưới 40 rem.

## Elevation & Depth

Biểu mẫu nằm trực tiếp trên nền workspace. Dùng khoảng cách và đường phân cách để tạo nhóm, không thêm lớp card hay bóng đổ cho từng trường. Nút và menu chọn giọng giữ xử lý chiều sâu của thành phần chung. Menu giọng được đưa ra ngoài vùng cuộn qua portal để tránh bị cắt.

## Shapes

Giữ ngôn ngữ bo góc của studio: nút dùng bán kính điều khiển chung 0,5 rem; ô nhập, vùng lời và dòng lịch sử dùng bán kính trung bình hiện hữu. Nút chạy, nút hủy và mục điều hướng SingingStudio cao 2,75 rem; dòng lịch sử có chiều cao tối thiểu tương ứng.

## Components

- **Chọn chế độ:** hai nút Đổi giọng và Tạo bài dùng `aria-pressed`; chế độ được chọn có nền thứ cấp. Tạo bài chỉ khả dụng khi API báo có engine tương ứng.
- **Chọn giọng:** dùng `VoiceSelector` chung, chỉ đưa vào profile có `ref_audio_path`; không bật thư viện gallery, preset hoặc giọng mặc định engine. Có thể thay bằng file audio tham chiếu. Chọn profile sẽ xóa file tham chiếu và chọn file sẽ bỏ profile, giữ một nguồn giọng rõ ràng.
- **Nguồn audio:** chọn file audio/video hoặc liên kết. Khi có file nguồn, ô liên kết bị vô hiệu hóa. Tùy chọn vocal sạch mới hiện ô beat. File đã chọn có hành động xóa riêng.
- **Tạo bài:** lời, phong cách và thời lượng có nhãn riêng. Thời lượng mặc định 30 giây, giới hạn 10 - 180 giây.
- **Tham số:** số bước mặc định 30, giới hạn 10 - 50; vocal mặc định 1, giới hạn 0,1 - 2; nhạc nền mặc định 0,8, giới hạn 0 - 2. Giá trị ngoài khoảng đánh dấu `aria-invalid` và chặn chạy.
- **Chạy và hủy:** nút chạy dùng kiểu chính; hủy dùng kiểu viền khi đang gửi, xếp hàng hoặc chạy. Hủy chỉ khả dụng sau khi có job. Biểu mẫu và lịch sử bị khóa trong thời gian bận.
- **Tiến trình và lỗi:** vùng kết quả có `aria-live="polite"`, hiển thị giai đoạn và phần trăm; tác vụ đang chạy có thanh tiến trình native. Lỗi dùng `role="alert"` và cho phép xuống dòng. Nếu engine chuyển giọng chưa cài, thông báo có `role="status"` và nút chạy bị chặn.
- **Kết quả:** job hoàn tất hiện trình phát audio native, không tự phát. Nút viền tải từng file do API trả về. Lịch sử hiển thị thời gian local và trạng thái; chọn một dòng để mở lại job đó.

Khi mở bề mặt, giao diện đọc khả năng engine và lịch sử, tiếp tục theo dõi job đang hoạt động nếu có. Theo dõi job bắt đầu sau 800 ms, lặp sau 1.500 ms khi đang chạy và thử lại sau 3.000 ms nếu đọc trạng thái lỗi. Chuyển khỏi bề mặt hủy yêu cầu đọc và timer; việc hủy tác vụ backend dùng nút hủy riêng.

## Do's and Don'ts

- Giữ nút, ô nhập, bộ chọn giọng và token chung khi mở rộng công cụ.
- Giữ nguồn tham chiếu, nguồn bài, tham số và kết quả thành các nhóm dễ đọc theo thứ tự thao tác.
- Duy trì nhãn, focus bàn phím, trạng thái vô hiệu hóa và thông báo lỗi trong mọi chế độ.
- Dùng phản hồi tiến trình cho tác vụ dài; giữ nghe thử và tải file ngay cạnh kết quả.
- Không chuyển bố cục riêng của SingingStudio thành quy tắc cho toàn ứng dụng.
- Không thêm bảng màu, card trang trí hoặc trình phát tùy biến chỉ để làm khác nhận diện hiện hữu.
- Không coi trạng thái engine khả dụng hoặc ảnh giao diện là bằng chứng inference đã tương thích hay chất lượng giọng đã đạt yêu cầu.
