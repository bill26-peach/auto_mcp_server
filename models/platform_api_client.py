
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin
import aiohttp
import time
from models.config.service_config import ServiceConfig
from models.config.api_endpoint import APIEndpoint
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
                # "Authorization": f"Bearer {self.config.api_key}",
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
        # cache_key = self._get_cache_key(endpoint.path, params)
        # if use_cache and cache_key in self._cache:
        #     cached_entry = self._cache[cache_key]
        #     if self._is_cache_valid(cached_entry):
        #         self.logger.debug(f"Cache hit for {endpoint.path}")
        #         return cached_entry["data"]

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
                    if endpoint.content_type == "form-data":
                        form_data = aiohttp.FormData()
                        for key, value in params.items():
                            # 如果后续支持文件上传，可在这里判断 value 是不是文件
                            form_data.add_field(key, str(value))
                        # mpbd需要appkey
                        form_data.add_field("appKey", self.config.api_key)
                        async with self.session.post(url, data=form_data) as response:
                            result = await self._handle_response(response, endpoint)
                            break
                    else:  # 默认 json
                        async with self.session.post(url, json=params) as response:
                            result = await self._handle_response(response, endpoint)
                            break

                else:
                    raise ValueError(f"Unsupported method: {endpoint.method}")

            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt == self.config.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)

        # 记录速率限制
        if endpoint.rate_limit:
            self._rate_limits[endpoint.path].append(time.time())

        # 缓存结果
        # if use_cache:
        #     self._cache[cache_key] = {
        #         "data": result,
        #         "timestamp": time.time()
        #     }

        return result

    async def _handle_response(
            self,
            response: aiohttp.ClientResponse,
            endpoint: APIEndpoint
    ) -> Dict[str, Any] | list:
        """处理API响应"""
        if response.status >= 400:
            error_text = await response.text()
            raise Exception(f"API Error {response.status}: {error_text}")

        if endpoint.response_format == "json":
            # 有些服务不会返回 application/json，这里放宽判断
            json_resp = await response.json(content_type=None)

            # 直接取 data.list（不存在就给空列表）
            return (json_resp.get("data") or {}).get("list", [])

        else:
            text = await response.text()
            return {"content": text}



