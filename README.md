# Alipay Demo

轻量级支付宝扫码支付演示项目，支持当面付（扫码支付）场景。

## 环境要求

- Python 3.11+
- Windows / Linux / macOS

## 安装依赖

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 配置环境变量

项目支持从 `.env` 文件加载配置（在项目根目录创建）：

```bash
# 复制示例配置
copy .env.example .env
```

编辑 `.env` 文件：

| 环境变量 | 说明 | 示例 |
|---------|------|------|
| `ALIPAY_APP_ID` | 支付宝应用 ID | 2021000000000000 |
| `ALIPAY_APP_PRIVATE_KEY` | 应用私钥（PKCS#8） | -----BEGIN PRIVATE KEY-----\n... |
| `ALIPAY_PUBLIC_KEY` | 支付宝公钥（验签用） | -----BEGIN PUBLIC KEY-----\n... |
| `ALIPAY_SIGN_TYPE` | 签名方式，默认 RSA2 | RSA2 |
| `ALIPAY_IS_SANDBOX` | 是否沙箱环境 | true / false |
| `ALIPAY_NOTIFY_URL` | 异步通知地址（需公网可访问） | http://localhost:5000/api/notify |
| `FLASK_PORT` | 服务端口，默认 5000 | 5000 |
| `FLASK_ENV` | 运行模式 | development / production |

### 2. 运行服务

```bash
python app_api.py
# 监听 0.0.0.0:5000
```

### 3. 测试支付

浏览器访问：`http://localhost:5000/test`

填写金额和标题后点击"立即支付"，在新标签页渲染扫码页面。

## 接口列表

### 测试页面

```
GET /test
```

浏览器直接访问，填写金额和标题后点击"立即支付"，在新标签页渲染扫码页面。

---

### 扫码支付页面（主流程）

```
GET /paynow?amount=0.01&subject=商品标题&out_trade_no=自定义订单号
```

| 参数 | 必填 | 说明 |
|------|------|------|
| `amount` / `total_amount` | 是 | 金额（元） |
| `subject` | 是 | 商品标题 |
| `out_trade_no` | 否 | 订单号，不传则自动生成 |

服务端创建支付宝预下单并直接渲染二维码支付页面，前端 qrcode.js 将链接绘制为可扫码图片。

**支付页面行为：**
- 每 2 秒轮询一次订单状态
- 支付成功：二维码立即隐藏，显示"支付成功"提示，5 秒后自动关闭标签页
- 订单关闭：显示"订单已关闭"提示
- 5 分钟后二维码自动过期变灰

**前端调用示例：**

```html
<!-- 新标签页打开，不影响当前页面 -->
<button onclick="window.open('/paynow?amount=9.90&subject=商品名称', '_blank')">立即购买</button>
```

---

### 创建支付（JSON 接口，供后端对接）

```
POST /api/pay/create
Content-Type: application/json
```

**请求体：**
```json
{
    "total_amount": 0.01,
    "subject": "商品标题",
    "out_trade_no": "自定义订单号（可选）"
}
```

**返回：**
```json
{
    "code": 0,
    "qr_code": "https://qr.alipay.com/xxx",
    "order_id": "订单号",
    "amount": 0.01,
    "subject": "商品标题"
}
```

**curl 示例：**
```bash
curl -X POST "http://localhost:5000/api/pay/create" \
  -H "Content-Type: application/json" \
  -d '{"total_amount": 0.01, "subject": "测试商品"}'
```

---

### 查询订单状态

```
GET /api/order/query/<order_id>
```

**返回：**
```json
{
    "code": 0,
    "order_id": "订单号",
    "trade_status": "TRADE_SUCCESS",
    "amount": "0.01",
    "data": { ... }
}
```

**交易状态：**

| 状态 | 说明 |
|------|------|
| `WAIT_BUYER_PAY` | 等待付款 |
| `TRADE_SUCCESS` | 支付成功 |
| `TRADE_FINISHED` | 交易完成（不可退款） |
| `TRADE_CLOSED` | 交易关闭 |

---

### 撤销订单

```
POST /api/order/cancel/<order_id>
```

---

### 退款

```
POST /api/refund
Content-Type: application/json
```

**请求体：**
```json
{
    "out_trade_no": "原订单号",
    "refund_amount": 0.01,
    "reason": "退款原因（可选）"
}
```

---

### 异步通知回调

```
POST /api/notify
```

支付宝支付成功后主动 POST 此地址，验签后处理业务逻辑。

- 必须返回字符串 `success`，否则支付宝会在 25 小时内多次重试
- 需要幂等处理（同一笔订单可能多次收到通知）
- 在代码 TODO 处添加业务逻辑（更新订单、发货、发通知等）

**回调关键参数：**

| 参数 | 说明 |
|------|------|
| `out_trade_no` | 商户订单号 |
| `trade_no` | 支付宝交易号 |
| `trade_status` | 交易状态 |
| `total_amount` | 订单金额 |
| `receipt_amount` | 实收金额 |
| `buyer_logon_id` |买家支付宝账号 |
| `gmt_payment` |支付时间 |

验证回调地址是否可访问：
```bash
curl "http://你的域名/api/notify"
# 返回: notify endpoint ok
```

## 项目结构

```
alipay_demo/
├── alipay_config.py      # 配置管理类，从 .env 或环境变量加载
├── alipay_service.py     # AlipayService 服务类，封装支付接口
├── app_api.py            # Flask API 服务，提供 HTTP 接口和页面渲染
├── init.py               # 项目初始化脚本（检查 Python 版本等）
├── requirements.txt      # Python 依赖列表
├── .env.example          # 环境变量配置示例文件
└── templates/
    ├── test_pay.html     # 测试页面（输入金额、标题发起支付）
    └── pay.html          # 二维码展示与轮询页面（含成功/关闭视图）
```

## 技术特性

- **签名方式**：支持 PKCS#8/RSA2，通过 patch SDK 实现，无需手动转换密钥格式
- **类型注解**：完整的类型提示，提升代码可读性和 IDE 支持
- **统一响应解析**：抽取公共函数处理支付宝响应，减少重复代码

## 生产部署建议

1. **HTTPS**：生产环境必须使用 HTTPS，确保通信安全

2. **环境变量**：使用系统环境变量或安全的配置中心管理敏感信息，避免提交到版本控制

3. **订单号**：使用业务系统全局唯一 ID（如 UUID、业务主键），避免重复下单导致资金损失

4. **金额校验**：服务端以数据库商品价格为准，不信任前端传入的金额，防止篡改

5. **回调验签**：已实现完整验签逻辑，排除 sign 和 sign_type 后按参数名升序验签，确保回调来源可信

6. **幂等处理**：异步通知可能重复送达，需在业务系统中实现幂等逻辑（如通过 trade_no 判断）

7. **日志监控**：生产环境建议接入日志收集服务，便于排查问题
5. **幂等处理**：回调可能重复，以订单号为键判断是否已处理
6. **日志**：生产环境将日志级别调整为 `WARNING` 或 `ERROR`
