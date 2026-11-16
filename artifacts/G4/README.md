# G4 2 核 4G 形态压测产物

- `load_test/`：连接池修复前，12 并发 60 请求。
- `load_test_24c/`：连接池修复前，24 并发 120 请求。
- `load_test_12c_fixed/`：有界连接池修复后，12 并发 60 请求。
- `load_test_24c_fixed/`：有界连接池修复后，24 并发 120 请求。
- `comparison.json`：修复前后与资源约束对比。
- `test_summary.json`：最终容量验收摘要。

资源形态：Backend 1.0 CPU、MySQL 0.75 CPU、Nginx 0.25 CPU，合计约 2 核；内存限额合计约 2.43GB。
