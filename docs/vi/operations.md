# Vận hành

[English](../operations.md) | Tiếng Việt | [Mục lục](README.md)

Khởi động bằng `make up`, tạo mapping bằng `make bootstrap`, rồi kiểm tra trạng thái bằng `curl localhost:8000/ready`. Khi xảy ra sự cố, dùng `make ps` và `make logs` để kiểm tra.

Số lượng message tồn đọng là `messages_ready`; số lượng công việc đang xử lý là `messages_unacknowledged`. Backlog tăng dần có thể cho thấy hệ thống thiếu consumer, dịch vụ phía sau phản hồi chậm hoặc poison message đang liên tục được retry.
