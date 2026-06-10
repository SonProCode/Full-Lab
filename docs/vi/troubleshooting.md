# Xử lý sự cố

[English](../troubleshooting.md) | Tiếng Việt | [Mục lục](README.md)

- API không truy cập được: kiểm tra `docker compose ps` và `docker compose logs api-server`.
- `/ready` trả về 503: trường detail trong JSON cho biết vấn đề nằm ở RabbitMQ, Redis hay Elasticsearch.
- Lỗi queue `inequivalent arg`: classic queue và quorum queue không thể dùng chung một tên đã tồn tại; hãy xóa volume khi đổi chế độ.
- Không tìm thấy log: kiểm tra `docker compose logs log-parser`, sau đó chạy `curl localhost:9200/_cat/indices?v`.
- Elasticsearch thoát: cấp thêm bộ nhớ cho Docker và đặt `vm.max_map_count=262144` trên host.
- RabbitMQ cluster ở chế độ full không đầy đủ: chạy `docker compose -f docker-compose.full.yml exec rabbitmq1 rabbitmqctl cluster_status`.
