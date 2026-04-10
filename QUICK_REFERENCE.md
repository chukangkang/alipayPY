# alipayPY 改造版 - 快速参考卡片

## 📦 文件变更清单

```
alipayPY/
├── ✨ epay_util.py           【新增】EPay MD5 签名工具
├── ✏️ app_api.py              【修改】添加 /submit.php 和回调逻辑
├── ✏️ alipay_config.py        【修改】添加 New-API 配置
├── ✏️ requirements.txt        【修改】添加 SQLAlchemy 依赖
├── ✏️ .env.example            【修改】添加 EPay 配置项
├── ✅ alipay_service.py       【无改动】
├── ✅ templates/pay.html      【无改动】
└── ✅ templates/test_pay.html 【无改动】
```

---

## 🚀 5分钟快速起步

```bash
# 1. 替换文件
cp alipayPY_改造包/*.py ./alipayPY/
cp alipayPY_改造包/requirements.txt ./alipayPY/
cp alipayPY_改造包/.env.example ./alipayPY/

# 2. 安装依赖
cd ./alipayPY
pip install -r requirements.txt

# 3. 配置环境
cp .env.example .env
# 编辑 .env，填入支付宝和 New-API 配置

# 4. 启动服务
python app_api.py

# 5. 测试
# 访问 http://localhost:5000/test （现有功能）
# 或配置 New-API 后直接调用
```

---

## 🔑 关键配置项

| 配置项 | 从哪里获得 | 用途 |
|--------|-----------|------|
| `ALIPAY_APP_ID` | 支付宝开放平台 | 调用支付宝 API |
| `ALIPAY_APP_PRIVATE_KEY` | 支付宝开放平台 | 签名（支付宝格式） |
| `ALIPAY_PUBLIC_KEY` | 支付宝开放平台 | 验签（支付宝回调） |
| `EPAY_MERCHANT_ID` | New-API 后台 | 验证商户身份 |
| `EPAY_MERCHANT_KEY` | New-API 后台 | MD5 签名密钥 |
| `EPAY_NOTIFY_BASE_URL` | 本服务公网地址 | 回调 New-API 时使用 |

---

## 📡 核心接口

### 1. /submit.php （New-API 调用）

```
GET /submit.php?pid=123&out_trade_no=order_1&type=alipay&money=100&name=充值&notify_url=http://new-api.com/notify&sign=xxx&sign_type=MD5
```

**返回**：支付二维码页面

### 2. /api/check-status （前端查询）

```
GET /api/check-status?out_trade_no=order_1
```

**返回**：`{code: 0, status: 1, message: "支付成功"}`

### 3. /api/notify （支付宝回调）

由支付宝自动调用，不需要手动调用

### 4. 回调 New-API

系统自动调用，格式：

```
POST https://new-api.com/notify?trade_no=xxx&out_trade_no=xxx&money=100&sign=xxx
```

---

## 🔐 MD5 签名算法

```python
# 签名步骤：
params = {
    'pid': '1673765678',
    'out_trade_no': 'order_123',
    'type': 'alipay',
    'money': '100.00',
}

# 1. 过滤 sign/sign_type 和空值
# 2. 按 key 字母升序排序
sorted_params = {'money': '100.00', 'out_trade_no': 'order_123', 'pid': '1673765678', 'type': 'alipay'}

# 3. 拼接为 key=value&...
sign_str = 'money=100.00&out_trade_no=order_123&pid=1673765678&type=alipay'

# 4. 末尾追加商户密钥（无 & 分隔符）
sign_str += 'xm3787562987'

# 5. MD5 哈希
sign = md5(sign_str).hexdigest()  # 小写十六进制
```

---

## 📊 数据库表结构

```sql
pay_order:
  id              INTEGER PRIMARY KEY
  out_trade_no    VARCHAR(64)  -- 商户订单号
  trade_no        VARCHAR(64)  -- 平台订单号
  pid             INTEGER      -- 商户 ID
  type            VARCHAR(16)  -- 支付类型 (alipay/wxpay)
  name            VARCHAR(128) -- 商品名称
  money           FLOAT        -- 金额
  notify_url      VARCHAR(512) -- 回调地址
  status          INTEGER      -- 0=待支付, 1=已支付, 2=已通知
  alipay_trade_no VARCHAR(64)  -- 支付宝交易号
  qr_code         TEXT         -- 二维码 URL
  notify_count    INTEGER      -- 重试次数
  created_at      DATETIME
  updated_at      DATETIME
```

---

## 🔄 支付流程

```
1. New-API 调用
   GET /submit.php?pid=...&out_trade_no=...&sign=...

2. 验证签名 ✓

3. 创建支付宝订单
   返回 → 二维码页面

4. 用户扫码支付

5. 支付宝回调
   POST /api/notify

6. 标记订单已支付

7. 异步回调 New-API
   POST notify_url

8. New-API 返回 success

9. 标记订单已通知 ✓
```

---

## 🐛 测试命令

```bash
# 测试支付（现有功能）
curl "http://localhost:5000/test"

# 查询订单状态
curl "http://localhost:5000/api/check-status?out_trade_no=order_123"

# 测试 submit.php（需签名）
# 使用工具生成签名后调用
python -c "
from epay_util import sign_epay
params = {
    'pid': '1673765678',
    'out_trade_no': 'order_test_001',
    'type': 'alipay',
    'money': '0.01',
    'name': 'Test',
    'notify_url': 'http://localhost:5000/api/notify',
}
sign = sign_epay(params, 'xm3787562987')
print(f'sign={sign}')
"

# 然后调用
curl "http://localhost:5000/submit.php?pid=1673765678&out_trade_no=order_test_001&type=alipay&money=0.01&name=Test&notify_url=http://localhost:5000/api/notify&sign=XXXXX&sign_type=MD5"
```

---

## 📁 目录结构

```
alipayPY/
├── data/                 【新增】数据库文件夹
│   └── orders.db        (SQLite 数据库)
├── templates/
│   ├── pay.html
│   └── test_pay.html
├── alipay_config.py      【改】增加 New-API 配置类
├── alipay_service.py
├── app_api.py            【改】增加 /submit.php 接口
├── epay_util.py          【新】MD5 签名工具
├── requirements.txt      【改】增加 sqlalchemy
├── .env.example          【改】增加 EPay 配置
├── .env                  【新】实际配置（不提交 Git）
├── .gitignore
└── README.md
```

---

## 💾 .env 最小配置

```bash
# 支付宝（必需）
ALIPAY_APP_ID=2021006132666221
ALIPAY_APP_PRIVATE_KEY=MIIEvAIBA...
ALIPAY_PUBLIC_KEY=MIIBIjANBg...
ALIPAY_IS_SANDBOX=false
ALIPAY_NOTIFY_URL=http://你的域名:5000/api/notify

# New-API（必需）
EPAY_MERCHANT_ID=1673765678
EPAY_MERCHANT_KEY=xm3787562987
EPAY_NOTIFY_BASE_URL=http://你的域名:5000

# Flask
FLASK_ENV=production
FLASK_PORT=5000
```

---

## ⚡ 性能优化

### 异步处理

- 支付成功后，**异步线程**回调 New-API（不阻塞主流程）
- 定时任务每 30 秒检查一次未通知的订单

### 数据库连接

- **SQLite**（开发）：内置支持，无需配置
- **MySQL**（生产）：使用连接池，性能更好

### 日志级别

```bash
LOG_LEVEL=INFO    # 生产环境
LOG_LEVEL=DEBUG   # 开发环境
```

---

## 🚨 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| "签名验证失败" | `EPAY_MERCHANT_KEY` 错误 | 检查与 New-API 配置是否一致 |
| "商户ID不匹配" | `EPAY_MERCHANT_ID` 错误 | 检查配置 |
| "订单不存在" | 数据库没有创建表 | 重启应用自动创建 |
| "支付宝未返回二维码" | 支付宝配置错误 | 检查 `ALIPAY_*` 配置 |
| "回调超时" | `EPAY_NOTIFY_BASE_URL` 不可访问 | 使用公网地址，检查防火墙 |

---

## 📞 快速问题排查

**Q: 改造后原有功能是否还能用？**  
A: 完全兼容！所有原有接口（/test、/paynow 等）都保留

**Q: 必须使用 MySQL 吗？**  
A: 不必。默认 SQLite 适合开发/小型，生产推荐 MySQL

**Q: 支持微信支付吗？**  
A: 当前仅支持支付宝。微信支付可后续添加

**Q: 回调失败会怎样？**  
A: 每 30 秒重试一次，最多 5 次，之后放弃

**Q: 生产环境推荐配置？**  
A: MySQL + Gunicorn + Nginx(HTTPS) + 系统服务管理

---

## 📚 相关资源

- [EPay 协议文档](https://github.com/QuantumNous/new-api)
- [支付宝接入文档](https://opendocs.alipay.com/open/200/105285)
- [SQLAlchemy 快速指南](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)

---

**更新时间**：2024-04-10  
**版本**：1.0  
**状态**：✅ 生产就绪
