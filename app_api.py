# -*- coding: utf-8 -*-
"""
支付宝当面付 API 服务
供其他项目对接调用、本地测试使用

配置从 alipay_config 中读取，支持 .env 环境变量配置
"""

import uuid
import logging
from functools import wraps
from typing import Any, Callable, Optional
from flask import Flask, request, jsonify, render_template, Response
from alipay_service import AlipayService, verify_sign
from alipay_config import config

# 设置日志
logging.basicConfig(
    level=config.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =====================================================================
#  辅助函数
# =====================================================================
def validate_amount(amount: Any, field_name: str = "金额") -> float:
    """校验金额参数"""
    if not amount:
        raise ValueError(f"{field_name}不能为空")
    try:
        amount_float = float(amount)
        if amount_float <= 0:
            raise ValueError(f"{field_name}必须大于0")
        return amount_float
    except (ValueError, TypeError):
        raise ValueError(f"{field_name}格式非法")


def validate_required(value: Any, field_name: str) -> str:
    """校验必需参数"""
    if not value or not (value_str := str(value).strip()):
        raise ValueError(f"{field_name}不能为空")
    return value_str


def error_response(message: str, status: int = 400) -> tuple:
    """返回错误响应"""
    return jsonify({'code': -1, 'message': message}), status


def success_response(data: dict, status: int = 200) -> tuple:
    """返回成功响应"""
    return jsonify({'code': 0, **data}), status

# 创建 Flask 应用
app = Flask(__name__)
app.secret_key = config.flask_secret_key

logger.info("="*60)
logger.info("正在初始化 AlipayService...")
try:
    alipay_service = AlipayService()
    logger.info("✓ AlipayService 初始化成功")
except Exception as e:
    logger.error(f"❌ AlipayService 初始化失败: {e}")
    raise
logger.info("="*60)


# ------------------------------------------------------------------ #
#  直接渲染支付宝扫码页面                                           #
# ------------------------------------------------------------------ #
@app.route('/paynow')
def pay_now() -> Response:
    """
    直接跳转到支付宝扫码页面（浏览器自动重定向）

    URL 参数：
    - total_amount 或 amount: 订单金额（元），必需，必须大于0
    - subject: 商品标题/描述，必需
    - out_trade_no: 商户订单号（可选，不传自动生成）

    使用示例：
    <a href="/paynow?amount=0.01&subject=测试商品">立即购买</a>

    返回：支付成功页面 HTML
    """
    # 获取参数（支持 total_amount 或 amount 两种参数名）
    try:
        amount_float = validate_amount(
            request.args.get('total_amount') or request.args.get('amount'),
            "金额"
        )
        subject = validate_required(request.args.get('subject'), "商品标题")
        out_trade_no = request.args.get('out_trade_no') or None
    except ValueError as e:
        logger.warning(f"❌ 参数校验失败: {e}")
        return error_response(str(e))

    # 生成订单号
    order_id = out_trade_no or str(uuid.uuid4()).replace('-', '')[:20]

    try:
        logger.info(f"创建支付: order_id={order_id}, amount={amount_float}, subject={subject}")
        qr_code = alipay_service.create_qr_payment(
            out_trade_no=order_id,
            total_amount=amount_float,
            subject=subject,
        )

        if not qr_code:
            logger.error("支付宝未返回二维码")
            return "❌ 支付创建失败：未获取到二维码", 400

        # 渲染二维码页面
        return render_template('pay.html',
            order_id=order_id,
            qr_code=qr_code,
            amount=str(amount_float),
            subject=subject
        )

    except Exception as e:
        logger.error(f"❌ 创建支付失败: {e}")
        return f"❌ 支付创建失败：{str(e)}", 500


# ------------------------------------------------------------------ #
#  创建支付二维码（API 接口）                                        #
# ------------------------------------------------------------------ #
@app.route('/api/pay/create', methods=['POST'])
def create_pay() -> tuple:
    """
    创建支付二维码（API 接口）

    请求方式：POST
    Content-Type: application/json

    请求参数：
    {
        "out_trade_no": "订单号（可选，不传自动生成）",
        "total_amount": 0.01,      # 订单金额（元），必需
        "subject": "商品标题"       # 商品描述，必需
    }

    返回示例：
    {
        "code": 0,
        "qr_code": "https://qr.alipay.com/xxx",
        "order_id": "订单号",
        "amount": 0.01,
        "subject": "商品标题"
    }

    错误返回：
    {
        "code": -1,
        "message": "错误信息"
    }
    """
    data = request.get_json() or {}

    # 参数提取和校验
    try:
        amount_float = validate_amount(data.get('total_amount'), "金额")
        subject = validate_required(data.get('subject'), "商品标题")
        out_trade_no = data.get('out_trade_no') or None
    except ValueError as e:
        logger.warning(f"❌ API 参数校验失败: {e}")
        return error_response(str(e))

    # 生成订单号
    order_id = out_trade_no or str(uuid.uuid4()).replace('-', '')[:20]

    try:
        logger.info(f"API 创建支付: order_id={order_id}, amount={amount_float}, subject={subject}")
        qr_code = alipay_service.create_qr_payment(
            out_trade_no=order_id,
            total_amount=amount_float,
            subject=subject,
        )

        logger.info(f"✓ API 创建支付成功: order_id={order_id}")
        host_url = request.host_url.rstrip('/')

        return success_response({
            'qr_code': qr_code,
            'pay_url': f"{host_url}/pay/{order_id}?qr={qr_code}",
            'order_id': order_id,
            'amount': amount_float,
            'subject': subject
        })

    except Exception as e:
        logger.error(f"❌ API 创建支付异常: {e}")
        return error_response(str(e), 500)


# ------------------------------------------------------------------ #
#  测试页面                                                          #
# ------------------------------------------------------------------ #
@app.route('/test')
def test_page():
    """支付测试页面"""
    return render_template('test_pay.html')


# ------------------------------------------------------------------ #
#  查询订单状态                                                         #
# ------------------------------------------------------------------ #
@app.route('/api/order/query/<order_id>', methods=['GET'])
def query_order(order_id):
    """
    查询订单状态
    
    URL 参数：
    - order_id: 商户订单号（必需）
    
    返回示例：
    {
        "code": 0,
        "order_id": "订单号",
        "trade_status": "TRADE_SUCCESS",
        "amount": "0.01",
        "data": { ... 订单详情 ... }
    }
    """
    if not order_id or not order_id.strip():
        logger.warning("❌ 查询订单: 缺少订单号参数")
        return jsonify({'code': -1, 'message': '订单号不能为空'}), 400
    
    try:
        logger.info(f"查询订单: order_id={order_id}")
        result = alipay_service.query_order(order_id)
        
        if not isinstance(result, dict):
            logger.error(f"❌ 查询订单: 返回格式异常")
            return jsonify({'code': -1, 'message': '查询结果格式异常'}), 500
        
        trade_status = result.get('trade_status', '未知')
        total_amount = result.get('total_amount', '')
        
        logger.info(f"✓ 查询订单成功: order_id={order_id}, status={trade_status}")
        
        return jsonify({
            'code': 0,
            'order_id': order_id,
            'trade_status': trade_status,
            'amount': total_amount,
            'data': result
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 查询订单异常: {e}")
        return jsonify({'code': -1, 'message': str(e)}), 500



# ------------------------------------------------------------------ #
#  撤销订单                                                            #
# ------------------------------------------------------------------ #
@app.route('/api/order/cancel/<order_id>', methods=['POST'])
def cancel_order(order_id):
    """
    撤销订单
    
    URL 参数：
    - order_id: 商户订单号（必需）
    
    返回成功示例：
    {
        "code": 0,
        "data": { ... 撤销结果 ... }
    }
    """
    if not order_id or not order_id.strip():
        logger.warning("❌ 撤销订单: 缺少订单号参数")
        return jsonify({'code': -1, 'message': '订单号不能为空'}), 400
    
    try:
        logger.info(f"撤销订单: order_id={order_id}")
        result = alipay_service.cancel_order(order_id)
        
        logger.info(f"✓ 撤销订单成功: order_id={order_id}")
        return jsonify({'code': 0, 'data': result}), 200
        
    except Exception as e:
        logger.error(f"❌ 撤销订单异常: {e}")
        return jsonify({'code': -1, 'message': str(e)}), 500


# ------------------------------------------------------------------ #
#  退款                                                                #
# ------------------------------------------------------------------ #
@app.route('/api/refund', methods=['POST'])
def refund() -> tuple:
    """
    订单退款

    请求方式：POST
    Content-Type: application/json

    请求参数：
    {
        "out_trade_no": "原订单号",      # 必需
        "refund_amount": 0.01,           # 退款金额（元），必需，不能大于订单金额
        "reason": "退款原因"              # 可选
    }

    返回成功示例：
    {
        "code": 0,
        "data": { ... 退款结果 ... },
        "message": "退款成功"
    }
    """
    data = request.get_json() or {}

    # 参数校验
    try:
        order_id = validate_required(data.get('out_trade_no'), "订单号")
        amount_float = validate_amount(data.get('refund_amount'), "退款金额")
        refund_reason = str(data.get('reason', '')).strip()
    except ValueError as e:
        logger.warning(f"❌ 退款参数校验失败: {e}")
        return error_response(str(e))

    try:
        logger.info(f"退款: order_id={order_id}, amount={amount_float}, reason={refund_reason}")
        result = alipay_service.refund(
            out_trade_no=order_id,
            refund_amount=amount_float,
            refund_reason=refund_reason,
        )

        logger.info(f"✓ 退款成功: order_id={order_id}, amount={amount_float}")

        return success_response({'data': result, 'message': '退款成功'})

    except Exception as e:
        logger.error(f"❌ 退款异常: {e}")
        return error_response(str(e), 500)


# ------------------------------------------------------------------ #
#  异步通知（支付宝服务器回调）                                           #
# ------------------------------------------------------------------ #
@app.route('/api/notify', methods=['POST'])
def alipay_notify():
    """
    支付宝异步通知回调
    
    支付宝服务器会在交易成功时向该地址发送 POST 请求
    返回字符串 'success' 表示已收到，否则支付宝会重试通知
    
    """
    params = request.form.to_dict()
    logger.info(f"[NOTIFY] 收到支付宝回调，参数: {params}")

    # 取出 sign，同时排除 sign_type（支付宝验签规则：两者都不参与签名）
    sign = params.pop('sign', None)
    params.pop('sign_type', None)

    if not sign:
        logger.error("[NOTIFY] 回调中没有 sign 字段，验签失败")
        return 'fail'

    # 按参数名升序排列，过滤空值，拼接待验签串
    sign_content = '&'.join(
        f"{k}={v}" for k, v in sorted(params.items()) if v
    )
    logger.debug(f"[NOTIFY] 待验签字符串: {sign_content[:100]}...")

    # 使用配置中的公钥验签
    if not verify_sign(sign_content, sign, config.alipay_public_key):
        logger.error(f"[NOTIFY] ❌ 验签失败! sign={sign[:50]}...")
        return 'fail'

    logger.info("[NOTIFY] ✓ 验签成功")

    # 提取关键信息
    trade_status = params.get('trade_status', '')
    out_trade_no = params.get('out_trade_no', '')
    trade_no = params.get('trade_no', '')
    total_amount = params.get('total_amount', '')

    logger.info(
        f"[NOTIFY] 交易信息: "
        f"status={trade_status}, order_id={out_trade_no}, "
        f"trade_no={trade_no}, amount={total_amount}"
    )

    # 处理不同的交易状态
    if trade_status in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
        logger.info(f"[NOTIFY] ✓ 订单已支付: {out_trade_no}")
        # TODO: 在这里写业务逻辑（更新订单状态、发货等）
        # 例如：
        # - 更新数据库中订单的支付状态
        # - 触发发货流程
        # - 发送确认邮件等
        return 'success'

    elif trade_status == 'TRADE_CLOSED':
        logger.info(f"[NOTIFY] ⚠ 订单已关闭: {out_trade_no}")
        # 订单未支付被关闭，可选处理
        return 'success'

    elif trade_status == 'WAIT_BUYER_PAY':
        logger.info(f"[NOTIFY] ⏳ 订单待支付: {out_trade_no}")
        return 'success'

    logger.warning(f"[NOTIFY] 未处理的交易状态: {trade_status}")
    return 'success'


@app.route('/api/notify', methods=['GET'])
def alipay_notify_check():
    """GET 请求用于验证回调地址是否可访问"""
    return 'notify endpoint ok', 200


if __name__ == '__main__':
    """启动 Flask 应用服务器"""
    logger.info("="*60)
    logger.info(f"🚀 启动 Flask 应用")
    logger.info(f"  - 地址: {config.flask_host}:{config.flask_port}")
    logger.info(f"  - 环境: {config.flask_env}")
    logger.info(f"  - 支付宝沙箱: {config.is_sandbox}")
    logger.info("="*60)
    
    app.run(
        host=config.flask_host,
        port=config.flask_port,
        debug=(config.flask_env == 'development')
    )
