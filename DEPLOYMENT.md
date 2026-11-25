# Deployment Information

## Public URL
https://k5-l3a-day14-tranmanhhung-2a202603496.onrender.com

## Platform
Render (Web Service chạy Docker từ `06-lab-complete/` + Render Key Value / Redis)

## Test Commands (Self-Test CP6 — không lộ API key thật)

```bash
export BASE="https://k5-l3a-day14-tranmanhhung-2a202603496.onrender.com"
# Nhập key đã đặt trên Render Dashboard (không lưu trong repo):
read -s -p "AGENT_API_KEY: " AGENT_API_KEY && echo ""

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
- `PORT` (do Render tự động cấp, mặc định `10000`)
- `REDIS_URL` (Internal Key Value URL trỏ tới Redis service cùng region trên Render)
- `AGENT_API_KEY` (tạo bằng nút Generate trực tiếp trên Render Dashboard, không lưu trong repo)
- `ENVIRONMENT` (`production`)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`10.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
