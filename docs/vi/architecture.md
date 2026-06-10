# Kiến trúc

[English](../architecture.md) | Tiếng Việt | [Mục lục](README.md)

API chịu trách nhiệm kiểm tra request, giới hạn tốc độ, đảm bảo tính idempotent và publish message. RabbitMQ tách thời gian phản hồi request khỏi quá trình xử lý bất đồng bộ. Worker chịu trách nhiệm xử lý nghiệp vụ, cập nhật trạng thái hiện tại trong Redis và lưu tài liệu nghiệp vụ vào Elasticsearch. Logstash hoạt động độc lập, chuyển các file log JSON dùng chung thành các sự kiện `logs-app-*` có thể tìm kiếm.

Hệ thống sử dụng cơ chế giao nhận ít nhất một lần (at-least-once). Nếu worker dừng sau khi index dữ liệu nhưng trước khi gửi acknowledgement, message có thể được giao lại. Trong môi trường production, thao tác xử lý phải có tính idempotent, thường bằng cách dùng mã đơn hàng làm document ID và bảo vệ các side effect không idempotent.

Chế độ light ưu tiên tiết kiệm tài nguyên máy cá nhân. Chế độ full ưu tiên các bài thực hành về tính sẵn sàng của RabbitMQ, đồng thời vẫn sử dụng Elasticsearch một node.
