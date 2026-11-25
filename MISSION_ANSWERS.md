# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **Hardcoded secrets (dòng 17–18):** `OPENAI_API_KEY = "sk-hardcoded-..."` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` ghi trực tiếp vào source code — nếu push lên Git sẽ lộ secret ngay lập tức.
2. **In secret ra log bằng `print()` (dòng 33–38):** Dùng `print()` thay cho structured logging và đặc biệt dòng 34 (`print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`) in thẳng API key ra stdout.
3. **Không có config management theo môi trường (dòng 21–22):** Hardcode `DEBUG = True`, `MAX_TOKENS = 500`, không đọc biến môi trường.
4. **Không có health check / readiness endpoint (dòng 42–43):** Không có `/health` hay `/ready`, nên Docker/Cloud platform không biết khi nào process treo để restart hoặc ngừng gửi traffic.
5. **Bind cứng `host="localhost"`, `port=8000` và bật `reload=True` (dòng 49–54):**
   - `host="localhost"` khiến container/cloud không nhận được kết nối từ bên ngoài (phải là `0.0.0.0`).
   - `port=8000` cố định, không đọc biến `PORT` do Railway/Render cấp.
   - `reload=True` chỉ dùng lúc phát triển, gây tốn tài nguyên và mất ổn định trong production.
6. **Không có graceful shutdown & không có CORS/validation rõ ràng:** Khi container nhận `SIGTERM`, process bị ngắt đột ngột làm đứt request đang xử lý.

**Đối chiếu một anti-pattern đã được sửa trong `01-localhost-vs-production/production/app.py`:**
- Trong `develop/app.py` (dòng 33–38) dùng `print()` và lộ API key; sang `production/app.py` (dòng 28–32 và 111–122) đã đổi sang `logging` định dạng JSON có cấu trúc và tuyệt đối không ghi secret vào log.
- Trong `develop/app.py` (dòng 51–53) hardcode `localhost:8000`, `reload=True`; sang `production/app.py` (dòng 194–199) đọc `settings.host` (`0.0.0.0`), `settings.port` (từ env `PORT`) và chỉ bật `reload` khi `settings.debug` là `True`.

### Exercise 1.2: Run develop version

Lệnh chạy trong `01-localhost-vs-production/develop/` và gọi thử (bản develop nhận `question` qua query param):

```bash
curl -sS -i -X POST "http://127.0.0.1:8000/ask?question=Hello"
```

Kết quả thực tế:

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:15:45 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 1.3: Comparison table

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Why Important? |
|---------|----------------------------|----------------------------------|----------------|
| Config & Secrets | Hardcode API key, DB URL, `DEBUG=True`, `port=8000` trong code | Đọc toàn bộ từ biến môi trường qua `config.py` (`settings`) và `.env` (không commit `.env`) | Cùng 1 bản code chạy được trên dev/staging/prod, xoay vòng secret dễ dàng, không lộ key lên Git |
| Network Binding | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port=settings.port`, `reload=settings.debug` | Trong container/cloud phải nghe `0.0.0.0` và cổng động `PORT` do nền tảng cấp; tắt `reload` để ổn định hiệu năng |
| Health & Readiness | Không có | Có `/health` (liveness), `/ready` (readiness trả 503 khi chưa sẵn sàng), `/metrics` | Orchestrator biết khi nào container chết để restart và khi nào đủ sẵn sàng để nhận traffic |
| Logging | `print()` dạng chuỗi tự do, in cả `OPENAI_API_KEY` | Structured JSON logging (`logging`), không in secret | Hệ thống log tập trung (Loki, Datadog, Cloud Logging) có thể parse, tìm kiếm, lọc lỗi và tạo cảnh báo tự động |
| Shutdown | Ngắt đột ngột | `lifespan` context manager + `signal.SIGTERM` handler đặt `is_ready=False` rồi dọn tài nguyên | Không cắt ngang request đang chạy dở khi redeploy/scale down, tránh lỗi 502 cho người dùng |
| Security (CORS & Validation) | Không cấu hình CORS, nhận query string thô | Có `CORSMiddleware` theo `allowed_origins`, kiểm tra JSON body và trả `422` khi thiếu `question` | Giới hạn nguồn trình duyệt gọi API và trả mã lỗi chuẩn thay vì lỗi 500 không rõ ràng |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (bản Debian đầy đủ kèm Python 3.11 và rất nhiều công cụ hệ thống, dung lượng lớn ~1 GB+).
2. **Working directory:** `/app` (`WORKDIR /app` — mọi lệnh `COPY`, `RUN`, `CMD` sau đó thực thi trong thư mục này).
3. **Tại sao `COPY requirements.txt` trước `COPY . .` (hoặc copy code)?** Vì Docker cache theo từng layer. `requirements.txt` ít thay đổi hơn code ứng dụng; nếu copy và chạy `pip install` trước, khi chỉ sửa `app.py` Docker sẽ tái sử dụng layer cache của `pip install` thay vì tải và cài lại toàn bộ thư viện từ đầu, giúp build nhanh hơn rất nhiều.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` định nghĩa lệnh (hoặc tham số mặc định) chạy khi container khởi động, và **dễ dàng bị ghi đè** khi truyền lệnh ở cuối `docker run <image> <cmd>`.
   - `ENTRYPOINT` định nghĩa tiến trình chính cố định của container; mọi tham số truyền thêm ở `docker run` sẽ được **nối vào sau** `ENTRYPOINT` (chỉ ghi đè được khi dùng cờ `--entrypoint`).

### Exercise 2.2 & 2.3: Build, run container & Image size comparison

Build từ gốc repo:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
```

**Kết quả test container `my-agent:develop` (cổng 8000):**
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:17:53 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

**Phân tích Multi-stage build (`02-docker/production/Dockerfile`):**
- **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` để biên dịch và cài toàn bộ Python packages vào `/root/.local` (`pip install --no-cache-dir --user`). Stage này không được đóng gói vào image cuối.
- **Stage 2 (`runtime`):** Bắt đầu mới từ `python:3.11-slim`, tạo non-root user `appuser`, chỉ `COPY --from=builder /root/.local` và mã nguồn cần chạy (`main.py`, `utils/mock_llm.py`), thêm `HEALTHCHECK` và chạy `uvicorn`.
- **Tại sao image nhỏ hơn?** Loại bỏ hoàn toàn base image Debian full và toàn bộ trình biên dịch/công cụ build (`gcc`, `libpq-dev`, headers, cache) vốn chỉ cần lúc cài thư viện chứ không cần lúc chạy.

**So sánh kích thước thực đo bằng `docker images my-agent`:**
- Develop (`my-agent:develop`): **1.67 GB** (`1,667,792,437 bytes` ≈ `1,667.8 MB`)
- Production (`my-agent:advanced`): **240 MB** (`239,815,442 bytes` ≈ `239.8 MB`)
- Difference: **Giảm 85.6%** (nhỏ hơn ~6.95 lần)

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc (4 services trên bridge network `internal`):**

```text
               (Host :80 / :443)
                      │
                      ▼
               ┌─────────────┐
               │    nginx    │  (nginx:alpine — Reverse Proxy + Security Headers)
               └──────┬──────┘
                      │ internal network (http://agent:8000)
                      ▼
               ┌─────────────┐
               │    agent    │  (FastAPI, không expose port trực tiếp ra host)
               └──┬───────┬──┘
       REDIS_URL  │       │  QDRANT_URL
                  ▼       ▼
        ┌────────────┐  ┌────────────┐
        │   redis    │  │   qdrant   │  (có healthcheck & persistent volumes)
        │  (:6379)   │  │  (:6333)   │
        └────────────┘  └────────────┘
```

**Các service khởi động (`docker compose -p k5-day14-docker ps`):** `redis` (healthy), `qdrant` (healthy), `agent` (chờ `redis` & `qdrant` healthy mới khởi động), `nginx` (expose cổng `80:80`, `443:443`). Chúng giao tiếp qua tên service DNS nội bộ trên mạng `internal`.

**Kết quả test thực tế qua Nginx (`http://localhost`):**

```http
-- GET http://localhost/health --
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.4,"version":"2.0.0","timestamp":"2026-11-25T09:18:29.481662"}

-- POST http://localhost/ask --
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Main Cloud Deployment & Config Comparison
- Platform: <!-- Điền sau khi deploy xong (Render hoặc Railway) -->
- Public URL: <!-- Điền URL public sau khi deploy -->
- Screenshots: `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

**So sánh `railway.toml` và `render.yaml` (khác nhau chỗ nào & vì sao):**

| Tiêu chí | `railway.toml` | `render.yaml` (Render Blueprint) |
|---|---|---|
| **Định dạng & phạm vi** | **TOML**, cấu hình **1 service duy nhất** (mỗi service trên Railway có thể dùng file riêng hoặc dashboard). | **YAML**, là **Infrastructure-as-Code (Blueprint)** mô tả cùng lúc **nhiều service** (web service, Redis/Key Value, PostgreSQL, worker) trong 1 file duy nhất. |
| **Khai báo build & runtime** | Mục `[build]` chỉ rõ `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` (hoặc Nixpacks/Railpack). | Nằm trong từng item của `services:` với `type: web`, `runtime: docker`, `plan: free`. |
| **Health check & Restart** | `[deploy]` dùng `healthcheckPath = "/health"`, `healthcheckTimeout = 30`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3`. | Dùng `healthCheckPath: /health` ngay trong cấu hình service; chính sách restart do nền tảng tự quản lý. |
| **Biến môi trường & Secrets** | Không khai báo danh sách `envVars` trực tiếp trong `railway.toml`; toàn bộ biến & secret được đặt qua Railway Dashboard hoặc CLI (`railway variables set`). | Khai báo rõ `envVars:` trong file: biến thường dùng `value:`, còn **secret** bắt buộc dùng `generateValue: true` (nền tảng tự sinh ngẫu nhiên) hoặc `sync: false` (nhập tay trên Dashboard) để không bao giờ commit secret vào Git. |
| **Vì sao có sự khác biệt này?** | Railway hướng tới trải nghiệm deploy cực nhanh qua CLI/Dashboard cho từng service rời lẻ, ghép Redis bằng thao tác thêm plugin trong project. | Render Blueprint hướng tới tái lập toàn bộ kiến trúc (web + database/cache + env) từ 1 file Git duy nhất theo mô hình GitOps/IaC. |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Pipeline CI/CD trong `cloudbuild.yaml` tự động chạy khi push lên nhánh `main` và đi qua **4 bước tuần tự** (mỗi bước dùng `waitFor` để chỉ chạy khi bước trước thành công):
1. **Test (`test`):** Dùng container `python:3.11-slim` cài `requirements.txt`, `pytest` và chạy `pytest tests/ -v` — nếu test fail sẽ dừng pipeline ngay, không build/deploy bản lỗi.
2. **Build (`build`):** Dùng `cloud-builders/docker` build image gắn 2 tag (`:$COMMIT_SHA` và `:latest`), tận dụng `--cache-from` từ image `:latest` để tăng tốc build.
3. **Push (`push`):** Đẩy toàn bộ tag của image vừa build lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Gọi `gcloud run deploy` triển khai đúng image `:$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình public endpoint, scale `1..10` instance (tránh cold start), giới hạn `512Mi` RAM / `1` CPU, và nạp secret từ **Secret Manager** (`--set-secrets`) thay vì hardcode. Song song đó, `service.yaml` định nghĩa cấu hình tương đương theo chuẩn Knative IaC (`containerConcurrency: 80`, `livenessProbe` tại `/health`, `startupProbe` tại `/ready` và tham chiếu `secretKeyRef` từ Secret Manager).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)
- **Kiểm tra ở đâu:** Tại dependency `verify_api_key` dùng `APIKeyHeader(name="X-API-Key", auto_error=False)` và gắn vào endpoint `POST /ask` qua `Depends(verify_api_key)`.
- **Khi thiếu hoặc sai key:** Thiếu header trả `401 Unauthorized`, sai key trả `403 Forbidden` (ở Part 6 chuẩn hóa cả hai thành `401`).
- **Cách rotate key:** Đọc key từ biến môi trường (`AGENT_API_KEY`) thay vì hardcode; trong thực tế production hỗ trợ tạm thời cả key cũ và key mới (hoặc tập key) trong thời gian chuyển đổi rồi thu hồi key cũ sau khi client đã cập nhật.

**Kết quả test thực tế (`AGENT_API_KEY=secret-key-123`):**

```http
-- Không có API Key -> 401 --
HTTP/1.1 401 Unauthorized
server: uvicorn
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

-- Có X-API-Key: secret-key-123 -> 200 --
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **Thuật toán trong `rate_limiter.py`:** **Sliding Window Counter** lưu danh sách timestamp trong `collections.deque` cho từng `user_id` (loại bỏ các timestamp cũ hơn `now - 60s`, đếm số request còn lại trong cửa sổ 60 giây). Trong production nhiều instance phải chuyển sang lưu trong Redis Sorted Set như Part 6.
- **Giới hạn:** Tài khoản user thường (`student`) là **10 requests/phút** (`rate_limiter_user`); tài khoản admin là **100 requests/phút** (`rate_limiter_admin`) — phân tách theo trường `role` trong JWT payload (hoặc có thể bỏ qua kiểm tra limiter nếu `role == "admin"`).

**Kết quả test thực tế (`POST /auth/token` với `student`/`demo123`, token đã được che `<REDACTED_TOKEN>`):**

```http
-- Request #1 với Authorization: Bearer <REDACTED_TOKEN> -> 200 --
HTTP/1.1 200 OK
server: uvicorn
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

Vòng lặp gọi tiếp Request `#2` → `#11`:
```text
Request #2  -> HTTP 200
Request #3  -> HTTP 200
Request #4  -> HTTP 200
Request #5  -> HTTP 200
Request #6  -> HTTP 200
Request #7  -> HTTP 200
Request #8  -> HTTP 200
Request #9  -> HTTP 200
Request #10 -> HTTP 200
Request #11 -> HTTP 429
```

Chi tiết `curl -i` khi chạm ngưỡng Rate Limit (Request `#11`):
```http
HTTP/1.1 429 Too Many Requests
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795598404
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cost Guard Implementation
- **Cách hoạt động:**
  - Trước khi gọi LLM (`check_budget`): đọc tổng chi phí tích lũy từ Redis theo key theo ngày/tháng (ví dụ `cost:daily:YYYY-MM-DD` hoặc `budget:{user_id}:{YYYY-MM}`). Nếu chi phí đã đạt hoặc vượt ngưỡng (`DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD` — ví dụ \$10/tháng) thì chặn ngay bằng **HTTP 402 Payment Required** (hoặc `503` nếu chạm ngân sách toàn hệ thống).
  - Sau khi gọi LLM (`record_cost`): tính chi phí theo số lượng `input_tokens` và `output_tokens` rồi cộng nguyên tử vào Redis bằng `INCRBYFLOAT` kèm `EXPIRE` (TTL > chu kỳ ngày/tháng để tự reset).
- **Tại sao cần cả Rate Limit lẫn Cost Guard?**
  - **Rate Limit** bảo vệ **tốc độ truy cập & tài nguyên server** (chặn spam/DDoS theo số request/phút).
  - **Cost Guard** bảo vệ **ngân sách tiền thật cho LLM API** (vì một user vẫn có thể gửi đều đặn dưới mức rate limit nhưng mỗi câu hỏi chứa hàng chục nghìn token gây đội chi phí rất nhanh).

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Health Checks, Graceful Shutdown & Stateless Design
- **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
  - `/health` (Liveness probe) chỉ kiểm tra process ứng dụng còn sống hay không (luôn trả `200`, không phụ thuộc Redis/DB) → tránh việc orchestrator restart vòng lặp container khi chỉ có Redis bị mất kết nối tạm thời.
  - `/ready` (Readiness probe) kiểm tra kết nối tới các dịch vụ phụ thuộc (ping Redis/DB); trả `200` khi sẵn sàng và `503` khi chưa sẵn sàng → Load Balancer tạm ngưng đẩy traffic vào instance đó cho đến khi phục hồi.
- **Graceful Shutdown (`SIGTERM`):** Khi nhận `SIGTERM` (lúc deploy phiên bản mới hoặc scale down), server ngừng nhận kết nối mới, hoàn thành các request đang chạy dở, đóng kết nối Redis/DB rồi mới thoát với exit code `0`.
- **Stateless Design:** Không lưu lịch sử hội thoại, rate limit hay chi phí trong biến `dict` trên RAM của process. Nếu lưu trong RAM, khi chạy nhiều instance sau Nginx Load Balancer, request 1 vào `instance-A` nhưng request 2 vào `instance-B` sẽ bị mất toàn bộ ngữ cảnh hội thoại (và mất sạch khi container restart). Giải pháp là chuyển toàn bộ state sang **Redis** dùng chung.

### Exercise 5.4 & 5.5: Load Balancing (3 instances) & Stateless Test (`05-scaling-reliability/production/`)

Chạy stack với 3 agent instances sau Nginx (cổng `8080`, endpoint `POST /chat`):
```bash
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
docker compose -p k5-day14-scaling down -v
```

**Trạng thái các container (`docker compose -p k5-day14-scaling ps`):**
```text
NAME                       SERVICE   STATUS
k5-day14-scaling-agent-1   agent     Up 12 seconds (healthy)
k5-day14-scaling-agent-2   agent     Up 11 seconds (healthy)
k5-day14-scaling-agent-3   agent     Up 11 seconds (healthy)
k5-day14-scaling-nginx-1   nginx     Up 11 seconds
k5-day14-scaling-redis-1   redis     Up 22 seconds (healthy)
```

**Kết quả thực tế chạy `python test_stateless.py`:**
```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 5a15bb1d-1dc4-44b5-b1c0-104bff0679ce

Request 1: [instance-805034]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-8f76d0]
  Q: Why do we need containers?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 3: [instance-805034]
  Q: What is Kubernetes?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 4: [instance-f105d6]
  Q: How does load balancing work?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 5: [instance-8f76d0]
  Q: What is Redis used for?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-f105d6', 'instance-805034', 'instance-8f76d0'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Kubernetes?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: How does load balancing work?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Redis used for?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...

✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:** 5 request trong cùng 1 `session_id` được Nginx phân tải đều qua cả **3 instance khác nhau** (`instance-805034`, `instance-8f76d0`, `instance-f105d6`). Khi gọi `GET /chat/{session_id}/history`, toàn bộ **10 tin nhắn** (5 câu hỏi + 5 câu trả lời) vẫn còn nguyên vẹn vì mọi instance đều đọc/ghi chung vào Redis thay vì RAM cục bộ.

---

## Part 6: Final Project — Production Readiness Check (`PASS 12/12`)

Chạy đầy đủ trong WSL2 Ubuntu-24.04 (`os.name = posix`, Docker 29.9.3):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

- Kích thước Docker image thực đo: **270 MB** (< 500 MB, multi-stage `python:3.11-slim`, user non-root `appuser`).
- Thời gian `docker stop` (graceful shutdown): **0.7s**, exit code **0**.

---

## AI Log (Khai báo sử dụng AI theo RULES.md)

| Thời điểm / Phần bài | Câu hỏi / Yêu cầu gửi cho AI | Nội dung AI hỗ trợ | Cách tự kiểm tra & chỉnh sửa |
|---|---|---|---|
| Setup & Rà soát quy định | Đọc cấu trúc repo, rubric, luật lab để tránh bị trừ điểm | Tổng hợp yêu cầu nộp bài, kiểm tra `.gitignore`, tạo file `.env.local` rỗng và khung file nộp bài chuẩn theo `SUBMISSION.md` & `RULES.md` | Tự đối chiếu với `SUBMISSION.md`, `RUBRIC.md`, `RULES.md` và kiểm tra `git status` / `git check-ignore` |
| Part 6 (`06-lab-complete/`) | Hoàn thiện các `TODO` cho Production AI Agent và giải thích kiến trúc từng module | Viết mã nguồn các module trong `06-lab-complete/app/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`) và cấu hình `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml` | Chạy kiểm tra đầy đủ `python check_production_ready.py` trong WSL2 Ubuntu có Docker, đạt `PASS 12/12 (43/43 checks passed)`, image 270 MB, tắt êm 0.7s, đọc hiểu giải thích từng module |
| Part 1, 2, 4, 5 (`MISSION_ANSWERS.md`) | Chạy thực nghiệm các bài mẫu Part 1, 2, 4, 5, tổng hợp câu trả lời và giải thích | Hỗ trợ chạy lệnh thực nghiệm trong WSL2 + Docker, tổng hợp bảng so sánh, sơ đồ kiến trúc và câu trả lời dựa trên output thực đo | Tự xác minh toàn bộ số đo thực tế từ máy (`1.67 GB` vs `240 MB`, `401/200/429`, 3 instance `test_stateless.py`), che JWT token trước khi lưu |
| Part 7 (`BENCHMARK_REPORT.md`) | Thực hiện benchmark hiệu năng/chất lượng (CP7), chạy Observability stack, chaos alert, chụp 4 ảnh và viết báo cáo (CP8) | Thêm metric `agent_question_length_chars`, sửa `KNOWLEDGE_BASE` trong `mock_llm.py`, sửa lỗi thiếu `PYTHONUSERBASE` trong `production/Dockerfile`, chạy `load_test.py`, `run_eval.py`, Locust headless, kích hoạt 2 alert firing, chụp 4 ảnh và tổng hợp `BENCHMARK_REPORT.md` | Đối chiếu từng con số trong `BENCHMARK_REPORT.md` khớp 100% với 10 file JSON trong `reports/`, 2 file CSV trong `benchmark-results/` và 4 ảnh trong `screenshots/`; dọn sạch Docker stack sau khi xong |
| Part 3 lý thuyết (`MISSION_ANSWERS.md`) | So sánh `railway.toml` vs `render.yaml` và mô tả pipeline CI/CD Cloud Run (Exercise 3.3) | Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml`, `service.yaml` và viết bảng so sánh cấu hình + tóm tắt 4 bước pipeline CI/CD | Đối chiếu trực tiếp với `railway.toml`, `render.yaml`, `cloudbuild.yaml`, `service.yaml` và yêu cầu trong `RUBRIC.md` |
