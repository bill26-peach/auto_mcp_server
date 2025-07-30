"""
Platform A MCP Integration Server - 修复版本
完整的平台服务接入架构设计

修复了异步调用问题，确保MCP工具能正确执行
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Union, Callable
from urllib.parse import urljoin
import aiohttp
import time
from functools import wraps
from makefun import create_function
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

# =============================================================================
# 配置和数据模型
# =============================================================================

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


@dataclass
class APIEndpoint:
    """API端点定义"""
    path: str
    method: str = "GET"
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    response_format: str = "json"
    requires_auth: bool = True
    rate_limit: Optional[int] = None  # 每分钟请求限制


@dataclass
class ServiceDefinition:
    """服务定义"""
    name: str
    category: str
    endpoints: Dict[str, APIEndpoint]
    description: str = ""
    enabled: bool = True


# =============================================================================
# 核心抽象层
# =============================================================================

class PlatformAPIClient:
    """平台A的API客户端"""

    def __init__(self, config: ServiceConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(f"api_client.{config.name}")
        self._cache: Dict[str, Any] = {}
        self._rate_limits: Dict[str, List[float]] = {}

    async def __aenter__(self):
        """异步上下文管理器入口"""
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "User-Agent": "MCP-Platform-Integration/1.0"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()

    def _get_cache_key(self, endpoint: str, params: Dict) -> str:
        """生成缓存键"""
        param_str = json.dumps(params, sort_keys=True)
        return f"{endpoint}:{hash(param_str)}"

    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """检查缓存是否有效"""
        return time.time() - cache_entry["timestamp"] < self.config.cache_ttl

    def _check_rate_limit(self, endpoint: str, rate_limit: Optional[int]) -> bool:
        """检查速率限制"""
        if not rate_limit:
            return True

        now = time.time()
        if endpoint not in self._rate_limits:
            self._rate_limits[endpoint] = []

        # 清理超过1分钟的记录
        self._rate_limits[endpoint] = [
            t for t in self._rate_limits[endpoint]
            if now - t < 60
        ]

        return len(self._rate_limits[endpoint]) < rate_limit

    async def call_api(
        self,
        endpoint: APIEndpoint,
        params: Optional[Dict] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """调用API端点"""
        params = params or {}

        # 检查缓存
        cache_key = self._get_cache_key(endpoint.path, params)
        if use_cache and cache_key in self._cache:
            cached_entry = self._cache[cache_key]
            if self._is_cache_valid(cached_entry):
                self.logger.debug(f"Cache hit for {endpoint.path}")
                return cached_entry["data"]

        # 检查速率限制
        if not self._check_rate_limit(endpoint.path, endpoint.rate_limit):
            raise Exception(f"Rate limit exceeded for {endpoint.path}")

        # 构建请求URL
        url = urljoin(self.config.base_url, f"{self.config.version}/{endpoint.path}")

        # 执行请求（带重试）
        for attempt in range(self.config.max_retries):
            try:
                if endpoint.method.upper() == "GET":
                    async with self.session.get(url, params=params) as response:
                        result = await self._handle_response(response, endpoint)
                        break
                elif endpoint.method.upper() == "POST":
                    async with self.session.post(url, json=params) as response:
                        result = await self._handle_response(response, endpoint)
                        break
                else:
                    raise ValueError(f"Unsupported method: {endpoint.method}")

            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # 指数退避

        # 记录速率限制
        if endpoint.rate_limit:
            self._rate_limits[endpoint.path].append(time.time())

        # 缓存结果
        if use_cache:
            self._cache[cache_key] = {
                "data": result,
                "timestamp": time.time()
            }

        return result

    async def _handle_response(
        self,
        response: aiohttp.ClientResponse,
        endpoint: APIEndpoint
    ) -> Dict[str, Any]:
        """处理API响应"""
        if response.status >= 400:
            error_text = await response.text()
            raise Exception(f"API Error {response.status}: {error_text}")

        if endpoint.response_format == "json":
            return await response.json()
        else:
            text = await response.text()
            return {"content": text}


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


# =============================================================================
# MCP服务器实现
# =============================================================================

class PlatformMCPServer:
    """平台集成MCP服务器"""

    def __init__(self, name: str = "platform-integration"):
        self.mcp = FastMCP(name)
        self.registry = ServiceRegistry()
        self.logger = logging.getLogger("mcp_server")
        self._setup_base_resources()

    def _setup_base_resources(self):
        """设置基础资源"""

        @self.mcp.resource("platform://services")
        def list_services() -> str:
            """列出所有可用的平台服务"""
            services = []
            for name, service_def in self.registry.services.items():
                services.append(f"## {service_def.name}")
                services.append(f"**类别**: {service_def.category}")
                services.append(f"**描述**: {service_def.description}")
                services.append(f"**端点数量**: {len(service_def.endpoints)}")
                services.append("")

            return "\n".join(services) if services else "没有可用的服务"

        @self.mcp.resource("platform://service/{service_name}")
        def get_service_info(service_name: str) -> str:
            """获取特定服务的详细信息"""
            service_def = self.registry.get_service(service_name)
            if not service_def:
                return f"服务 '{service_name}' 不存在"

            info = [
                f"# {service_def.name} 服务信息",
                f"**类别**: {service_def.category}",
                f"**描述**: {service_def.description}",
                "",
                "## 可用端点:"
            ]

            for endpoint_name, endpoint in service_def.endpoints.items():
                info.extend([
                    f"### {endpoint_name}",
                    f"- **路径**: {endpoint.path}",
                    f"- **方法**: {endpoint.method}",
                    f"- **描述**: {endpoint.description}",
                    f"- **参数**: {list(endpoint.parameters.keys())}",
                    ""
                ])

            return "\n".join(info)

    def register_service_from_config(self, config_path: str):
        """从配置文件注册服务"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 解析服务配置
            service_config = ServiceConfig(**config_data['service_config'])

            # 解析服务定义
            service_def_data = config_data['service_definition']
            endpoints = {}

            for ep_name, ep_data in service_def_data['endpoints'].items():
                endpoints[ep_name] = APIEndpoint(**ep_data)

            service_def = ServiceDefinition(
                name=service_def_data['name'],
                category=service_def_data['category'],
                endpoints=endpoints,
                description=service_def_data.get('description', ''),
                enabled=service_def_data.get('enabled', True)
            )

            # 注册服务
            self.registry.register_service(service_def, service_config)

            # 动态创建MCP工具
            self._create_service_tools(service_def)

        except Exception as e:
            self.logger.error(f"Failed to register service from {config_path}: {e}")
            raise

    def _create_service_tools(self, service_def: ServiceDefinition):
        """为服务创建MCP工具 - 修复版本"""

        def map_openapi_type_to_python(openapi_type: str):
            return {
                'string': str,
                'integer': int,
                'number': float,
                'boolean': bool,
                'array': list,
                'object': dict
            }.get(openapi_type, str)

        for endpoint_name, endpoint in service_def.endpoints.items():
            tool_name = f"{service_def.name}_{endpoint_name}"

            def create_tool_func(ep_name=endpoint_name, service_name=service_def.name, ep_obj=endpoint):
                param_defs = ep_obj.parameters

                sig_parts = []
                annotations = {}

                for param_name, param_info in param_defs.items():
                    openapi_type = param_info.get("type", "string")
                    py_type = map_openapi_type_to_python(openapi_type)
                    annotations[param_name] = py_type

                    is_required = param_info.get("required", False)
                    has_default = "default" in param_info

                    if not is_required and has_default:
                        default = param_info["default"]
                        sig_parts.append(f"{param_name}: {py_type.__name__} = {repr(default)}")
                    elif not is_required:
                        sig_parts.append(f"{param_name}: {py_type.__name__} = None")
                    else:
                        sig_parts.append(f"{param_name}: {py_type.__name__}")

                sig_str = ", ".join(sig_parts)
                full_signature = f"{tool_name}({sig_str}) -> str"

                # 修复：使用同步函数包装异步调用
                def handler_func(**kwargs):
                    # 获取事件循环
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    # 定义异步执行函数
                    async def execute_api_call():
                        client = self.registry.get_client(service_name)
                        service = self.registry.get_service(service_name)
                        if not client or not service:
                            return f"服务 {service_name} 不可用"

                        endpoint_obj = service.endpoints[ep_name]
                        try:
                            async with client:
                                result = await client.call_api(endpoint_obj, kwargs)
                                return json.dumps(result, ensure_ascii=False, indent=2)
                        except Exception as e:
                            self.logger.error(f"Tool {tool_name} failed: {e}")
                            return f"调用失败: {str(e)}"

                    # 同步执行异步函数
                    if loop.is_running():
                        # 如果循环正在运行，创建任务
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(asyncio.run, execute_api_call())
                            return future.result()
                    else:
                        # 如果循环未运行，直接运行
                        return loop.run_until_complete(execute_api_call())

                # 创建动态函数
                tool_func = create_function(full_signature, handler_func)
                tool_func.__doc__ = f"{service_name} - {ep_obj.description}"
                tool_func.__annotations__ = annotations

                return tool_func

            # 创建并注册工具函数
            tool_func = create_tool_func()
            self.mcp.tool()(tool_func)

    def run(self, transport: str = "stdio"):
        """启动MCP服务器"""
        self.logger.info(f"Starting platform MCP server with {len(self.registry.services)} services")
        self.mcp.settings.port = 8055
        self.mcp.settings.host = "0.0.0.0"
        self.mcp.run(transport="streamable-http")


# =============================================================================
# 配置示例和使用方法
# =============================================================================

def create_sample_config():
    """创建示例配置文件"""
    config = {
        "service_config": {
            "name": "user_service",
            "base_url": "https://api.platform-a.com/",
            "api_key": "your-api-key-here",
            "version": "v1",
            "timeout": 30,
            "max_retries": 3,
            "cache_ttl": 300
        },
        "service_definition": {
            "name": "user_service",
            "category": "用户管理",
            "description": "平台A的用户管理服务",
            "enabled": True,
            "endpoints": {
                "get_user": {
                    "path": "users/{user_id}",
                    "method": "GET",
                    "description": "获取用户信息",
                    "parameters": {
                        "user_id": {"type": "string", "required": True}
                    },
                    "rate_limit": 100
                },
                "create_user": {
                    "path": "users",
                    "method": "POST",
                    "description": "创建新用户",
                    "parameters": {
                        "name": {"type": "string", "required": True},
                        "email": {"type": "string", "required": True}
                    },
                    "rate_limit": 50
                },
                "list_users": {
                    "path": "users",
                    "method": "GET",
                    "description": "获取用户列表",
                    "parameters": {
                        "page": {"type": "integer", "default": 1},
                        "limit": {"type": "integer", "default": 20}
                    },
                    "rate_limit": 200
                }
            }
        }
    }

    with open("config/user_service_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print("示例配置文件已创建: user_service_config.json")


# =============================================================================
# 主程序入口
# =============================================================================

def main():
    """主程序"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建MCP服务器
    server = PlatformMCPServer("platform-a-integration")

    # 从配置文件注册服务
    try:
        # server.register_service_from_config("user_service_config.json")
        server.register_service_from_config("config/user_service_config.json")
        # 可以注册多个服务
        # server.register_service_from_config("payment_service_config.json")
        # server.register_service_from_config("notification_service_config.json")

    except FileNotFoundError:
        print("配置文件不存在，创建示例配置...")
        create_sample_config()
        print("请编辑配置文件并重新运行")
        return

    # 启动服务器
    server.run(transport="streamable-http")


if __name__ == "__main__":
    # 创建示例配置（如果需要）
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "create-config":
        create_sample_config()
    else:
        main()