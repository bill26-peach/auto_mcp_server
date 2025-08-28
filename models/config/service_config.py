from dataclasses import dataclass, field

@dataclass
class ServiceConfig:
    """平台服务配置"""
    name: str
    base_url: str
    api_key: str
    version: str = "v1"
    timeout: int = 30
    max_retries: int = 3
    cache_ttl: int = 300  # 缓存5分钟
