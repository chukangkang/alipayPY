# alipayPY - 支付宝 + EPay 支付网关代理

轻量级支付宝扫码支付服务，支持 **New-API EPay 协议集成**和**订单数据库管理**。

> 原始功能保留 + 新增 EPay 协议支持 + 生产级订单管理

---

## 📋 项目概述

| 功能 | 说明 |
|------|------|
| **支付宝集成** | RSA2 签名、当面付扫码、二维码生成 |
| **EPay 协议** | MD5 签名验证、New-API 下单接口 (`/submit.php`) |
| **订单管理** | SQLAlchemy ORM + SQLite/MySQL 数据库持久化 |
| **异步回调** | 支付成功自动通知 New-API，含重试机制 |
| **本地测试** | `/test` 页面直接测试支付 |

---

## 🚀 快速开始（5分钟）

### 第1步：环境要求

- Python 3.11+
- pip 包管理器

### 第2步：安装依赖

```bash
# 创建虚拟环境（可选但推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 第3步：配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入以下必需配置：
```

**支付宝配置项：**

```env
# 获取方式：支付宝开放平台 (https://open.alipay.com)
ALIPAY_APP_ID=2021000000000000
ALIPAY_APP_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----
ALIPAY_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----

# 可选配置
ALIPAY_SIGN_TYPE=RSA2
ALIPAY_FORMAT=json
ALIPAY_CHARSET=utf-8
ALIPAY_IS_SANDBOX=false  # true使用沙箱，false使用正式环境
ALIPAY_NOTIFY_URL=http://your-domain:5000/api/notify
ALIPAY_RETURN_URL=http://your-domain:5000/alipay/return
```

**New-API 配置项：**（若需要 EPay 集成）

```env
EPAY_MERCHANT_ID=1673765678
EPAY_MERCHANT_KEY=xm3787562987
EPAY_NOTIFY_BASE_URL=http://your-domain:5000
```

**数据库配置：**

```env
# SQLite（默认，开发环境推荐）
DB_URL=sqlite:///pay_orders.db

# MySQL（生产环境推荐，需先安装 pymysql）
# DB_URL=mysql+pymysql://用户名:密码@localhost:3306/alipay_db

# PostgreSQL
# DB_URL=postgresql://用户名:密码@localhost:5432/alipay_db
```

**其他配置：**

```env
FLASK_PORT=5000
FLASK_ENV=development  # 或 production
FLASK_SECRET_KEY=your-secret-key-here
LOG_LEVEL=INFO  # DEBUG/INFO/WARNING/ERROR
```

### 第4步：启动服务

```bash
python app_api.py
```

看到以下日志说明启动成功：

```
✓ AlipayService 初始化成功
🚀 启动 Flask 应用【改造版 - 支持 New-API】
  - 地址: 0.0.0.0:5000
  - 环境: development
```

### 第5步：测试支付

浏览器访问：**http://localhost:5000/test**

- 填写金额和商品标题
- 点击"立即支付"，新标签页显示支付二维码
- 使用支付宝扫描（或支付宝沙箱测试账户）

---

## 📡 API 接口

### 1️⃣ 支付页面（Web）

#### GET `/paynow`

直接渲染支付宝扫码支付页面

**参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `amount` 或 `total_amount` | float | ✅ | 金额（元），必须大于0 |
| `subject` | string | ✅ | 商品标题/描述 |
| `out_trade_no` | string | ❌ | 商户订单号，不传则自动生成 |

**示例：**

```html
<!-- 在新标签页打开支付页面 -->
<a href="/paynow?amount=9.90&subject=VIP会员" target="_blank">立即充值</a>

<!-- 跳转支付页面 -->
<a href="/paynow?amount=29.90&subject=月卡&out_trade_no=order_12345">购买月卡</a>
```

**返回：** HTML 支付页面（支付宝二维码）

---

### 2️⃣ 创建支付（JSON API）

#### POST `/api/pay/create`

供后端服务调用，生成支付二维码

**请求体：**

```json
{
  "total_amount": 99.90,
  "subject": "商品名称",
  "out_trade_no": "order_20240410_001"
}
```

**返回成功（200）：**

```json
{
  "code": 0,
  "data": {
    "order_id": "order_20240410_001",
    "qr_code": "https://qr.alipay.com/...",
    "amount": 99.90,
    "subject": "商品名称"
  }
}
```

**返回错误：**

```json
{
  "code": -1,
  "message": "金额必须大于0"
}
```

---

### 3️⃣ EPay 下单接口（New-API 调用）

#### POST/GET `/submit.php`

**EPay 协议兼容的下单接口**，New-API 支付网关调用此接口进行支付

**参数（POST/GET）：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `pid` | int | ✅ | 商户 ID（必须与 EPAY_MERCHANT_ID 一致） |
| `out_trade_no` | string | ✅ | 商户订单号（唯一） |
| `type` | string | ✅ | 支付类型：`alipay` / `wxpay`（暂仅支持alipay） |
| `money` | float | ✅ | 金额（元） |
| `name` | string | ✅ | 商品名称 |
| `notify_url` | string | ✅ | 支付成功回调地址 |
| `return_url` | string | ❌ | 支付成功返回地址 |
| `sign` | string | ✅ | MD5 签名 |
| `sign_type` | string | ✅ | 签名类型：`MD5` |

**签名生成算法（MD5）：**

```python
# 1. 过滤掉 sign、sign_type 和空值
# 2. 按 key 字母升序排序
# 3. 拼接：key1=value1&key2=value2&...
# 4. 末尾追加商户密钥（无 & 分隔）
# 5. MD5 哈希（小写十六进制）

from epay_util import sign_epay

params = {
    'pid': '1673765678',
    'out_trade_no': 'order_123',
    'type': 'alipay',
    'money': '100.00',
    'name': '充值100元',
    'notify_url': 'http://newapi.example.com/notify',
}
params['sign'] = sign_epay(params, 'xm3787562987')  # merchant_key
```

**返回：** HTML 支付页面（支付宝二维码）

---

### 4️⃣ 订单状态查询

#### GET `/api/check-status`

轮询查询订单支付状态

**参数：**

| 参数名 | 必填 | 说明 |
|--------|------|------|
| `out_trade_no` | ✅ | 商户订单号 |

**返回成功（200）：**

```json
{
  "code": 0,
  "status": 1,
  "message": "支付成功"
}
```

---

### 5️⃣ 支付宝异步回调

#### POST `/api/notify`

支付宝的异步回调地址，接收支付成功通知

**流程：**
1. 支付宝向此地址 POST 回调数据
2. 我们验证签名并更新订单状态
3. 返回 "success" 给支付宝

> ⚠️ **重要**：此地址需要配置在支付宝开放平台，且需要公网可访问

---

### 6️⃣ 支付宝同步返回

#### GET `/alipay/return`

用户支付成功后，支付宝页面跳转到此地址

> 此地址仅用于用户浏览器跳转提示，不作为支付成功凭证

---

## 📦 依赖清单

```
alipay-sdk-python>=3.7.1018    # 支付宝 SDK
flask>=3.0.0                   # Web 框架
requests>=2.31.0               # HTTP 请求
pycryptodome>=3.19.0           # RSA 签名（Python 3.11+ 兼容）
python-dotenv>=1.0.0           # 环境变量管理
sqlalchemy>=2.0.0              # 数据库 ORM
# pymysql>=1.1.0               # MySQL 驱动（可选，仅在使用 MySQL 时需要）
```

---

## 🗄️ 数据库

### SQLite（默认）

```env
DB_URL=sqlite:///pay_orders.db
```

优点：开发/测试方便，无需额外配置
缺点：并发性能一般，不适合高并发生产环境

### MySQL（生产推荐）

```bash
# 1. 安装 pymysql
pip install pymysql

# 2. 创建数据库
mysql -u root -p
> CREATE DATABASE alipay_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 3. 配置 .env
DB_URL=mysql+pymysql://root:password@localhost:3306/alipay_db
```

### 表结构

自动创建 `pay_order` 表，包含以下字段：

```sql
CREATE TABLE pay_order (
  id INT PRIMARY KEY AUTO_INCREMENT,
  out_trade_no VARCHAR(64) UNIQUE NOT NULL,
  trade_no VARCHAR(64),
  pid INT,
  type VARCHAR(16),
  name VARCHAR(128),
  money FLOAT,
  notify_url VARCHAR(512),
  return_url VARCHAR(512),
  status INT DEFAULT 0,
  alipay_trade_no VARCHAR(64),
  qr_code TEXT,
  notify_count INT DEFAULT 0,
  created_at DATETIME DEFAULT NOW(),
  updated_at DATETIME DEFAULT NOW() ON UPDATE NOW(),
  INDEX idx_out_trade_no (out_trade_no)
);
```

---

## 🔐 安全性

### 环境变量管理

❌ **不要硬编码敏感信息：**

```python
# ❌ 错误做法
ALIPAY_APP_ID = "2021000000000000"
```

✅ **从 .env 文件读取：**

```python
# ✅ 正确做法
from alipay_config import config
print(config.app_id)  # 从环境变量读取
```

### 签名验证

所有支付宝请求都使用 **RSA2** 签名验证，确保数据完整性。
EPay 协议使用 **MD5** 签名验证。

---

## 🌐 生产部署

### Gunicorn 启动（推荐）

```bash
# 安装 gunicorn
pip install gunicorn

# 启动（4 个 worker）
gunicorn -w 4 -b 0.0.0.0:5000 app_api:app
```

### Docker 部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV FLASK_ENV=production
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app_api:app"]
```

---

## 🐛 故障排查

### 签名验证失败

检查 `.env` 中的支付宝密钥是否正确，确保密钥格式为 PKCS#8。

### 数据库连接失败

检查数据库 URL 配置和连接权限。

### 支付宝返回 403

确认 `ALIPAY_APP_ID` 与签名密钥对应，检查签名方式是否为 `RSA2`。

---

## 📚 文件结构

```
alipayPY/
├── app_api.py                  # Flask 主应用
├── alipay_config.py            # 配置管理
├── alipay_service.py           # 支付宝服务
├── epay_util.py                # EPay 签名工具
├── requirements.txt            # 依赖列表
├── .env.example                # 环境变量示例
├── .gitignore                  # Git 忽略规则
├── templates/
│   ├── pay.html                # 支付页面（二维码展示）
│   └── test_pay.html           # 测试页面
├── README.md                   # 本文件
├── README_MIGRATION.md         # 改造指南（详细）
├── SUMMARY.md                  # 改造成果总结
└── QUICK_REFERENCE.md          # 快速参考卡片
```

---

## 📖 更多文档

- [改造指南](./README_MIGRATION.md) - 完整的改造细节和工作流程
- [快速参考](./QUICK_REFERENCE.md) - API 快速查询手册
- [改造成果](./SUMMARY.md) - 项目改造成果总结

---

## 💡 常见问题

**Q: 支持微信支付吗？**
A: 代码框架已预留 `wxpay` 类型，但当前仅支持支付宝，微信支付可后续扩展。

**Q: 支持多商户吗？**
A: 当前为单商户配置，多商户需基于此功能二次开发。

**Q: 订单数据会丢失吗？**
A: 使用数据库存储，不会丢失。建议定期备份数据库。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**最后更新：2026年4月10日**
