"""
Platform A MCP Integration Server - 修复版本（含 schedule 定时清理）
完整的平台服务接入架构设计

- 修复了异步调用问题，确保 MCP 工具能正确执行
- 新增：每天 02:00 定时删除某目录下文件名包含 "mpdb2mcp" 的文件
"""

import logging
import time
import threading
import glob
import hashlib
import os
from datetime import datetime
import schedule  # ✅ 使用 schedule 做定时任务

from models.platform_mcp_server import PlatformMCPServer

CONFIG_DIR = "config"
CONFIG_GLOB = os.path.join(CONFIG_DIR, "*.json")

# ====================== 清理任务配置 ======================
# 需要定时清理的目标目录（请替换为你的实际路径）
CLEANUP_DIR = r"/app/config"
# 文件名中包含的关键字
CLEANUP_KEYWORD = "mpbd2mcp"
# 每天执行时间（24 小时制，本地时间）
CLEANUP_TIME = "02:00"
# ========================================================


# =============================================================================
# 工具函数与配置热加载
# =============================================================================

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def load_or_reload_configs(server, state: dict[str, str]) -> None:
    """
    扫描 config/*.json：
    - 新文件 或 内容哈希变化 -> 重新调用 register_service_from_config
    - 删除文件：这里只记录日志（除非你有 server 的卸载 API）
    """
    current_files = set(glob.glob(CONFIG_GLOB))
    known_files = set(state.keys())

    # 处理新增/更新
    for path in current_files:
        try:
            new_hash = file_sha256(path)
        except Exception as e:
            logging.warning("计算配置文件哈希失败: %s (%s)", path, e)
            continue

        if path not in state:
            logging.info("检测到新配置文件：%s，开始注册...", path)
            try:
                server.register_service_from_config(path)
                state[path] = new_hash
                logging.info("完成注册：%s", path)
            except FileNotFoundError:
                logging.error("文件消失或无法读取：%s", path)
            except Exception as e:
                logging.exception("注册失败 %s：%s", path, e)
        elif state[path] != new_hash:
            logging.info("检测到配置变更：%s，重新加载...", path)
            try:
                server.register_service_from_config(path)  # 假设幂等/覆盖
                state[path] = new_hash
                logging.info("完成重载：%s", path)
            except Exception as e:
                logging.exception("重载失败 %s：%s", path, e)

    # 处理删除
    removed = known_files - current_files
    for path in removed:
        logging.warning("配置文件被删除：%s", path)
        state.pop(path, None)

def start_config_watcher(server, interval_sec: float = 10.0) -> threading.Thread:
    """
    启动后台线程，定期扫描并热加载配置
    """
    state: dict[str, str] = {}

    # 启动前做一次完整加载
    load_or_reload_configs(server, state)

    def loop():
        while True:
            try:
                load_or_reload_configs(server, state)
            except Exception:
                logging.exception("扫描/加载配置时出现异常")
            time.sleep(interval_sec)

    t = threading.Thread(target=loop, daemon=True, name="config-watcher")
    t.start()
    return t


# =============================================================================
# 定时清理任务（schedule）
# =============================================================================

def delete_keyword_files(target_dir: str, keyword: str) -> None:
    """删除 target_dir 下文件名包含 keyword 的普通文件（不递归）"""
    if not os.path.isdir(target_dir):
        logging.warning("清理目录不存在或不可访问：%s", target_dir)
        return

    pattern = os.path.join(target_dir, f"*{keyword}*")
    files = [f for f in glob.glob(pattern) if os.path.isfile(f)]
    if not files:
        logging.info("未找到需要删除的文件（目录=%s，关键字=%s）", target_dir, keyword)
        return

    deleted, failed = 0, 0
    for f in files:
        try:
            os.remove(f)
            deleted += 1
            logging.info("已删除：%s", f)
        except Exception as e:
            failed += 1
            logging.warning("删除失败：%s（原因：%s）", f, e)

    logging.info("清理完成：删除=%d，失败=%d（目录=%s，关键字=%s）",
                 deleted, failed, target_dir, keyword)

def _schedule_loop():
    """schedule 的守护线程：每25秒检查一次待执行任务"""
    while True:
        try:
            schedule.run_pending()
        except Exception:
            logging.exception("执行定时任务时出现异常")
        time.sleep(25)

def start_daily_cleanup_with_schedule(target_dir: str, keyword: str, at_hhmm: str = "02:00") -> threading.Thread:
    """
    使用 schedule 安排每天 at_hhmm 运行 delete_keyword_files
    """
    # 先清理可能存在的旧任务（可选）
    schedule.clear("daily-cleanup")

    schedule.every().day.at(at_hhmm).do(
        delete_keyword_files, target_dir=target_dir, keyword=keyword
    ).tag("daily-cleanup")

    logging.info("已安排定时清理任务：每天 %s 执行（目录=%s，关键字=%s）",
                 at_hhmm, target_dir, keyword)

    t = threading.Thread(target=_schedule_loop, daemon=True, name="schedule-runner")
    t.start()
    return t


# =============================================================================
# 主程序入口
# =============================================================================
def main():
    """主程序"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    server = PlatformMCPServer("platform-a-integration")

    # 启动配置监听（包含首次加载）
    start_config_watcher(server, interval_sec=10.0)

    # 启动每天 02:00 的清理任务（删除文件名包含 mpdb2mcp 的文件）
    start_daily_cleanup_with_schedule(CLEANUP_DIR, CLEANUP_KEYWORD, at_hhmm=CLEANUP_TIME)

    # 可选：服务启动时先尝试清理一次（注释掉则只在 02:00 执行）
    # delete_keyword_files(CLEANUP_DIR, CLEANUP_KEYWORD)

    # 启动服务器（监听线程会持续监控并热加载；schedule 在线程中独立运行）
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
