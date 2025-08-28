from dataclasses import dataclass
from typing import Dict
from .api_endpoint import APIEndpoint


@dataclass
class ServiceDefinition:
    """服务定义"""
    name: str
    category: str
    endpoints: Dict[str, APIEndpoint]
    description: str = ""
    enabled: bool = True
