# Redis

[English](../redis.md) | Tiếng Việt | [Mục lục](README.md)

Các key sử dụng prefix rõ ràng: `idempotency:`, `rate:` và `job:`. Tất cả key của ứng dụng đều có TTL. Cách này ngăn trạng thái tạm thời tăng không giới hạn, nhưng cũng có nghĩa Redis không phải nơi lưu trữ bản ghi nghiệp vụ lâu dài.

Chế độ full gồm một replica và Sentinel để quan sát. Các ứng dụng mẫu vẫn kết nối trực tiếp tới primary; để failover trong production, cần connection pool hỗ trợ Sentinel và ít nhất ba tiến trình Sentinel độc lập.
