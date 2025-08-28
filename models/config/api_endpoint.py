from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


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
    content_type: str = "json"  # 新增字段，可选: "json" | "form-data"
