"""飞书通知器实现

负责将公告推送到飞书机器人，并维护已推送公告的历史记录以防止重复推送。
支持主频道和次要频道：
- 主频道：推送符合过滤规则的公告
- 次要频道（可选）：推送被主频道过滤掉的公告
"""

import time
import os
import requests
from typing import List, Set, Optional
from pathlib import Path
from core.interface import Notifier
from core.model import Announcement

import dotenv
dotenv.load_dotenv()  # 加载环境变量文件（如果存在）

class FeishuNotifier(Notifier):
    """飞书通知器"""
    
    def __init__(
        self, 
        webhook_url: Optional[str] = None,
        history_file: str = "feishu_sent_history.txt",
        timeout: int = 10
    ):
        """
        初始化飞书通知器
        
        Args:
            webhook_url: 飞书机器人 Webhook URL，多个 URL 使用英文逗号分隔；
                如果为 None 则从环境变量 FEISHU_WEBHOOK_URL 读取
            history_file: 历史记录文件路径（相对于当前工作目录），txt 格式
            timeout: 请求超时时间（秒）
        """
        webhook_value = webhook_url or os.getenv("FEISHU_WEBHOOK_URL")
        self.webhook_urls = self._parse_webhook_urls(webhook_value)
        if not self.webhook_urls:
            raise ValueError(
                "未提供 webhook_url，请通过参数传入或设置环境变量 FEISHU_WEBHOOK_URL"
            )

        # 保留原属性，兼容现有直接读取 webhook_url 的调用方。
        self.webhook_url = self.webhook_urls[0]
        
        self.history_file = Path(history_file)
        self.timeout = timeout
        
        # 已推送公告的 hash 集合
        self.sent_hashes: Set[str] = self._load_history()
    
    def notify(self, ann: Announcement, delay: float = 0) -> None:
        """
        发送公告通知到飞书
        
        Args:
            ann: 要推送的公告
            delay: 推送后等待的秒数（避免发送过快）
        """
        
        # 检查是否已经推送过
        if ann.hash in self.sent_hashes:
            # print(f"[跳过] 公告已推送过: {ann.title[:30]}...")
            # 跳过打印信息以避免循环日志过多
            return
        
        # 构建消息内容
        message = self._build_message(ann)
        
        failures = []
        for index, webhook_url in enumerate(self.webhook_urls, 1):
            try:
                self._send_message(webhook_url, message)
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                print(f"[失败] 第 {index} 个 Webhook 推送失败: {exc}")
                failures.append((index, exc))

        if failures:
            failed_indexes = ", ".join(str(index) for index, _ in failures)
            raise RuntimeError(f"部分飞书 Webhook 推送失败，序号: {failed_indexes}")

        # 所有 Webhook 均成功后才记录历史，避免部分目标永久漏发。
        self.sent_hashes.add(ann.hash)
        self._save_history(ann.hash)

        print(
            f"[成功] 已推送到 {len(self.webhook_urls)} 个 Webhook: "
            f"[{ann.exchange}] {ann.title[:30]}..."
        )

        if delay > 0:
            time.sleep(delay)

    @staticmethod
    def _parse_webhook_urls(webhook_value: Optional[str]) -> List[str]:
        """解析逗号分隔的 Webhook，并保持配置顺序去重。"""
        if not webhook_value:
            return []

        return list(dict.fromkeys(
            url.strip() for url in webhook_value.split(",") if url.strip()
        ))

    def _send_message(self, webhook_url: str, message: dict) -> None:
        """向单个飞书 Webhook 发送消息并检查业务响应。"""
        response = requests.post(
            webhook_url,
            json=message,
            timeout=self.timeout
        )
        response.raise_for_status()

        result = response.json()
        if result.get("code") != 0:
            raise RuntimeError(f"飞书 API 返回错误: {result.get('msg')}")
    
    def _build_message(self, ann: Announcement) -> dict:
        """
        构建飞书文本消息
        
        Args:
            ann: 公告对象
            
        Returns:
            飞书消息 JSON
        """
        # 格式化时间
        time_str = ann.announcement_time_local.strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建文本内容
        tag_display = f"[{ann.tag}] " if ann.tag else ""
        content = (
            f"🔔 {ann.exchange} 交易所公告\n"
            f"\n"
            f"{tag_display}{ann.title}\n"
            f"\n"
            f"发布时间: {time_str}\n"
            f"详情链接: {ann.url}"
        )
        
        # 使用 text 类型消息
        message = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }
        
        return message
    
    def _load_history(self) -> Set[str]:
        """
        从本地 txt 文件加载历史推送记录（每行一个 hash）
        
        Returns:
            已推送的 hash 集合
        """
        if not self.history_file.exists():
            print(f"[初始化] 历史记录文件不存在，创建新文件: {self.history_file}")
            return set()
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                # 每行一个 hash，去除空行和空白字符
                hashes = set(line.strip() for line in f if line.strip())
                print(f"[加载] 已加载 {len(hashes)} 条历史推送记录")
                return hashes
        except IOError as e:
            print(f"[警告] 加载历史记录失败: {e}，使用空记录")
            return set()
    
    def _save_history(self, hash_to_add: str) -> None:
        """
        追加新的 hash 到历史记录文件（流式写入）
        
        Args:
            hash_to_add: 要添加的 hash
        """
        try:
            # 确保目录存在
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 追加模式写入（流式，不需要重写整个文件）
            with open(self.history_file, 'a', encoding='utf-8') as f:
                f.write(f"{hash_to_add}\n")
            
        except IOError as e:
            print(f"[错误] 保存历史记录失败: {e}")
    
    def clear_history(self) -> None:
        """
        清空历史推送记录（谨慎使用）
        """
        self.sent_hashes.clear()
        # 清空文件
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                f.write("")
            print("[清空] 已清空历史推送记录")
        except IOError as e:
            print(f"[错误] 清空历史记录失败: {e}")
    
    def initial_hashes(self, announcements: list[Announcement]) -> None:
        """
        初始化历史记录，批量添加现有公告的 hash
        
        用于首次运行时，将已存在的公告标记为已推送，避免重复推送。
        
        Args:
            announcements: 公告列表
        """
        if not announcements:
            print("[初始化] 没有公告需要初始化")
            return
        
        added_count = 0
        for ann in announcements:
            if ann.hash not in self.sent_hashes:
                self.sent_hashes.add(ann.hash)
                self._save_history(ann.hash)
                added_count += 1
        
        print(f"[初始化] 已添加 {added_count} 条公告到历史记录")
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "total_sent": len(self.sent_hashes),
            "history_file": str(self.history_file),
            "file_exists": self.history_file.exists()
        }


class FeishuSecondaryNotifier(FeishuNotifier):
    """飞书次要频道通知器
    
    用于推送被主频道过滤掉的公告到次要频道。
    如果未配置次要频道 webhook，则不进行任何操作。
    """
    
    def __init__(
        self, 
        webhook_url: Optional[str] = None,
        history_file: str = "feishu_secondary_sent_history.txt",
        timeout: int = 10
    ):
        """
        初始化次要频道通知器
        
        Args:
            webhook_url: 飞书机器人 Webhook URL，多个 URL 使用英文逗号分隔；
                如果为 None 则从环境变量 FEISHU_SECONDARY_WEBHOOK_URL 读取
            history_file: 历史记录文件路径
            timeout: 请求超时时间（秒）
        """
        webhook_value = webhook_url or os.getenv("FEISHU_SECONDARY_WEBHOOK_URL")
        self.webhook_urls = self._parse_webhook_urls(webhook_value)
        
        # 次要频道是可选的，如果没有配置则设置为不可用状态
        self.enabled = bool(self.webhook_urls)
        
        if not self.enabled:
            print("[次要频道] 未配置次要频道 webhook，次要频道功能已禁用")
            self.sent_hashes: Set[str] = set()
            self.history_file = Path(history_file)
            self.timeout = timeout
            return

        self.webhook_url = self.webhook_urls[0]
        
        # 调用父类初始化（但跳过 webhook_url 验证）
        self.history_file = Path(history_file)
        self.timeout = timeout
        self.sent_hashes: Set[str] = self._load_history()
        
        print(f"[次要频道] 已启用次要频道通知")
    
    def notify(self, ann: Announcement, delay: float = 0) -> None:
        """
        发送公告通知到次要飞书频道
        
        如果次要频道未启用，则静默跳过。
        
        Args:
            ann: 要推送的公告
            delay: 推送后等待的秒数
        """
        if not self.enabled:
            return
        
        # 调用父类的 notify 方法
        super().notify(ann, delay)
    
    def initial_hashes(self, announcements: list[Announcement]) -> None:
        """
        初始化历史记录
        
        如果次要频道未启用，则静默跳过。
        """
        if not self.enabled:
            return
        
        super().initial_hashes(announcements)
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "enabled": self.enabled,
            "total_sent": len(self.sent_hashes),
            "history_file": str(self.history_file),
            "file_exists": self.history_file.exists() if self.enabled else False
        }


# 使用示例
if __name__ == "__main__":
    from datetime import datetime, timezone
    
    # 从环境变量读取 Webhook URL
    # 或者直接传入: notifier = FeishuNotifier(webhook_url="https://...")
    try:
        notifier = FeishuNotifier()  # 自动从环境变量读取
    except ValueError as e:
        print(f"错误: {e}")
        print("请设置环境变量 FEISHU_WEBHOOK_URL 或传入 webhook_url 参数")
        exit(1)
    
    # 首次运行时，初始化已有公告（避免重复推送）
    existing_announcements = [
        Announcement(
            exchange="Binance",
            title="币安已有公告 1",
            announcement_time=datetime.fromisoformat("2024-05-01T10:00:00+00:00"),
            url="https://www.binance.com/zh-CN/support/announcement/old-1",
            tag="历史公告"
        ),
        Announcement(
            exchange="Binance",
            title="币安已有公告 2",
            announcement_time=datetime.fromisoformat("2024-05-02T10:00:00+00:00"),
            url="https://www.binance.com/zh-CN/support/announcement/old-2",
            tag="历史公告"
        ),
    ]
    
    # 如果是首次运行，初始化历史记录
    if notifier.get_stats()["total_sent"] == 0:
        print("检测到首次运行，初始化历史记录...")
        notifier.initial_hashes(existing_announcements)
    
    # 创建新公告进行测试
    test_announcement = Announcement(
        exchange="Binance",
        title="币安将上线 TEST/USDT 交易对",
        announcement_time=datetime.fromisoformat("2024-06-01T12:00:00+00:00"),
        url="https://www.binance.com/zh-CN/support/announcement/test-123",
        tag="新币上线"
    )
    
    # 推送通知
    try:
        notifier.notify(test_announcement)
        print("\n统计信息:")
        print(notifier.get_stats())
    except Exception as e:
        print(f"推送失败: {e}")
