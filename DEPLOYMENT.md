# Deployment Information

## Public URL
<!-- Điền URL sau khi deploy ở CP6, ví dụ: https://your-agent.up.railway.app -->

## Platform
<!-- Railway hoặc Render -->

## Test Commands (Self-Test CP6 — không lộ API key thật)

```bash
# Đặt biến môi trường trên máy local khi test (KHÔNG ghi key thật vào file này):
# export BASE="https://your-agent.up.railway.app"
# export AGENT_API_KEY="<YOUR_SECRET_API_KEY>"

# 1. Liveness check (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check với Redis (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Không có API Key (Expected: 401)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. Có API Key hợp lệ (Expected: 200)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Environment Variables Set on Platform
- `PORT` (hoặc do nền tảng tự cấp)
- `REDIS_URL` (trỏ tới Redis service trên cloud, giá trị thực tế đặt trên Dashboard)
- `AGENT_API_KEY` (đặt trực tiếp trên Dashboard, không lưu trong repo)
- `RATE_LIMIT_PER_MINUTE`
- `DAILY_BUDGET_USD`
- `ENVIRONMENT`
- `LOG_LEVEL`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
