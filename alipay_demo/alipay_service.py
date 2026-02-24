# -*- coding: utf-8 -*-
"""
支付宝当面付服务封装 - 扫码支付
配置从 alipay_config 中读取，支持多环境部署
"""

import base64
import json
import logging
from typing import Any, Optional
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256, SHA1
from alipay.aop.api.AlipayClientConfig import AlipayClientConfig
from alipay.aop.api.DefaultAlipayClient import DefaultAlipayClient
from alipay_config import config

# 获取模块已配置的日志记录器
logger = logging.getLogger(__name__)


# =====================================================================
#  辅助函数
# =====================================================================
def parse_response(resp_str: str, response_key: str) -> dict:
    """解析支付宝响应，统一处理 JSON 和异常"""
    resp = json.loads(resp_str) if isinstance(resp_str, str) else resp_str

    if isinstance(resp, dict):
        result = resp.get(response_key, resp)
        code = result.get("code")
        msg = result.get("msg")
        sub_code = result.get("sub_code")
        sub_msg = result.get("sub_msg")

        if code != "10000":
            error_msg = f"{sub_code}: {sub_msg or msg}"
            logger.error(f"请求失败: {error_msg}")
            raise Exception(error_msg)

        return result

    raise Exception(f"意外返回格式: {resp_str}")


def custom_sign(content: str, private_key_raw: str) -> str:
    """
    使用 pycryptodome 自定义 RSA 签名
    
    参数：
        content: 待签名的内容字符串
        private_key_raw: 原始的私钥字符串（无 PEM 标记）
    
    返回：
        base64 编码的签名字符串
    """
    # 移除可能存在的 PEM 标记和换行符
    key_str = (
        private_key_raw
        .replace("-----BEGIN PRIVATE KEY-----", "")
        .replace("-----END PRIVATE KEY-----", "")
        .replace("-----BEGIN RSA PRIVATE KEY-----", "")
        .replace("-----END RSA PRIVATE KEY-----", "")
        .replace("\n", "")
        .replace("\r", "")
    )
    
    try:
        # 尝试作为 base64 解码后的 bytes 导入
        key_bytes = base64.b64decode(key_str)
        key = RSA.import_key(key_bytes)
        logger.debug("✓ 私钥使用 base64 解码方式加载")
    except Exception:
        # 如果失败，直接用字符串导入（带 PEM 标记）
        key = RSA.import_key(private_key_raw)
        logger.debug("✓ 私钥使用 PEM 格式加载")

    # 根据签名类型选择加密算法
    if config.sign_type == "RSA2":
        digest = SHA256.new(content.encode("utf-8"))
    else:
        digest = SHA1.new(content.encode("utf-8"))

    signature = pkcs1_15.new(key).sign(digest)
    return base64.b64encode(signature).decode("utf-8")


def verify_sign(sign_content: str, sign: str, alipay_public_key_raw: str) -> bool:
    """
    验证支付宝返回数据的签名
    
    参数：
        sign_content: 待验签的内容字符串
        sign: 签名字符串（base64 编码）
        alipay_public_key_raw: 支付宝公钥字符串（无 PEM 标记）
    
    返回：
        True 表示签名有效，False 表示签名无效
    """
    # 移除可能存在的 PEM 标记和换行符
    key_str = (
        alipay_public_key_raw
        .replace("-----BEGIN PUBLIC KEY-----", "")
        .replace("-----END PUBLIC KEY-----", "")
        .replace("\n", "")
        .replace("\r", "")
    )
    
    try:
        key_bytes = base64.b64decode(key_str)
        key = RSA.import_key(key_bytes)
    except Exception:
        key = RSA.import_key(alipay_public_key_raw)

    # 根据签名类型选择加密算法
    if config.sign_type == "RSA2":
        digest = SHA256.new(sign_content.encode("utf-8"))
    else:
        digest = SHA1.new(sign_content.encode("utf-8"))

    try:
        pkcs1_15.new(key).verify(digest, base64.b64decode(sign))
        return True
    except Exception as e:
        logger.warning(f"签名验证失败: {e}")
        return False


class AlipayService:
    """
    支付宝支付服务类
    
    功能：
    - 创建扫码支付（当面付）
    - 查询订单状态
    - 撤销订单
    - 处理退款
    """

    def __init__(self):
        """初始化支付宝客户端配置"""
        logger.debug(f"初始化 AlipayService...")
        logger.debug(f"  - AppID: {config.app_id}")
        logger.debug(f"  - 签名方式: {config.sign_type}")
        logger.debug(f"  - 沙箱环境: {config.is_sandbox}")
        logger.debug(f"  - 通知地址: {config.notify_url}")

        # 创建支付宝客户端配置
        self.alipay_client_config = AlipayClientConfig(
            sandbox_debug=config.is_sandbox
        )
        self.alipay_client_config.app_id = config.app_id
        self.alipay_client_config.app_private_key = config.app_private_key
        self.alipay_client_config.alipay_public_key = config.alipay_public_key
        self.alipay_client_config.sign_type = config.sign_type
        self.alipay_client_config.format = config.format
        self.alipay_client_config.charset = config.charset
        self.alipay_client_config.timeout = 30
        self.alipay_client_config.server_url = config.gateway

        logger.debug(f"  - 服务器地址: {self.alipay_client_config.server_url}")

        # 初始化默认支付宝客户端
        self.client = DefaultAlipayClient(self.alipay_client_config)

        # 注入自定义签名到 DefaultAlipayClient 的模块命名空间
        # 注意：SDK 用 `from SignatureUtils import *` 直接导入函数
        # 必须 patch DefaultAlipayClient 模块本身，否则无效！
        self._patch_signature_methods()
        
        logger.info("✓ AlipayService 初始化完成")

    def _patch_signature_methods(self):
        """
        为 DefaultAlipayClient 注入自定义签名方法
        
        SDK 默认使用内置的签名方式，将其替换为 pycryptodome 实现
        以支持 Python 3.11+ 环境
        """
        import alipay.aop.api.DefaultAlipayClient as _dc_module

        def patched_sign_with_rsa2(private_key, sign_content, charset):
            """RSA2 签名方法（签名算法：SHA256）"""
            return custom_sign(sign_content, private_key)

        def patched_sign_with_rsa(private_key, sign_content, charset):
            """RSA 签名方法（签名算法：SHA1）"""
            return custom_sign(sign_content, private_key)

        _dc_module.sign_with_rsa2 = patched_sign_with_rsa2
        _dc_module.sign_with_rsa = patched_sign_with_rsa
        logger.debug("✓ 已注入自定义签名方法")

    # ------------------------------------------------------------------ #
    #  当面付 - 扫码支付（商家展示二维码，用户扫）                           #
    # ------------------------------------------------------------------ #
    def create_qr_payment(self, out_trade_no: str, total_amount: float, subject: str) -> str:
        """
        当面付预下单接口 - alipay.trade.precreate

        创建扫码支付订单，返回二维码链接供商家展示

        参数：
            out_trade_no (str): 商户订单号，需保证唯一性
            total_amount (float): 订单金额（元）
            subject (str): 订单标题/商品描述

        返回：
            str: 支付宝二维码链接 URL

        异常：
            Exception: 支付宝返回错误时抛出
        """
        from alipay.aop.api.request.AlipayTradePrecreateRequest import (
            AlipayTradePrecreateRequest,
        )

        request = AlipayTradePrecreateRequest()
        request.notify_url = config.notify_url
        request.biz_content = {
            "out_trade_no": out_trade_no,
            "total_amount": str(total_amount),
            "subject": subject,
        }

        try:
            resp_str = self.client.execute(request)
            logger.info(f"预下单响应: {resp_str}")

            result = parse_response(resp_str, "alipay_trade_precreate_response")
            qr_code = result.get("qr_code")
            logger.info(f"✓ 创建二维码成功: order_id={out_trade_no}")
            return qr_code

        except Exception as e:
            logger.error(f"❌ 预下单异常: {e}")
            raise

    # ------------------------------------------------------------------ #
    #  查询订单                                                            #
    # ------------------------------------------------------------------ #
    def query_order(self, out_trade_no: str) -> dict:
        """
        查询订单状态 - alipay.trade.query
        
        参数：
            out_trade_no (str): 商户订单号
        
        返回：
            dict: 订单详情，包含支付状态等信息
        
        异常：
            Exception: 查询失败时抛出
        """
        from alipay.aop.api.request.AlipayTradeQueryRequest import (
            AlipayTradeQueryRequest,
        )
        
        request = AlipayTradeQueryRequest()
        request.biz_content = {"out_trade_no": out_trade_no}

        try:
            resp_str = self.client.execute(request)
            result = parse_response(resp_str, "alipay_trade_query_response")
            logger.info(f"✓ 查询订单成功: order_id={out_trade_no}")
            return result

        except Exception as e:
            logger.error(f"❌ 订单查询异常: {e}")
            raise

    # ------------------------------------------------------------------ #
    #  撤销订单                                                            #
    # ------------------------------------------------------------------ #
    def cancel_order(self, out_trade_no: str) -> dict:
        """
        撤销未支付或已支付的订单 - alipay.trade.cancel

        参数：
            out_trade_no (str): 商户订单号

        返回：
            dict: 撤销结果

        异常：
            Exception: 撤销失败时抛出
        """
        from alipay.aop.api.request.AlipayTradeCancelRequest import (
            AlipayTradeCancelRequest,
        )

        request = AlipayTradeCancelRequest()
        request.biz_content = {"out_trade_no": out_trade_no}

        try:
            resp_str = self.client.execute(request)
            result = parse_response(resp_str, "alipay_trade_cancel_response")
            logger.info(f"✓ 撤销订单成功: order_id={out_trade_no}")
            return result

        except Exception as e:
            logger.error(f"❌ 撤销订单异常: {e}")
            raise

    # ------------------------------------------------------------------ #
    #  退款                                                                #
    # ------------------------------------------------------------------ #
    def refund(self, out_trade_no: str, refund_amount: float, refund_reason: str = "") -> dict:
        """
        订单退款 - alipay.trade.refund

        参数：
            out_trade_no (str): 原商户订单号
            refund_amount (float): 退款金额（元），不能大于订单金额
            refund_reason (str): 退款原因说明（可选）

        返回：
            dict: 退款结果

        异常：
            Exception: 退款失败时抛出
        """
        from alipay.aop.api.request.AlipayTradeRefundRequest import (
            AlipayTradeRefundRequest,
        )

        request = AlipayTradeRefundRequest()
        request.biz_content = {
            "out_trade_no": out_trade_no,
            "refund_amount": str(refund_amount),
            "refund_reason": refund_reason,
        }

        try:
            resp_str = self.client.execute(request)
            result = parse_response(resp_str, "alipay_trade_refund_response")
            logger.info(f"✓ 退款成功: order_id={out_trade_no}, amount={refund_amount}")
            return result

        except Exception as e:
            logger.error(f"❌ 退款异常: {e}")
            raise


