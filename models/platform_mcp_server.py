import json
import logging
import asyncio

import time
from makefun import create_function
from mcp.server.fastmcp import FastMCP
from .service_registry import ServiceRegistry
from models.config.service_config import ServiceConfig
from models.config.api_endpoint import APIEndpoint
from models.config.service_definition import ServiceDefinition
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
            # 方法名
            tool_name = f"{service_def.name}_{endpoint_name}"

            def create_tool_func(ep_name=endpoint_name, service_name=service_def.name, ep_obj=endpoint):
                param_defs = ep_obj.parameters

                sig_parts = []
                annotations = {}

                for param_name, param_info in param_defs.items():
                    openapi_type = param_info.get("type", "string")
                    py_type = map_openapi_type_to_python(openapi_type)
                    annotations[param_name] = py_type

                    # 如果有 defaultValue 就用它，否则统一用 None
                    if "defaultValue" in param_info:
                        default = param_info["defaultValue"]
                    else:
                        default = None

                    sig_parts.append(f"{param_name}: {py_type.__name__} = {repr(default)}")

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
                                result = await client.call_api(endpoint_obj, kwargs, False)
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
                tool_func.__doc__ = ep_obj.description
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
