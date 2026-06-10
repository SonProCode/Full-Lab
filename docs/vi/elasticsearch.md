# Elasticsearch

[English](../elasticsearch.md) | Tiếng Việt | [Mục lục](README.md)

Index `orders` lưu các bản ghi nghiệp vụ đã xử lý. `logs-app-*` lưu log vận hành đã được phân tích. Quá trình bootstrap cài đặt các template tường minh từ `elasticsearch/templates`.

Chức năng bảo mật và TLS được tắt chỉ để phục vụ việc học trên máy cá nhân. Khi triển khai production, cần có xác thực, TLS, lifecycle policy, snapshot, lập kế hoạch dung lượng và nhiều node được phân bổ theo các fault domain khác nhau.
