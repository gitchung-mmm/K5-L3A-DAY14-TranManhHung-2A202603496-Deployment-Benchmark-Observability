# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây đều lấy trực tiếp từ các file report thật trong `reports/`, `benchmark-results/` và 4 ảnh chụp trong `screenshots/`.

**Họ tên:** Tran Manh Hung - 2A202603496  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 11 + WSL2 Ubuntu-24.04 (`Python 3.12.3`), Docker Desktop `29.9.3` (Docker Compose `v5.7.0`)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Request thông thường tốn ~180–220 ms (retrieval + mock LLM); ngưỡng 500 ms cho phép 95% người dùng có trải nghiệm mượt mà, đồng thời phát hiện ngay khi tail latency lan sang p95 hoặc hệ thống bị nghẽn hàng đợi |
| Error rate `/ask` | `< 2.0 %` | `MOCK_ERROR_RATE` mặc định là 1%; ngưỡng 2% cho phép biên dao động thống kê nhỏ nhưng bắt kịp thời khi lỗi upstream tăng bất thường (alert `AgentHighErrorRate` kích hoạt khi > 5%) |
| Accuracy trên golden dataset | `≥ 85 %` (mục tiêu sau sửa KB: `100 %`) | Đảm bảo agent v2 trả lời đúng hầu hết câu hỏi cốt lõi và chặn mọi thay đổi gây regression trước khi deploy |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 requests/mức)

Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO (`p95 ≤ 500ms`, `err ≤ 2%`) |
|---|---|---|---|---|---|---|
| 1 | 4.35 | 185.1 | 218.8 | 1694.0 | 1.33% | ✅ PASS |
| 10 | 36.23 | 187.3 | 220.9 | 1702.5 | 1.67% | ✅ PASS |
| 50 | 122.92 | 192.1 | 263.7 | 1705.8 | 1.00% | ✅ PASS |
| 100 | 75.09 | 273.9 | 2052.5 | 2282.5 | 1.67% | ❌ FAIL (`p95 > 500ms`) |

**Nhận xét:** RPS **không** tăng tuyến tính mãi theo concurrency. Từ concurrency 1 → 10 → 50, RPS tăng mạnh (`4.35` → `36.23` → `122.92 req/s`) nhờ FastAPI chạy bất đồng bộ (async I/O) xử lý song song các `await asyncio.sleep`. Tuy nhiên đến concurrency **100**, 1 process uvicorn đơn lẻ chạm ngưỡng bão hòa event loop/connection backlog khiến request phải xếp hàng: RPS tụt xuống còn `75.09 req/s`, p50 tăng lên `273.9 ms` và p95 vọt lên `2052.5 ms` (vi phạm SLO).

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 189.0 | 215.3 | 222.0 |
| 0.03 (mặc định) | 234.9 | 219.6 | 1692.3 |
| 0.1 | 357.5 | 1687.3 | 1710.4 |

**Nhận xét:**
- **p99** là chỉ số nhạy nhất với request chậm: chỉ cần `3%` request chậm (`MOCK_SLOW_RATE=0.03`), `avg` chỉ tăng nhẹ từ `189.0 ms` → `234.9 ms` (+45.9 ms), `p95` gần như đứng yên (`219.6 ms`), nhưng **p99 nhảy vọt từ `222.0 ms` lên `1692.3 ms`** (~7.6 lần).
- Khi tăng lên `10%` (`MOCK_SLOW_RATE=0.1` > 5%), cả **p95 cũng vọt lên `1687.3 ms`** (vi phạm SLO 500 ms), trong khi `avg` mới chỉ là `357.5 ms` (vẫn nhìn có vẻ "khỏe" dưới 500 ms!).
- Vì vậy **SLO bắt buộc phải đặt theo percentile (`p95`/`p99`)**, không đặt theo trung bình (`average`), vì giá trị trung bình che giấu nhóm người dùng đang chịu trải nghiệm rất chậm (tail latency).

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.3% (21/23) | **100.0% (23/23)** |
| Avg tokens / câu | 57.8 | 108.8 | 113.9 |
| Tổng cost (USD) | \$0.000414 | \$0.000758 | \$0.000793 |
| Cost / câu đúng (USD) | \$0.00041415 | \$0.00003607 | **\$0.00003446** |
| Quality gate | FAIL | PASS (≥ 80%) | **PASS (≥ 100%, 0 regression)** |

**Những câu v2 trả lời sai ban đầu và cách sửa (`06-lab-complete/benchmark-observability/develop/utils/mock_llm.py` & đồng bộ sang `production/utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt"], ...)` vào `KNOWLEDGE_BASE` giải thích sự khác nhau giữa API key và JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn) |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["hpa", "kubernetes", "autoscal"], ...)` vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA scale pod dựa trên CPU, memory hoặc custom metrics |

**Nhận xét trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng:** v2 (có bước retrieval RAG) tăng accuracy từ `4.35%` → `91.3%` → `100%` (tăng +95.65 điểm %).
- **Chi phí:** Mỗi câu của v2 tốn gần gấp đôi số token (`113.9` vs `57.8`) do prompt chứa thêm đoạn context truy xuất được, tổng cost tăng ~1.9 lần (`\$0.000793` vs `\$0.000414`). Tuy nhiên xét trên **cost / câu trả lời đúng**, v2 (`\$0.00003446`) **rẻ hơn v1 (`\$0.00041415`) tới ~12 lần** vì v1 tốn tiền cho 22 câu trả lời sai.
- **Latency:** v2 chậm hơn một chút ở p95 (`212.7 ms` vs `186.6 ms`, +26 ms) do thêm bước retrieval (~20 ms) — đây là sự đánh đổi hoàn toàn xứng đáng.

**Dùng Quality Gate trong CI để chặn merge PR:**
Script `eval/run_eval.py` trả về **exit code `0`** khi đạt ngưỡng `--min-accuracy` và không có câu nào bị regression so với `--baseline`, ngược lại trả **exit code `1`**. Trong GitHub Actions (`.github/workflows/eval.yml`), ta khởi động agent v2 ở background rồi chạy:
```yaml
python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85 --baseline reports/eval_v2.json
```
Nếu accuracy tụt dưới 85% hoặc có câu nào đang đúng trở thành sai (regression), bước này thoát với mã lỗi `1` → CI job **fail** → GitHub Branch Protection tự động **chặn merge PR** vào `main`.

**Ghi chú Exercise 7.1 (Metrics & Cardinality):**
- Ví dụ 3 loại metric trên `/metrics`: Counter (`http_requests_total`), Gauge (`agent_in_flight_requests`), Histogram (`http_request_duration_seconds`, và metric mới thêm `agent_question_length_chars`).
- Nếu dùng URL thật (`request.url.path`) thay vì route template (`route.path`) làm label, khi bot quét hàng nghìn URL lạ (`/wp-admin`, `/.env`, `/a1b2c3`...), số tổ hợp time series sẽ bùng nổ (**high cardinality**), làm Prometheus nhanh chóng cạn RAM và chậm truy vấn.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với **2 alert đang firing cùng lúc** (`AgentHighErrorRate` & `LLMCostBurnRateHigh`): [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời Exercise 7.4 (quan sát từ Grafana & Nginx):**
1. **p95 và avg khi có tải:** Trong lúc tải cao trên Grafana, `avg` ở mức ~`236 ms` (p50 ~`175 ms`), trong khi `p95` ở mức ~`294 ms` và `p99` lên tới `1.85 s`. Khoảng cách lớn giữa `avg`/`p50` với `p99` (gấp ~7–10 lần) cho thấy hệ thống có đuôi trễ (tail latency ~3% request chậm thêm 1.5s).
2. **Requests/s theo instance:** Nginx phân tải rất đều giữa các instance theo round-robin (quan sát cùng thời điểm: `172.21.0.5:8000` đạt `22.6 req/s` và `172.21.0.8:8000` đạt `22.7 req/s`).
3. **Vì sao input tokens/s thường lớn hơn (hoặc biến động theo prompt) output tokens/s?** Mỗi request gửi vào LLM phải kèm `SYSTEM_PROMPT` + đoạn tài liệu context RAG (agent v2) + câu hỏi người dùng nên phần input dài; trong khi câu trả lời ngắn gọn chỉ bằng 1 đoạn ngắn (tuy nhiên ở một số câu hỏi có câu trả lời dài hơn prompt ngắn, tỉ lệ thay đổi tùy nội dung câu hỏi).
4. **`curl -i http://localhost:8080/metrics` trả về gì và vì sao?** Trả về **`HTTP/1.1 404 Not Found`** từ `nginx/1.28.3`. Lý do: Nginx cố tình không expose `/metrics` ra bên ngoài để tránh lộ thông tin vận hành nội bộ (số request, phiên bản, chi phí) ra internet; chỉ Prometheus nằm chung mạng Docker nội bộ `obs_net` mới được scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống" (Chaos & Alerting)

Unit test alert rules bằng `promtool test rules /p/alert_rules_test.yml`: **`SUCCESS`**.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.25` (kèm tải Locust 30 users) | `AgentHighErrorRate` (`severity=critical`, giá trị đo `24.6%` > `5%`) | **83.5 giây** (~1m 24s; điều kiện `for: 1m` + chu kỳ scrape/eval) | **Error rate** & **LLM calls theo kết quả (`error`)** |
| C | `LLM_MODEL=mock-llm-large` (chạy đồng thời với A) | `LLMCostBurnRateHigh` (`severity=warning`, giá trị đo `\$14.37/giờ` > `\$2/giờ`) | **158.6 giây** (~2m 39s; điều kiện `for: 2m` + thời gian tích lũy rate 5m) | **LLM cost (1h)** & **Latency `/ask`** (do `latency_factor=2.5`) |
| B | `MOCK_SLOW_RATE=0.3` (phân tích từ rule) | `AgentHighLatencyP95` (`p95 > 1s`) | ~2m 15s – 2m 30s (`for: 2m`) | **Latency `/ask` (p95 / p99)** |
| D | `docker pause` 1 instance (phân tích từ rule) | `AgentInstanceDown` (`up == 0`) | ~45s (`for: 30s` + 15s scrape interval) | **Instances up** & **Requests/s theo instance** |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** (vì HTTP vẫn trả `200`, latency còn nhanh hơn và cost rẻ hơn) | Không firing | **Retrieval hit ratio** tụt về 0% & **Phiên bản đang chạy** đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing. Cách phát hiện loại sự cố này trong production:**
- Alert hạ tầng (4 Golden Signals) chỉ đo hệ thống có *chạy nhanh và không báo lỗi HTTP* hay không — hoàn toàn "mù" trước lỗi **suy giảm chất lượng câu trả lời** (hallucination, hỏng RAG, nhầm phiên bản prompt/agent).
- Để phát hiện trong production cần kết hợp:
  1. **Eval quality gate tự động trong CI/CD** trước khi deploy (so sánh accuracy với baseline trên golden dataset).
  2. **Giám sát metric đặc thù cho AI/RAG** như `retrieval_hit_ratio` (đặt alert nếu tụt bất thường), kết hợp **online evaluation** (chấm mẫu traffic thật bằng LLM-as-a-Judge) và theo dõi phản hồi người dùng (thumbs up/down).
- *Ghi chú thêm về lỗi 504 ở Nginx:* Khi agent bị treo/timeout ở tầng Nginx, Nginx tự trả `504 Gateway Timeout` cho client trước khi app FastAPI kịp ghi nhận response, nên lỗi này không hiện trong metric `http_requests_total` của agent — cần giám sát thêm cả metric/access log ở tầng Nginx (hoặc synthetic probe từ bên ngoài).

### 4.3 Debug bằng trace

Chọn trace chậm nhất tìm được trong Jaeger (`screenshots/jaeger-slow-trace.png`):

- `trace_id`: `a9bdcf93ede717ab0f2b5d853cf2386d`
- Tổng thời gian: **`1700 ms`** (`1.7s`, gồm 4 spans)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**`1699.0 ms`**, chiếm **~99%** tổng thời gian; bước `agent.retrieve_context` chỉ mất `18.2 ms`)
- Dòng log JSON tương ứng từ `docker compose -p k5-day14-observability logs agent` (khớp `trace_id`):

```json
{"ts": "2026-11-25T10:24:36.908905+00:00", "level": "INFO", "service": "observable-agent", "instance": "2285f90553f8", "event": "llm_call", "trace_id": "a9bdcf93ede717ab0f2b5d853cf2386d", "span_id": "fdc555c0301378cd", "request_id": "7a6a40ad2ac8", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1699.0}
```

*(Ngoài ra, ở trace lỗi `28d73b9fc44b2dd0bcfef04664725f1b` trong `screenshots/jaeger-error-trace.png`, span `chat mock-llm-small` ghi nhận sự kiện `exception`: `utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)` tại `81.7 ms`, khớp với dòng log `event: "llm_error"` có cùng `trace_id`.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn dữ liệu: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `POST /ask` — và tương ứng `Aggregated`).

| Số instance | RPS (`/ask` / Aggregated) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 56.82 / 62.61 | 190 | 230 | 1700 | 55 (0.77%) |
| 3 | 56.25 / 62.07 | 190 | 220 | 1700 | 76 (1.07%) |

**Giải thích kết quả:**
- **Scale từ 1 lên 3 instance chỉ giảm nhẹ p95 của `/ask` (`230 ms` → `220 ms`) và giảm một nửa p95 của `/health` (`10 ms` → `5 ms`), nhưng không làm tăng RPS gấp 3 lần và giữ nguyên p99 (`1700 ms`).**
- **Nút thắt (bottleneck) nằm ở thời gian chờ I/O của upstream LLM** (`~120–180 ms` mỗi call và `~1.7 s` cho 3% request chậm), kết hợp với `wait_time` giữa các request của 100 user giả lập trong Locust — hoàn toàn **không phải** do thiếu CPU của FastAPI (vì 1 instance async vẫn gánh tốt ~60 RPS I/O-bound).
- **Ý nghĩa thực tế:** Scale ngang số instance giúp hệ thống chịu được lượng user đồng thời lớn hơn trước khi bão hòa CPU/event loop và đảm bảo tính sẵn sàng cao (High Availability nếu 1 instance chết), nhưng để giảm latency p95/p99 của AI agent thì phải tối ưu ở tầng LLM (streaming, semantic caching trên Redis, chọn model nhỏ hơn/nhanh hơn, hoặc rút gọn prompt/context).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Đo bằng percentile (`p95`/`p99`), không tin vào trung bình:** Average che giấu tail latency; một hệ thống có avg 357 ms vẫn có thể làm 10% người dùng phải chờ gần 2 giây.
  2. **Ba trụ cột Observability (Metrics – Logs – Traces) bổ trợ cho nhau:** Metrics & Alerts trên Prometheus/Grafana cho biết *hệ thống đang có vấn đề*, Distributed Tracing trên Jaeger chỉ ra *chậm hay lỗi ở đúng span nào*, còn Structured JSON Logs gắn `trace_id` cung cấp ngữ cảnh chi tiết để sửa lỗi.
  3. **AI Agent cần thêm lớp giám sát chất lượng (Eval) và chi phí (Cost/Token):** Một bản deploy hỏng RAG (`v1`) vẫn trả `200 OK` và nhanh hơn nhưng trả lời sai 95% — chỉ có Eval quality gate và theo dõi `cost / câu đúng` mới bắt được.
- **Nếu đưa agent này lên production thật, sẽ thêm các metric / alert:**
  - **Metric & Alert về chất lượng RAG/LLM:** `retrieval_hit_ratio < 0.7`, tỉ lệ fallback/empty answer, điểm online eval (LLM-as-a-Judge) trên mẫu traffic thật.
  - **Metric & Alert về trải nghiệm Streaming:** **TTFT** (*Time To First Token*) và **TPOT** (*Time Per Output Token*) thay vì chỉ đo tổng thời gian request.
  - **Metric & Alert tầng hạ tầng phụ thuộc:** Redis latency/error rate, Nginx `5xx`/`504` rate, và cảnh báo sớm khi ngân sách LLM đạt 80% (`warn`) trước khi chạm 100% (`402`).
