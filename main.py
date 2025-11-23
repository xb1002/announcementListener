"""
公告监听主程序

工作流程：
1. 从配置的交易所获取最新公告
2. 使用 TitleTagger 自动打标签
3. 根据 filter_config.yaml 过滤标签
4. 推送符合条件的公告到飞书
5. 每隔 600±50 秒循环一次
"""

import time
import yaml
from random import randint
from pathlib import Path
from typing import List, Set, Optional
from datetime import datetime

from tagger import RegexTitleTagger
from feishu import FeishuNotifier
from core.model import RawAnnouncement, Announcement

# 导入交易所
from exchange.binance import BinanceAnnouncementSource
from exchange.okx import OKXAnnouncementSource
from exchange.gate import GateAnnouncementSource
from exchange.mexc import MexcAnnouncementSource
from exchange.huobi import HuobiAnnouncementSource
from exchange.bybit import BybitAnnouncementSource
from exchange.bitget import BitgetAnnouncementSource
from exchange.coinex import CoinExAnnouncementSource


class AnnouncementFilter:
    """公告过滤器"""
    
    def __init__(self, config_file: str = "config.yaml"):
        """
        初始化过滤器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.allowed_tags: Set[str] = set()
        self.allow_no_tag: bool = False
        self._load_config()
    
    def _load_config(self) -> None:
        """加载过滤配置"""
        if not self.config_file.exists():
            print(f"[警告] 配置文件不存在: {self.config_file}，将推送所有公告")
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                filter_config = config.get('filter', {})
                self.allowed_tags = set(filter_config.get('allowed_tags', []))
                self.allow_no_tag = filter_config.get('allow_no_tag', False)
                
                print(f"[过滤器] 允许的标签: {self.allowed_tags or '全部'}")
                print(f"[过滤器] 允许无标签: {self.allow_no_tag}")
        except Exception as e:
            print(f"[错误] 加载过滤配置失败: {e}")
    
    def should_notify(self, ann: Announcement) -> bool:
        """
        判断公告是否应该推送
        
        Args:
            ann: 公告对象
            
        Returns:
            True 表示应该推送，False 表示过滤掉
        """
        # 如果没有配置允许的标签，推送所有
        if not self.allowed_tags:
            return True
        
        # 如果公告有标签，检查是否在允许列表中
        if ann.tag:
            return ann.tag in self.allowed_tags
        
        # 如果公告没有标签，根据 allow_no_tag 配置决定
        return self.allow_no_tag
    
    def reload_config(self) -> None:
        """重新加载配置（用于动态更新过滤规则）"""
        print("[重载] 重新加载过滤配置...")
        self._load_config()


class AnnouncementMonitor:
    """公告监听器主程序"""
    
    def __init__(self, config_file: str = "config.yaml"):
        """初始化监听器"""
        print("=" * 80)
        print("初始化公告监听器")
        print("=" * 80)
        
        # 加载配置
        self.config_file = Path(config_file)
        self._load_monitor_config()
        
        # 初始化组件
        self.tagger = RegexTitleTagger(config_file)
        self.filter = AnnouncementFilter(config_file)
        self.notifier = FeishuNotifier()
        
        # 配置交易所列表
        self.sources = [
            BinanceAnnouncementSource(),
            OKXAnnouncementSource(),
            GateAnnouncementSource(),
            MexcAnnouncementSource(),
            HuobiAnnouncementSource(),
            BybitAnnouncementSource(),
            BitgetAnnouncementSource(),
            CoinExAnnouncementSource(),
        ]
        
        print(f"[交易所] 已配置 {len(self.sources)} 个交易所")
        print()
    
    def _load_monitor_config(self) -> None:
        """加载监听器运行参数"""
        if not self.config_file.exists():
            print(f"[警告] 配置文件不存在: {self.config_file}，使用默认参数")
            self._set_default_config()
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                monitor_config = config.get('monitor', {})
                
                self.init_history = monitor_config.get('init_history_on_first_run', True)
                self.max_cycles = monitor_config.get('max_cycles', 0)
                self.interval_seconds = monitor_config.get('interval_seconds', 600)
                self.interval_random = monitor_config.get('interval_random', 50)
                self.fetch_limit = monitor_config.get('fetch_limit', 10)
                self.notify_delay = monitor_config.get('notify_delay', 1.0)
                
                print(f"[配置] 初始化历史: {self.init_history}")
                print(f"[配置] 循环次数: {self.max_cycles or '无限'}")
                print(f"[配置] 间隔时间: {self.interval_seconds}±{self.interval_random}秒")
                print(f"[配置] 获取限制: {self.fetch_limit}条/交易所")
                print(f"[配置] 推送延迟: {self.notify_delay}秒")
        except Exception as e:
            print(f"[错误] 加载监听器配置失败: {e}，使用默认参数")
            self._set_default_config()
    
    def _set_default_config(self) -> None:
        """设置默认配置"""
        self.init_history = True
        self.max_cycles = 0
        self.interval_seconds = 600
        self.interval_random = 50
        self.fetch_limit = 10
        self.notify_delay = 1.0
    
    def fetch_all_announcements(self) -> List[RawAnnouncement]:
        """
        从所有交易所获取公告
        
        Returns:
            所有原始公告列表
        """
        all_announcements = []
        
        for source in self.sources:
            try:
                exchange_name = source.exchange
                announcements = source.fetch_latest(limit=self.fetch_limit)
                all_announcements.extend(announcements)
                print(f"[{exchange_name:8}] 获取到 {len(announcements)} 条公告")
            except Exception as e:
                print(f"[{source.exchange:8}] 获取失败: {e}")
        
        return all_announcements
    
    def process_and_notify(self, raw_announcements: List[RawAnnouncement]) -> None:
        """
        处理公告：打标签、过滤、推送
        
        Args:
            raw_announcements: 原始公告列表
        """
        if not raw_announcements:
            print("[处理] 没有公告需要处理")
            return
        
        # 统计
        total_count = len(raw_announcements)
        notified_count = 0
        filtered_count = 0
        skipped_count = 0
        failed_count = 0
        
        for raw in raw_announcements:
            try:
                # 打标签
                announcement = self.tagger.tag(raw)
                
                # 检查是否应该推送
                if not self.filter.should_notify(announcement):
                    filtered_count += 1
                    continue
                
                # 尝试推送
                try:
                    self.notifier.notify(announcement, delay=self.notify_delay)
                    notified_count += 1
                except Exception as e:
                    # 如果是已推送过的公告，不算失败
                    error_msg = str(e)
                    if "已推送过" in error_msg or announcement.hash in self.notifier.sent_hashes:
                        skipped_count += 1
                    else:
                        failed_count += 1
                        # 简化错误信息显示
                        if "Connection" in error_msg or "Timeout" in error_msg:
                            print(f"[失败] [{announcement.exchange}] 网络错误")
                        else:
                            print(f"[失败] [{announcement.exchange}] {error_msg[:50]}")
            
            except Exception as e:
                print(f"[错误] 处理公告失败: {e}")
                failed_count += 1
        
        # 输出统计
        print(f"\n[统计] 总计: {total_count} | 推送: {notified_count} | "
              f"过滤: {filtered_count} | 跳过: {skipped_count} | 失败: {failed_count}")
    
    def initial_load(self) -> None:
        """首次运行：加载现有公告并初始化历史"""
        print("=" * 80)
        print("首次加载：初始化历史记录")
        print("=" * 80)
        
        # 检查是否需要初始化
        if not self.init_history:
            print("[跳过] 配置禁用了自动初始化历史记录")
            print()
            return
        
        # 获取所有公告
        raw_announcements = self.fetch_all_announcements()
        print(f"\n[汇总] 共获取 {len(raw_announcements)} 条公告")
        
        # 打标签
        announcements = [self.tagger.tag(raw) for raw in raw_announcements]
        
        # 初始化历史（标记为已推送，避免首次运行时大量推送）
        self.notifier.initial_hashes(announcements)
    
    def run_once(self) -> None:
        """执行一次监听循环"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("=" * 80)
        print(f"执行监听 - {current_time}")
        print("=" * 80)
        
        # 获取公告
        raw_announcements = self.fetch_all_announcements()
        print(f"\n[汇总] 共获取 {len(raw_announcements)} 条公告")
        
        # 处理并推送
        self.process_and_notify(raw_announcements)
        
        # 显示统计
        stats = self.notifier.get_stats()
        print(f"[历史] 已推送总计: {stats['total_sent']} 条")
        print()
    
    def run(self) -> None:
        """运行监听器主循环"""
        try:
            # 首次加载
            self.initial_load()
            
            # 主循环
            cycle_count = 0
            while True:
                cycle_count += 1
                
                # 执行一次监听
                self.run_once()
                
                # 检查是否达到循环次数限制
                if self.max_cycles > 0 and cycle_count >= self.max_cycles:
                    print(f"\n[完成] 已达到最大循环次数: {self.max_cycles}")
                    break
                
                # 计算下次等待时间
                wait_time = self.interval_seconds + randint(-self.interval_random, self.interval_random)
                next_time = datetime.now().timestamp() + wait_time
                next_time_str = datetime.fromtimestamp(next_time).strftime("%Y-%m-%d %H:%M:%S")
                
                print(f"[休眠] 等待 {wait_time} 秒，下次执行时间: {next_time_str}")
                print("=" * 80)
                print()
                
                time.sleep(wait_time)
        
        except KeyboardInterrupt:
            print("\n\n[退出] 收到中断信号，正在退出...")
            print(f"总共执行了 {cycle_count} 个监听周期")
            print(f"最终统计: {self.notifier.get_stats()}")
        
        except Exception as e:
            print(f"\n\n[错误] 程序异常退出: {e}")
            raise


def main():
    """主入口"""
    monitor = AnnouncementMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
