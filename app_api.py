# -*- coding: utf-8 -*-
"""
支付宝当面付 API 服务 + New-API EPay 协议支持【改造版】
供其他项目对接调用、本地测试使用

【新增功能】
- /submit.php - EPay 协议下单接口（New-API 调用）
- /api/check-status - 订单状态查询接口
- 支付成功后回调 New-API 的 notify_url
- 订单数据持久化到数据库
"""

import os
import uuid
import logging
import requests
import threading
from typing import Any, Optional, Dict, Tuple
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, render_template, Response
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from alipay_service import AlipayService, verify_sign
from alipay_config import config
from epay_util import sign_epay, verify_epay_sign, build_epay_notify_params

# 设置日志
logging.basicConfig(
    level=config.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =====================================================================
# 数据库配置【新增】
# =====================================================================

engine = create_engine(
    config.db_url,
    echo=False,
    pool_pre_ping=True,  # SQLite 连接检测
    connect_args={'check_same_thread': False} if 'sqlite' in config.db_url else {}
)

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class PayOrder(Base):
    """支付订单模型【新增】"""
    __tablename__ = 'pay_order'
    
    id = Column(Integer, primary_key=True, index=True)
    
    # EPay 订单字段
    out_trade_no = Column(String(64), unique=True, nullable=False, index=True)  # 商户订单号
    trade_no = Column(String(64), nullable=True)  # 平台交易号
    
    # 商户信息
    pid = Column(Integer, nullable=True)  # 商户 ID
    type = Column(String(16), nullable=True)  # 支付类型 (alipay/wxpay)
    
    # 订单信息
    name = Column(String(128), nullable=True)  # 商品名称
    money = Column(Float, nullable=True)  # 金额（元）
    
    # 回调信息
    notify_url = Column(String(512), nullable=True)  # 回调地址
    return_url = Column(String(512), nullable=True)  # 返回地址
    
    # 状态
    status = Column(Integer, default=0)  # 0=待支付, 1=已支付, 2=已通知
    
    # 第三方信息
    alipay_trade_no = Column(String(64), nullable=True)  # 支付宝交易号
    qr_code = Column(Text, nullable=True)  # 二维码 URL
    
    # 通知重试
    notify_count = Column(Integer, default=0)  # 已通知次数
    
    # 账号发放状态（防重放）
    account_dispensed = Column(Integer, default=0)  # 0=未发放, 1=已发放
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow())
    updated_at = Column(DateTime, default=datetime.utcnow(), onupdate=datetime.utcnow())


# 创建表
Base.metadata.create_all(bind=engine)


# =====================================================================
# 商品价目表（后端硬编码，防止前端篡改金额）
# =====================================================================

PRODUCTS = {
    'account': {'name': '账号购买', 'price': 5.0},
}
DEFAULT_PRODUCT = 'account'


def require_admin_key(f):
    """管理员 API Key 认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not config.admin_api_key:
            return error_response("管理接口未配置 ADMIN_API_KEY，拒绝访问", 403)
        # 支持 Authorization: Bearer <key> 或 ?api_key=<key>
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            provided_key = auth_header[7:].strip()
        else:
            provided_key = (request.values.get('api_key') or '').strip()
        if not provided_key or provided_key != config.admin_api_key:
            logger.warning(f"[AUTH] 管理接口鉴权失败, path={request.path}")
            return error_response("API Key 无效", 403)
        return f(*args, **kwargs)
    return decorated


# =====================================================================
# 辅助函数
# =====================================================================

def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


def error_response(message: str, status: int = 400) -> Tuple:
    """返回错误响应"""
    return jsonify({'code': -1, 'message': message}), status


def success_response(data: dict, status: int = 200) -> Tuple:
    """返回成功响应"""
    return jsonify({'code': 0, **data}), status


def notify_new_api_async(order: PayOrder):
    """异步通知 New-API（在后台线程执行）【新增】"""
    def do_notify():
        try:
            # 构建回调参数（包含 name 和 trade_status，确保与 epay-proxy 兼容）
            notify_params = build_epay_notify_params(
                order_id=order.out_trade_no,
                trade_no=order.trade_no or "",
                money=str(order.money),
                pid=order.pid or config.epay_merchant_id,
                type_=order.type or 'alipay',
                status=1,  # 已支付
                name=order.name or "",  # 商品名称
                trade_status='TRADE_SUCCESS'  # 交易成功
            )
            
            # 签名
            sign = sign_epay(notify_params, config.epay_merchant_key)
            notify_params['sign'] = sign
            notify_params['sign_type'] = 'MD5'
            
            logger.info(f"回调 New-API: {order.notify_url}, params: {notify_params}")
            
            # 发送回调
            response = requests.post(
                order.notify_url,
                data=notify_params,
                timeout=10
            )
            
            # 检查响应
            if response.status_code == 200 and response.text.strip().lower() == 'success':
                logger.info(f"✓ 回调成功: {order.out_trade_no}")
                
                # 更新订单状态
                db = SessionLocal()
                try:
                    db_order = db.query(PayOrder).filter(
                        PayOrder.out_trade_no == order.out_trade_no
                    ).first()
                    if db_order:
                        db_order.status = 2  # 标记为已通知
                        db_order.notify_count += 1
                        db.commit()
                except Exception as e:
                    logger.error(f"更新订单状态失败: {e}")
                finally:
                    db.close()
            else:
                logger.warning(
                    f"❌ 回调失败: {order.out_trade_no}, "
                    f"status={response.status_code}, body={response.text[:100]}"
                )
                
                # 增加重试计数
                db = SessionLocal()
                try:
                    db_order = db.query(PayOrder).filter(
                        PayOrder.out_trade_no == order.out_trade_no
                    ).first()
                    if db_order:
                        db_order.notify_count += 1
                        db.commit()
                except Exception as e:
                    logger.error(f"更新重试计数失败: {e}")
                finally:
                    db.close()
        
        except requests.RequestException as e:
            logger.error(f"❌ 回调异常 ({order.out_trade_no}): {e}")
        except Exception as e:
            logger.error(f"❌ 回调异常 ({order.out_trade_no}): {e}")
    
    # 在后台线程执行
    thread = threading.Thread(target=do_notify, daemon=True)
    thread.start()


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


# =====================================================================
# 【新增】EPay 协议接口 - /submit.php
# =====================================================================

@app.route('/submit.php', methods=['GET', 'POST'])
def submit_order():
    """
    EPay 兼容的下单接口 - New-API 调用此接口进行支付
    
    URL 参数（GET）或表单参数（POST）：
    - pid: 商户 ID（必需）
    - out_trade_no: 商户订单号（必需）
    - type: 支付类型（必需）- alipay/wxpay
    - money: 金额（元）（必需）
    - name: 商品名称（必需）
    - notify_url: 支付成功回调地址（必需）
    - return_url: 支付成功返回地址（可选）
    - sign: MD5 签名（必需）
    - sign_type: 签名类型（必需） - MD5
    
    返回：
    - 支付宝：直接返回支付宝收银台 HTML（自动跳转）
    - 微信：返回二维码展示页面
    """
    # 获取参数
    if request.method == 'GET':
        params = request.args.to_dict()
    else:
        params = request.form.to_dict()
    
    logger.info(f"[EPay] 收到 /submit.php 请求, params: {params}")
    
    try:
        # 1. 验证签名
        if not verify_epay_sign(params, config.epay_merchant_key):
            logger.warning(f"[EPay] ❌ 签名验证失败")
            return "签名验证失败", 400
        
        # 2. 验证商户 ID
        pid = int(params.get('pid', 0))
        if pid != int(config.epay_merchant_id):
            logger.warning(f"[EPay] ❌ 商户 ID 不匹配: {pid} != {config.epay_merchant_id}")
            return "商户ID不匹配", 400
        
        # 3. 提取参数
        out_trade_no = validate_required(params.get('out_trade_no'), "订单号")
        pay_type = validate_required(params.get('type'), "支付类型")
        money = validate_amount(params.get('money'), "金额")
        name = validate_required(params.get('name'), "商品名称")
        notify_url = validate_required(params.get('notify_url'), "回调地址")
        return_url = params.get('return_url', '')
        
        # 4. 检查订单是否已存在（幂等性）
        db = next(get_db())
        existing_order = db.query(PayOrder).filter(
            PayOrder.out_trade_no == out_trade_no
        ).first()
        
        if existing_order:
            logger.info(f"[EPay] 订单已存在, 直接返回: {out_trade_no}")
            # 返回已有的支付信息
            if existing_order.qr_code:
                return render_template('pay.html',
                    order_id=out_trade_no,
                    qr_code=existing_order.qr_code,
                    amount=str(existing_order.money),
                    subject=existing_order.name
                )
        
        # 5. 调用支付宝创建支付
        logger.info(f"[EPay] 创建支付: order={out_trade_no}, type={pay_type}, amount={money}")
        
        if pay_type not in ('alipay', 'wxpay'):
            raise ValueError(f"不支持的支付类型: {pay_type}")
        
        # 目前仅支持支付宝
        if pay_type != 'alipay':
            raise ValueError("暂仅支持支付宝支付")
        
        # 生成平台交易号
        trade_no = f"EP{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8]}"
        
        # 调用支付宝 API
        qr_code = alipay_service.create_qr_payment(
            out_trade_no=out_trade_no,
            total_amount=money,
            subject=name
        )
        
        # 6. 保存订单到数据库
        order = PayOrder(
            out_trade_no=out_trade_no,
            trade_no=trade_no,
            pid=pid,
            type=pay_type,
            name=name,
            money=money,
            notify_url=notify_url,
            return_url=return_url or "",
            qr_code=qr_code,
            status=0  # 待支付
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        
        logger.info(f"[EPay] ✓ 订单已创建: {out_trade_no}")
        
        # 7. 返回支付页面
        return render_template('pay.html',
            order_id=out_trade_no,
            qr_code=qr_code,
            amount=str(money),
            subject=name
        )
    
    except ValueError as e:
        logger.error(f"[EPay] ❌ 参数错误: {e}")
        return f"参数错误: {str(e)}", 400
    except Exception as e:
        logger.error(f"[EPay] ❌ 创建支付失败: {e}", exc_info=True)
        return f"创建支付失败: {str(e)}", 500
    finally:
        try:
            db.close()
        except:
            pass


@app.route('/api/check-status', methods=['GET'])
def check_status():
    """
    查询订单状态（前端轮询使用）【新增】
    
    参数：
    - out_trade_no: 商户订单号（必需）
    
    返回：
    {
        "status": 0/1/2,  // 0=失败, 1=成功, 2=已通知
        "message": "状态说明"
    }
    """
    out_trade_no = request.args.get('out_trade_no', '')
    
    if not out_trade_no:
        return error_response("订单号不能为空")
    
    try:
        db = next(get_db())
        order = db.query(PayOrder).filter(
            PayOrder.out_trade_no == out_trade_no
        ).first()
        
        if not order:
            return error_response("订单不存在", 404)
        
        # 查询支付宝订单状态
        result = alipay_service.query_order(out_trade_no)
        trade_status = result.get('trade_status', '')
        
        if trade_status in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
            # 支付成功，更新本地订单
            if order.status == 0:
                order.status = 1  # 标记为已支付
                order.alipay_trade_no = result.get('trade_no', '')
                db.commit()
                
                # 异步回调 New-API
                notify_new_api_async(order)
            
            return success_response({
                'status': 1,
                'message': '支付成功'
            })
        elif trade_status == 'TRADE_CLOSED':
            return success_response({
                'status': 0,
                'message': '订单已关闭'
            })
        else:
            return success_response({
                'status': 0,
                'message': '等待支付'
            })
    
    except Exception as e:
        logger.error(f"查询订单状态失败: {e}")
        return error_response(str(e), 500)
    finally:
        try:
            db.close()
        except:
            pass


# =====================================================================
# 【统一入口】直接购买页面（内部走 /submit.php 同样的数据库入库逻辑）
# =====================================================================

@app.route('/paynow')
def pay_now() -> Response:
    """
    直接购买接口 - 金额由后端 PRODUCTS 价目表决定，订单统一入库。

    URL 参数：
    - product: 商品 ID（可选，默认 account）
    - out_trade_no: 商户订单号（可选，不传自动生成）

    返回：支付二维码页面 HTML
    """
    product_id = request.args.get('product', DEFAULT_PRODUCT)
    product = PRODUCTS.get(product_id)
    if not product:
        return error_response(f"商品不存在: {product_id}", 400)

    amount_float = product['price']
    subject = product['name']
    out_trade_no = request.args.get('out_trade_no') or str(uuid.uuid4()).replace('-', '')[:20]

    db = None
    try:
        db = next(get_db())

        # 幂等：订单已存在则直接返回
        existing = db.query(PayOrder).filter(PayOrder.out_trade_no == out_trade_no).first()
        if existing and existing.qr_code:
            return render_template('pay.html',
                order_id=out_trade_no,
                qr_code=existing.qr_code,
                amount=str(existing.money),
                subject=existing.name
            )

        # 创建支付宝预下单
        logger.info(f"[paynow] 创建支付: order={out_trade_no}, product={product_id}, amount={amount_float}")
        trade_no = f"PN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8]}"
        qr_code = alipay_service.create_qr_payment(
            out_trade_no=out_trade_no,
            total_amount=amount_float,
            subject=subject,
        )
        if not qr_code:
            return "支付创建失败：未获取到二维码", 400

        # 订单入库（与 /submit.php 一致）
        order = PayOrder(
            out_trade_no=out_trade_no,
            trade_no=trade_no,
            pid=int(config.epay_merchant_id),
            type='alipay',
            name=subject,
            money=amount_float,
            notify_url='',
            return_url='',
            qr_code=qr_code,
            status=0
        )
        db.add(order)
        db.commit()
        logger.info(f"[paynow] ✓ 订单已入库: {out_trade_no}")

        return render_template('pay.html',
            order_id=out_trade_no,
            qr_code=qr_code,
            amount=str(amount_float),
            subject=subject
        )

    except Exception as e:
        logger.error(f"[paynow] ❌ 创建支付失败: {e}")
        return f"支付创建失败：{str(e)}", 500
    finally:
        if db:
            try:
                db.close()
            except:
                pass


@app.route('/test')
def test_page():
    """支付测试页面"""
    return render_template('test_pay.html')


# 账号文件路径（每行一条 "账号|密码"），位于项目根目录
ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts.txt')
_accounts_lock = threading.Lock()


@app.route('/api/account-stock', methods=['GET'])
def account_stock():
    """查询 accounts.txt 剩余可用账号数量"""
    try:
        if not os.path.exists(ACCOUNTS_FILE):
            return success_response({'stock': 0})
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            count = sum(1 for line in f if line.strip() and '|' in line)
        return success_response({'stock': count})
    except Exception as e:
        logger.error(f"[ACCOUNT] 查询库存失败: {e}")
        return error_response(str(e), 500)


@app.route('/api/get-account', methods=['GET', 'POST'])
def get_account():
    """
    读取 accounts.txt 第一行 "账号|密码"，并从文件中移除（消费式）。

    参数：
    - out_trade_no: 订单号（必需，必须是已支付状态，防止未支付套取账号）

    返回：
    {"code": 0, "account": "xxx", "password": "yyy"}
    """
    out_trade_no = (request.values.get('out_trade_no') or '').strip()
    if not out_trade_no:
        return error_response("订单号不能为空")

    # 校验订单支付状态 + 金额
    min_price = PRODUCTS[DEFAULT_PRODUCT]['price']
    db = SessionLocal()
    try:
        order = db.query(PayOrder).filter(PayOrder.out_trade_no == out_trade_no).first()

        # 【安全修复】订单必须在数据库中存在（仅通过 /submit.php 创建的订单才有效）
        if not order:
            logger.warning(f"[ACCOUNT] 订单不在数据库中, 拒绝: {out_trade_no}")
            return error_response("订单不存在（仅支持通过正规渠道创建的订单）", 403)

        # 【安全修复】防重放：同一订单只能发放一次账号
        if order.account_dispensed == 1:
            logger.warning(f"[ACCOUNT] 订单已发放过账号, 拒绝重复发放: {out_trade_no}")
            return error_response("该订单已领取过账号，不可重复领取", 403)

        # 【安全修复】强制校验金额（不再短路跳过）
        if order.money is None or order.money < min_price:
            logger.warning(f"[ACCOUNT] 金额不足: order={out_trade_no}, money={order.money}, min={min_price}")
            return error_response(f"支付金额不足（需 {min_price} 元）", 403)

        # 校验支付状态
        paid = False
        if order.status in (1, 2):
            paid = True
        else:
            # 兜底：查询支付宝确认支付状态
            try:
                result = alipay_service.query_order(out_trade_no)
                if (result.get('trade_status') or '') in ('TRADE_SUCCESS', 'TRADE_FINISHED'):
                    # 同步更新本地状态
                    order.status = 1
                    order.alipay_trade_no = result.get('trade_no', '')
                    db.commit()
                    paid = True
            except Exception:
                paid = False

        if not paid:
            return error_response("订单未支付，无法获取账号", 403)
    finally:
        db.close()

    # 读取并消费第一行
    with _accounts_lock:
        if not os.path.exists(ACCOUNTS_FILE):
            return error_response(f"账号文件不存在: {ACCOUNTS_FILE}", 500)
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 找到第一条非空行
            first_idx = -1
            first_line = ''
            for i, line in enumerate(lines):
                if line.strip():
                    first_idx = i
                    first_line = line.strip()
                    break

            if first_idx < 0:
                return error_response("账号库已空，请补充 accounts.txt", 500)

            # 解析 账号|密码
            if '|' not in first_line:
                return error_response(f"账号行格式错误（应为 账号|密码）: {first_line}", 500)
            account, password = first_line.split('|', 1)

            # 移除该行
            remaining = lines[:first_idx] + lines[first_idx + 1:]
            with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                f.writelines(remaining)

            # 【安全修复】标记订单为已发放，防止重复领取
            db2 = SessionLocal()
            try:
                db_order = db2.query(PayOrder).filter(
                    PayOrder.out_trade_no == out_trade_no
                ).first()
                if db_order:
                    db_order.account_dispensed = 1
                    db2.commit()
            except Exception as e:
                logger.error(f"[ACCOUNT] 标记已发放失败: {e}")
            finally:
                db2.close()

            logger.info(f"[ACCOUNT] 发放账号 order={out_trade_no}, account={account}")
            return success_response({
                'account': account.strip(),
                'password': password.strip(),
            })
        except Exception as e:
            logger.error(f"[ACCOUNT] 读取账号失败: {e}", exc_info=True)
            return error_response(f"读取账号失败: {str(e)}", 500)


@app.route('/api/order/query/<order_id>', methods=['GET'])
def query_order(order_id):
    """查询订单状态"""
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


@app.route('/api/order/cancel/<order_id>', methods=['POST'])
@require_admin_key
def cancel_order(order_id):
    """撤销订单"""
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


@app.route('/api/refund', methods=['POST'])
@require_admin_key
def refund() -> Tuple:
    """订单退款"""
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


@app.route('/api/notify', methods=['POST'])
def alipay_notify():
    """支付宝异步通知回调"""
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
        
        # 更新订单状态
        try:
            db = next(get_db())
            order = db.query(PayOrder).filter(
                PayOrder.out_trade_no == out_trade_no
            ).first()
            
            if order:
                # 【安全修复】校验回调金额与订单金额是否一致
                if total_amount and order.money is not None:
                    try:
                        callback_amount = float(total_amount)
                        if abs(callback_amount - order.money) > 0.01:
                            logger.error(
                                f"[NOTIFY] ❌ 金额不一致! 订单={order.money}, 回调={callback_amount}, "
                                f"order={out_trade_no}"
                            )
                            db.close()
                            return 'fail'
                    except (ValueError, TypeError):
                        logger.error(f"[NOTIFY] ❌ 回调金额格式异常: {total_amount}")
                        db.close()
                        return 'fail'

                if order.status == 0:  # 还未支付
                    order.status = 1  # 标记为已支付
                    order.alipay_trade_no = trade_no
                    db.commit()
                    
                    # 异步回调 New-API
                    notify_new_api_async(order)
                else:
                    logger.info(f"订单已处理，跳过: {out_trade_no}")
            
            db.close()
        except Exception as e:
            logger.error(f"处理支付宝通知异常: {e}", exc_info=True)
        
        return 'success'

    elif trade_status == 'TRADE_CLOSED':
        logger.info(f"[NOTIFY] ⚠ 订单已关闭: {out_trade_no}")
        return 'success'

    elif trade_status == 'WAIT_BUYER_PAY':
        logger.info(f"[NOTIFY] ⏳ 订单待支付: {out_trade_no}")
        return 'success'

    else:
        logger.warning(f"[NOTIFY] 未处理的交易状态: {trade_status}")
        return 'success'


@app.route('/api/notify', methods=['GET'])
def alipay_notify_check():
    """GET 请求用于验证回调地址是否可访问"""
    return 'notify endpoint ok', 200


if __name__ == '__main__':
    """启动 Flask 应用服务器"""
    logger.info("="*60)
    logger.info(f"🚀 启动 Flask 应用【改造版 - 支持 New-API】")
    logger.info(f"  - 地址: {config.flask_host}:{config.flask_port}")
    logger.info(f"  - 环境: {config.flask_env}")
    logger.info(f"  - 支付宝沙箱: {config.is_sandbox}")
    logger.info(f"  - EPay 商户ID: {config.epay_merchant_id}")
    logger.info(f"  - 数据库: {config.db_url}")
    logger.info("="*60)
    
    app.run(
        host=config.flask_host,
        port=config.flask_port,
        debug=(config.flask_env == 'development'),
        threaded=True
    )
