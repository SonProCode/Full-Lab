# Luồng xử lý log

[English](../log-pipeline.md) | Tiếng Việt | [Mục lục](README.md)

Logger của API và worker ghi mỗi object JSON trên một dòng ra stdout và volume dùng chung. Logstash theo dõi các file này, phân tích JSON, chuẩn hóa `timestamp` thành `@timestamp`, đặt `environment=lab`, rồi ghi dữ liệu vào các data stream `logs-app-*` theo ngày bằng thao tác create.

Có thể tìm kiếm chính xác theo `request_id` hoặc `trace_id`; cả hai đều là trường kiểu keyword. Quá trình ingest diễn ra bất đồng bộ nên log mới có thể mất vài giây mới xuất hiện.
