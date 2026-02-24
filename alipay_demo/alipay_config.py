# -*- coding: utf-8 -*-
"""
支付宝支付配置管理
从环境变量或 .env 文件读取配置，而不是硬编码敏感信息
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """配置管理类"""

    def __init__(self):
        """初始化配置，从 .env 文件加载环境变量"""
        # 查找 .env 文件位置（当前目录或项目根目录）
        env_path = Path(__file__).parent / '.env'
        
        if env_path.exists():
            logger.info(f"加载配置文件: {env_path}")
            load_dotenv(env_path)
        else:
            logger.warning(f"未找到 .env 配置文件: {env_path}，使用环境变量或默认值")
            load_dotenv()  # 加载系统环境变量

        # 加载支付宝配置
        self._load_alipay_config()
        # 加载集成配置
        self._load_integration_config()

    def _load_alipay_config(self):
        """加载支付宝相关配置"""
        # 必需配置项
        self.app_id = os.getenv('ALIPAY_APP_ID', '').strip()
        self.app_private_key = os.getenv('ALIPAY_APP_PRIVATE_KEY', '').strip()
        self.alipay_public_key = os.getenv('ALIPAY_PUBLIC_KEY', '').strip()

        # 验证必需的配置项
        if not self.app_id:
            raise ValueError("❌ 配置错误: 缺少 ALIPAY_APP_ID，请在 .env 文件中配置")
        if not self.app_private_key:
            raise ValueError("❌ 配置错误: 缺少 ALIPAY_APP_PRIVATE_KEY，请在 .env 文件中配置")
        if not self.alipay_public_key:
            raise ValueError("❌ 配置错误: 缺少 ALIPAY_PUBLIC_KEY，请在 .env 文件中配置")

        # 可选配置项（使用默认值）
        self.sign_type = os.getenv('ALIPAY_SIGN_TYPE', 'RSA2').upper()
        self.format = os.getenv('ALIPAY_FORMAT', 'json').lower()
        self.charset = os.getenv('ALIPAY_CHARSET', 'utf-8').lower()

        # 沙箱环境配置
        sandbox_env = os.getenv('ALIPAY_IS_SANDBOX', 'false').lower()
        self.is_sandbox = sandbox_env in ('true', '1', 'yes', 'on')

        # 回调地址配置
        self.notify_url = os.getenv('ALIPAY_NOTIFY_URL', 'http://localhost:5000/api/notify').strip()
        self.return_url = os.getenv('ALIPAY_RETURN_URL', 'http://localhost:5000/alipay/return').strip()

        # 网关地址（根据是否使用沙箱）
        self.gateway = (
            'https://openapi.alipaydev.com/gateway.do'
            if self.is_sandbox
            else 'https://openapi.alipay.com/gateway.do'
        )

        # 日志输出配置信息
        logger.info(f"✓ 支付宝配置已加载")
        logger.debug(f"  - AppID: {self.app_id}")
        logger.debug(f"  - 签名方式: {self.sign_type}")
        logger.debug(f"  - 沙箱环境: {self.is_sandbox}")
        logger.debug(f"  - 网关: {self.gateway}")

    def _load_integration_config(self):
        """加载集成相关配置"""
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        self.log_level = log_level

        # Flask 配置
        self.flask_secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
        self.flask_env = os.getenv('FLASK_ENV', 'development')
        self.flask_host = os.getenv('FLASK_HOST', '0.0.0.0')
        self.flask_port = int(os.getenv('FLASK_PORT', 5000))

        logger.info(f"✓ 集成配置已加载")
        logger.debug(f"  - 日志级别: {self.log_level}")
        logger.debug(f"  - Flask 环境: {self.flask_env}")


# =====================================================================
# 全局配置实例 - 应用启动时自动初始化
# =====================================================================
try:
    config = Config()
    
    # 为了向后兼容，导出配置项作为模块级变量
    APP_ID = config.app_id
    ALIPAY_PUBLIC_KEY = config.alipay_public_key
    APP_PRIVATE_KEY = config.app_private_key
    SIGN_TYPE = config.sign_type
    FORMAT = config.format
    CHARSET = config.charset
    IS_SANDBOX = config.is_sandbox
    NOTIFY_URL = config.notify_url
    RETURN_URL = config.return_url
    GATEWAY = config.gateway
    
    logger.info("="*60)
    logger.info("🎉 支付宝配置初始化成功！")
    logger.info("="*60)

except ValueError as e:
    logger.error(str(e))
    logger.error("配置初始化失败，应用无法启动")
    raise
except Exception as e:
    logger.error(f"配置加载出错: {e}")
    raise
