"""
标题标签器实现

基于正则表达式规则为公告标题自动打标签。
"""

import re
from typing import Optional, List, Dict
from pathlib import Path
import yaml

from core.interface import TitleTagger
from core.model import RawAnnouncement, Announcement


class RegexTitleTagger(TitleTagger):
    """基于正则表达式的标题标签器"""
    
    def __init__(self, config_file: str = "config.yaml"):
        """
        初始化标签器
        
        Args:
            config_file: 配置文件路径（相对于当前工作目录）
        """
        self.config_file = Path(config_file)
        self.rules: List[Dict] = []
        self._load_rules()
    
    def _load_rules(self) -> None:
        """从 YAML 文件加载规则"""
        if not self.config_file.exists():
            print(f"[警告] 配置文件不存在: {self.config_file}，将使用空规则")
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self.rules = config.get('tag_rules', [])
                print(f"[加载] 已加载 {len(self.rules)} 条标签规则")
        except Exception as e:
            print(f"[错误] 加载配置文件失败: {e}")
            self.rules = []
    
    def tag(self, raw: RawAnnouncement) -> Announcement:
        """
        根据标题匹配规则打标签
        
        Args:
            raw: 原始公告（不带标签）
            
        Returns:
            带标签的公告对象
        """
        tag = self._match_tag(raw.title)
        
        # 转换为 Announcement
        return Announcement(
            exchange=raw.exchange,
            title=raw.title,
            announcement_time=raw.announcement_time,
            url=raw.url,
            tag=tag
        )
    
    def _match_tag(self, title: str) -> Optional[str]:
        """
        匹配标题并返回对应的标签
        
        Args:
            title: 公告标题
            
        Returns:
            匹配到的标签名称，如果没有匹配则返回 None
        """
        for rule in self.rules:
            tag_name = rule.get('tag')
            patterns = rule.get('patterns', [])
            case_sensitive = rule.get('case_sensitive', False)
            
            # 检查是否匹配任意一个 pattern
            for pattern in patterns:
                flags = 0 if case_sensitive else re.IGNORECASE
                if re.search(pattern, title, flags):
                    return tag_name
        
        return None
    
    def reload_rules(self) -> None:
        """重新加载规则文件（用于动态更新规则）"""
        print("[重载] 重新加载标签规则...")
        self._load_rules()
    
    def test_title(self, title: str) -> Optional[str]:
        """
        测试一个标题会匹配到什么标签（调试用）
        
        Args:
            title: 要测试的标题
            
        Returns:
            匹配到的标签名称
        """
        tag = self._match_tag(title)
        if tag:
            print(f"[匹配] '{title}' -> '{tag}'")
        else:
            print(f"[未匹配] '{title}' -> None")
        return tag


# 使用示例
if __name__ == "__main__":
    from datetime import datetime, timezone
    
    # 创建标签器
    tagger = RegexTitleTagger()
    
    # 测试用例
    test_cases = [
        "币安将上线 XYZ/USDT 交易对",
        "Binance Will List ABC (ABC) Token",
        "关于下架 DEF/USDT 交易对的公告",
        "Delisting Notice: GHI Token",
        "系统维护公告",
        "Scheduled Maintenance Notification",
        "重要：安全升级通知",
        "新用户空投活动开始",
        "合约交易升级公告",
        "这是一个普通公告",
    ]
    
    print("=" * 80)
    print("测试标题匹配")
    print("=" * 80)
    print()
    
    for title in test_cases:
        tag = tagger.test_title(title)
    
    print()
    print("=" * 80)
    print("测试完整流程")
    print("=" * 80)
    print()
    
    # 创建原始公告
    raw_ann = RawAnnouncement(
        exchange="Binance",
        title="币安将上线 TEST/USDT 交易对",
        announcement_time=datetime(2024, 11, 23, 10, 0, 0, tzinfo=timezone.utc),
        url="https://www.binance.com/test"
    )
    
    # 打标签
    announcement = tagger.tag(raw_ann)
    
    print(f"原始公告: {raw_ann.title}")
    print(f"标签: {announcement.tag}")
    print(f"完整对象: {announcement}")
