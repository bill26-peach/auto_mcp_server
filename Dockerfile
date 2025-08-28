# 使用 Python 官方精简镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装 Python 依赖（不通过 requirements.txt）
RUN pip install --no-cache-dir \
    aiohttp>=3.12.15 \
    fastmcp>=2.10.6 \
    makefun>=1.16.0 \
    "mcp[cli]>=1.12.1" \
    uvicorn>=0.35.0 \
    schedule>=1.2.2

# 拷贝代码到镜像中
COPY . .

# 暴露 MCP 默认端口
EXPOSE 8055

# 启动 MCP Server（你可以改成实际主入口）
CMD ["python", "main.py"]
