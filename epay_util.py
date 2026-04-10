# -*- coding: utf-8 -*-
"""
EPay 协议工具类 - MD5 签名算法
与 New-API 兼容的签名方式

使用方式：
    from epay_util import sign_epay, verify_epay_sign
    
    # 签名
    sign = sign_epay(params, merchant_key)
    
    # 验证
    if verify_epay_sign(params, merchant_key):
        print("签名有效")
"""

import hashlib
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def sign_epay(params: Dict[str, str], merchant_key: str) -> str:
    """
    生成 EPay MD5 签名（与 New-API 兼容）
    
    算法：
    1. 过滤 sign、sign_type 和空值参数
    2. 按 key 字母升序排序
    3. 拼接为 key1=value1&key2=value2&...&keyN=valueN
    4. 末尾直接追加商户密钥（无 & 分隔符）
    5. 计算 MD5 哈希 → 小写十六进制
    
    参数：
        params: 要签名的参数字典
        merchant_key: 商户密钥（与 New-API 一致）
    
    返回：
        签名字符串（小写十六进制）
    
    示例：
        params = {
            'pid': '1673765678',
            'out_trade_no': 'order_123',
            'type': 'alipay',
            'money': '100.00',
            'name': '充值100元',
        }
        sign = sign_epay(params, 'xm3787562987')
        # → '5d41402abc4b2a76b9719d911017c592'
    """
    # 过滤：排除 sign、sign_type 和空值
    filtered_params = {
        k: str(v) for k, v in params.items()
        if k not in ('sign', 'sign_type') and v is not None and str(v).strip()
    }
    
    # 按 key 字母升序排序
    sorted_params = dict(sorted(filtered_params.items()))
    
    # 拼接字符串：key1=value1&key2=value2&...&keyN=valueN
    sign_parts = [f"{k}={v}" for k, v in sorted_params.items()]
    sign_string = '&'.join(sign_parts)
    
    # 末尾直接追加商户密钥（无 & 分隔符）
    sign_string += merchant_key
    
    logger.debug(f"EPay 签名字符串: {sign_string[:100]}...")
    
    # 计算 MD5
    md5_hash = hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()
    
    logger.debug(f"生成的签名: {md5_hash}")
    return md5_hash


def verify_epay_sign(params: Dict[str, str], merchant_key: str) -> bool:
    """
    验证 EPay MD5 签名
    
    参数：
        params: 包含 sign 字段的参数字典
        merchant_key: 商户密钥
    
    返回：
        True 表示签名有效，False 表示签名无效
    
    示例：
        params = {
            'pid': '1673765678',
            'out_trade_no': 'order_123',
            'type': 'alipay',
            'money': '100.00',
            'sign': '5d41402abc4b2a76b9719d911017c592',
        }
        if verify_epay_sign(params, 'xm3787562987'):
            print("签名验证成功")
    """
    # 提取签名
    sign_to_verify = params.get('sign', '')
    if not sign_to_verify:
        logger.warning("签名验证失败：缺少 sign 字段")
        return False
    
    # 计算签名
    calculated_sign = sign_epay(params, merchant_key)
    
    # 比较签名（不区分大小写）
    valid = sign_to_verify.lower() == calculated_sign.lower()
    
    if valid:
        logger.info("✓ EPay 签名验证成功")
    else:
        logger.warning(f"❌ EPay 签名验证失败")
        logger.debug(f"   期望: {calculated_sign}")
        logger.debug(f"   实际: {sign_to_verify}")
    
    return valid


def build_epay_notify_params(
    order_id: str,
    trade_no: str,
    money: str,
    pid: int,
    type_: str = 'alipay',
    status: int = 1
) -> Dict[str, str]:
    """
    构建 EPay 回调参数（用于回调 New-API）
    
    参数：
        order_id: 商户订单号（out_trade_no）
        trade_no: 平台交易号
        money: 支付金额（元）
        pid: 商户 ID
        type_: 支付类型（alipay/wxpay）
        status: 支付状态（1=已支付）
    
    返回：
        待签名的参数字典
    
    示例：
        params = build_epay_notify_params(
            order_id='order_123',
            trade_no='2024041000001234',
            money='100.00',
            pid=1673765678,
            type_='alipay'
        )
        sign = sign_epay(params, merchant_key)
        params['sign'] = sign
        params['sign_type'] = 'MD5'
        # 现在可以 POST 发送给 New-API
    """
    params = {
        'trade_no': str(trade_no),
        'out_trade_no': str(order_id),
        'money': str(money),
        'pid': str(pid),
        'type': str(type_),
        'status': str(status),
    }
    return params
