# alipayPY 项目改造指南 - 支持 New-API 支付链接

## 📋 改造概览

将原有的 alipayPY 项目（纯支付宝扫码支付）改造为支持 New-API 的支付网关代理。保留所有现有功能，同时增加 EPay 协议支持，使其能直接对接 New-API 的充值系统。

### 核心改造内容：

| 功能 | 改造前 | 改造后 |
|------|--------|--------|
| 支付下单 | `/paynow` 页面输入 | `/submit.php` (EPay 协议) + `/paynow` |
| 商户验证 | 无需验证 | MD5 签名验证（商户密钥） |
| 回调通知 | 仅支付宝回调 | 支付宝回调 + New-API 回调 |
| 订单存储 | 内存（重启丢失） | **SQLite/MySQL 数据库** |
| 调用方 | 手动输入 | New-API 自动调用 |

---

## 🚀 快速开始（5分钟）

### 第1步：下载改造文件

从 `alipayPY_改造包` 目录下载以下文件，覆盖原项目：

```
alipayPY/
├── app_api.py           # ✏️ 替换
├── alipay_config.py     # ✏️ 替换
├── requirements.txt     # ✏️ 替换
├── .env.example         # ✏️ 替换
├── epay_util.py         # ✨ 新增
└── （其他文件保持不变）
```

### 第2步：安装依赖

```bash
# 激活虚拟环境（如使用 venv）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 第3步：配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入配置
# 关键配置：
# 1. 支付宝配置（ALIPAY_APP_ID, ALIPAY_APP_PRIVATE_KEY 等）
# 2. New-API 配置（EPAY_MERCHANT_ID, EPAY_MERCHANT_KEY）
# 3. 本服务地址（EPAY_NOTIFY_BASE_URL）
```

### 第4步：启动服务

```bash
python app_api.py
```

看到以下日志说明启动成功：

```
🎉 支付宝配置 + EPay 配置初始化成功！
🚀 启动 Flask 应用【改造版 - 支持 New-API】
  - 地址: 0.0.0.0:5000
  - 环境: development
  - EPay 商户ID: 1673765678
```

### 第5步：在 New-API 配置支付方式

1. 登录 New-API 后台
2. 进入 **充值管理** → **支付方式** 
3. 新增/编辑支付方式：
   - 类型：**EPay**
   - 商户 ID：`1673765678`（与 .env 中 EPAY_MERCHANT_ID 一致）
   - 商户密钥：`xm3787562987`（与 .env 中 EPAY_MERCHANT_KEY 一致）
   - API 地址：`http://你的服务器:5000/submit.php`
   - 回调地址 URL：`http://你的服务器:5000` （自动生成）

4. 保存并测试

---

## 📊 工作流程

```
┌─────────────┐
│  New-API    │ （用户点击充值）
└──────┬──────┘
       │ 1. POST /submit.php
       │    (EPay 协议，包含签名)
       ↓
┌──────────────────┐
│  alipayPY 服务   │ ← 验证商户 ID 和签名
│ (改造版)         │ ← 创建支付宝订单
│                  │ ← 返回二维码页面
└──────┬───────────┘
       │ 2. 用户扫码支付
       ↓
┌──────────────────┐
│  支付宝服务      │
└──────┬───────────┘
       │ 3. 支付完成回调
       │    /api/notify
       ↓
┌──────────────────┐
│  alipayPY 服务   │ ← 验证支付宝签名
│                  │ ← 标记订单为已支付
│                  │ ← 异步回调 New-API
└──────┬───────────┘
       │ 4. POST notify_url
       │    (EPay 协议，包含签名)
       ↓
┌─────────────┐
│  New-API    │ ← 收到成功响应
│             │ ← 自动充值完成
└─────────────┘
```

---

## 🔐 安全特性

### MD5 签名验证

所有来自 New-API 的请求都必须包含有效的 MD5 签名：

```python
# 签名算法（与 New-API 一致）
1. 过滤 sign、sign_type 和空值参数
2. 按 key 字母升序排序
3. 拼接为 key1=value1&key2=value2&...
4. 末尾直接追加商户密钥（无 & 分隔符）
5. 计算 MD5 哈希值

示例：
params = {
    'pid': '1673765678',
    'out_trade_no': 'order_123',
    'type': 'alipay',
    'money': '100.00',
}
sign_string = 'money=100.00&out_trade_no=order_123&pid=1673765678&type=alipay' + 'xm3787562987'
sign = md5(sign_string) = '5d41402abc4b2a76b9719d911017c592'
```

---

## 📡 API 接口文档

### 1. /submit.php - EPay 下单接口（New-API 调用）

**请求方式**：GET / POST  
**调用方**：New-API  
**认证**：MD5 签名

**请求示例**：
```
GET /submit.php?
  pid=1673765678&
  out_trade_no=order_20240410_001&
  type=alipay&
  money=100.00&
  name=充值100元&
  notify_url=https://new-api.com/notify&
  return_url=https://new-api.com/&
  sign=xxx&
  sign_type=MD5
```

**请求参数**：

| 参数 | 必需 | 说明 | 示例 |
|------|------|------|------|
| pid | ✓ | 商户 ID | 1673765678 |
| out_trade_no | ✓ | 商户订单号（唯一） | order_20240410_001 |
| type | ✓ | 支付类型 | alipay |
| money | ✓ | 支付金额（元） | 100.00 |
| name | ✓ | 商品名称 | 充值100元 |
| notify_url | ✓ | 支付成功回调地址 | https://new-api.com/notify |
| return_url | ✗ | 支付成功返回地址 | https://new-api.com/ |
| sign | ✓ | MD5 签名 | - |
| sign_type | ✓ | 签名类型 | MD5 |

**返回**：
- 成功：支付二维码展示页面（HTML）
- 失败：错误信息（字符串或 400/500 状态码）

**工作流程**：
1. 验证 MD5 签名
2. 验证商户 ID
3. 检查订单是否已存在（幂等性）
4. 调用支付宝 API 创建预下单
5. 保存订单到数据库
6. 返回支付二维码页面

---

### 2. /api/check-status - 订单状态查询（前端轮询）

**请求方式**：GET  
**调用方**：前端（JavaScript）  
**认证**：无

**请求示例**：
```
GET /api/check-status?out_trade_no=order_20240410_001
```

**返回示例**：
```json
{
  "code": 0,
  "status": 1,
  "message": "支付成功"
}
```

**状态值**：
- 0: 支付失败/订单已关闭
- 1: 支付成功
- 2: 已通知（仅内部使用）

---

### 3. /api/notify - 支付宝异步回调（自动）

**请求方式**：POST  
**调用方**：支付宝服务器  
**认证**：RSA 签名（支付宝）

**工作流程**：
1. 接收支付宝的异步通知
2. 验证支付宝 RSA 签名
3. 标记订单为已支付
4. **异步回调 New-API 的 notify_url**

---

### 4. New-API 回调通知（自动）

当订单支付成功且需要通知 New-API 时，本服务会自动发起以下请求：

**请求方式**：POST  
**请求地址**：订单中的 `notify_url` 参数  
**认证**：MD5 签名

**请求示例**：
```
POST https://new-api.com/notify

trade_no=EP202404101234567890&
out_trade_no=order_20240410_001&
money=100.00&
pid=1673765678&
type=alipay&
status=1&
sign=xxx&
sign_type=MD5
```

**回调参数**：

| 参数 | 说明 | 示例 |
|------|------|------|
| trade_no | 平台订单号 | EP202404101234567890 |
| out_trade_no | 商户订单号 | order_20240410_001 |
| money | 支付金额（元） | 100.00 |
| pid | 商户 ID | 1673765678 |
| type | 支付类型 | alipay |
| status | 支付状态 | 1 (已支付) |
| sign | MD5 签名 | - |
| sign_type | 签名类型 | MD5 |

**New-API 需要**：
- 验证签名
- 返回字符串 `success` 确认收到
- 不返回或返回其他内容时，本服务会进行重试

**重试策略**：
- 首次：实时回调
- 之后：每 30 秒定时扫描一次未通知的订单
- 重试次数：最多 5 次

---

## 📊 数据库表结构

### pay_order 表

```sql
CREATE TABLE pay_order (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    
    -- EPay 订单字段
    out_trade_no VARCHAR(64) UNIQUE NOT NULL,  -- 商户订单号
    trade_no VARCHAR(64),                      -- 平台交易号
    
    -- 商户信息
    pid INTEGER,                               -- 商户 ID
    type VARCHAR(16),                          -- 支付类型
    
    -- 订单信息
    name VARCHAR(128),                         -- 商品名称
    money FLOAT,                               -- 金额（元）
    
    -- 回调信息
    notify_url VARCHAR(512),                   -- 回调地址
    return_url VARCHAR(512),                   -- 返回地址
    
    -- 状态
    status INTEGER DEFAULT 0,                  -- 0=待支付, 1=已支付, 2=已通知
    
    -- 第三方信息
    alipay_trade_no VARCHAR(64),               -- 支付宝交易号
    qr_code TEXT,                              -- 二维码 URL
    
    -- 通知重试
    notify_count INTEGER DEFAULT 0,            -- 已通知次数
    
    -- 时间戳
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW() ON UPDATE NOW()
);
```

---

## 🔧 配置详解

### 支付宝配置（ALIPAY_*）

获取方式：
1. 登录[蚂蚁开放平台](https://open.alipay.com)
2. 创建或选择应用
3. 配置 **电脑网站支付** 和 **当面付**
4. 获取 AppID、私钥、公钥

### New-API 配置（EPAY_*）

| 配置项 | 获取方式 | 示例 |
|--------|---------|------|
| EPAY_MERCHANT_ID | New-API 后台 → 充值管理 | 1673765678 |
| EPAY_MERCHANT_KEY | New-API 后台 → 充值管理 | xm3787562987 |
| EPAY_NOTIFY_BASE_URL | 本服务的公网地址 | http://pay.example.com |

**⚠️ 关键点**：
- `EPAY_MERCHANT_ID` 和 `EPAY_MERCHANT_KEY` 必须与 New-API 配置一致
- `EPAY_MERCHANT_KEY` 是密钥，不要泄露
- `EPAY_NOTIFY_BASE_URL` 必须是公网可访问的地址

### 数据库配置（DATABASE_*）

**SQLite（默认，适合开发/小型部署）**：
```
DATABASE_TYPE=sqlite
SQLITE_PATH=./data/orders.db
```

**MySQL（推荐生产环境）**：
```
DATABASE_TYPE=mysql
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_DB=alipay_db
```

---

## 🐛 常见问题排查

### 问题 1: "Invalid Signature"

**原因**：MD5 签名验证失败  
**排查**：
1. 确认 `EPAY_MERCHANT_KEY` 与 New-API 配置一致
2. 检查签名算法是否按照规则执行
3. 查看日志中的 `EPay签名字符串` 是否正确

### 问题 2: "商户ID不匹配"

**原因**：请求中的 pid 与 `EPAY_MERCHANT_ID` 不一致  
**排查**：
1. 检查 .env 中的 `EPAY_MERCHANT_ID`
2. 检查 New-API 中配置的商户 ID
3. 两者必须保持一致

### 问题 3：支付成功但 New-API 未收到通知

**排查步骤**：
1. 查看 alipayPY 日志中是否有 "回调 New-API" 的日志
2. 检查 New-API 是否收到请求（查看 New-API 的请求日志）
3. 检查 `EPAY_NOTIFY_BASE_URL` 是否配置正确
4. 确保 New-API 的回调地址可公网访问

**重试机制**：
- 如果首次回调失败，系统会在后续 30 秒内重试
- 最多重试 5 次

### 问题 4：数据库相关错误

**SQLite**：
- 确保 `./data/` 目录存在或可创建
- 检查文件权限

**MySQL**：
- 确保 MySQL 服务运行中
- 检查连接器参数是否正确
- 运行 `pip install pymysql`

---

## 📈 监控与维护

### 查看日志

```bash
# 实时查看日志
python app_api.py

# 配置日志级别
LOG_LEVEL=DEBUG python app_api.py
```

### 数据库查询

**SQLite**：
```bash
sqlite3 ./data/orders.db
> SELECT * FROM pay_order WHERE status = 1;
```

**MySQL**：
```bash
mysql -u root -p alipay_db
> SELECT * FROM pay_order WHERE status = 1;
```

### 监控关键指标

| 指标 | 查询 | 说明 |
|------|------|------|
| 待支付订单 | `status = 0` | 需要跟进的订单 |
| 已支付订单 | `status = 1` | 已支付但未通知 |
| 已通知订单 | `status = 2` | 完整交易记录 |
| 重试次数 | `notify_count` | 回调重试次数 |

---

## 🚢 部署指南

### 开发环境

```bash
# 本地运行
python app_api.py
# 访问 http://localhost:5000
```

### 生产环境

#### 使用 Gunicorn：

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app_api:app
```

#### 使用 Docker：

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p data

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app_api:app"]
```

#### 使用 Nginx（HTTPS）：

```nginx
server {
    listen 443 ssl http2;
    server_name pay.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### 使用 systemd（Linux）：

```ini
[Unit]
Description=alipayPY Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/home/www-data/alipayPY
ExecStart=/usr/bin/python3 app_api.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## 📝 改造清单

- [x] 添加 EPay 协议支持 (`epay_util.py`)
- [x] 实现 `/submit.php` 接口
- [x] 添加 MD5 签名验证
- [x] 集成数据库持久化
- [x] 实现异步回调通知
- [x] 添加重试机制
- [x] 编写完整文档
- [x] 提供配置范例

---

## 💡 下一步

1. **备份现有数据**（如果有）
2. **按照快速开始步骤**部署改造版本
3. **在测试环境验证**功能
4. **配置 New-API**
5. **进行端到端支付测试**
6. **上线生产环境**

---

## 📞 技术支持

如有问题，请查看以下资源：

- 支付宝接入文档：https://opendocs.alipay.com/
- New-API 文档：https://github.com/QuantumNous/new-api
- 项目日志：`python app_api.py` 的控制台输出

---

**祝改造顺利！** 🎉
