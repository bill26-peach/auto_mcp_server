import logging
from typing import Dict, List, Optional
from models.config.service_definition import ServiceDefinition
from models.config.service_config import ServiceConfig
from .platform_api_client import PlatformAPIClient

class ServiceRegistry:
    """服务注册中心"""

    def __init__(self):
        self.services: Dict[str, ServiceDefinition] = {}
        self.clients: Dict[str, PlatformAPIClient] = {}
        self.logger = logging.getLogger("service_registry")

    def register_service(
            self,
            service_def: ServiceDefinition,
            config: ServiceConfig
    ):
        """注册服务"""
        if not service_def.enabled:
            self.logger.info(f"Service {service_def.name} is disabled, skipping")
            return

        self.services[service_def.name] = service_def
        self.clients[service_def.name] = PlatformAPIClient(config)
        self.logger.info(f"Registered service: {service_def.name}")

    def get_service(self, name: str) -> Optional[ServiceDefinition]:
        """获取服务定义"""
        return self.services.get(name)

    def get_client(self, name: str) -> Optional[PlatformAPIClient]:
        """获取API客户端"""
        return self.clients.get(name)

    def list_services(self) -> List[str]:
        """列出所有可用服务"""
        return list(self.services.keys())
