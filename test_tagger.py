"""
测试标签规则

主要功能：
1. 从所有交易所获取公告
2. 使用配置文件中的规则打标签
3. 输出标题与对应的标签
"""

from typing import List
from core.model import RawAnnouncement, Announcement
from tagger import RegexTitleTagger

# 导入所有交易所
from exchange.binance import BinanceAnnouncementSource
from exchange.okx import OKXAnnouncementSource
from exchange.gate import GateAnnouncementSource
from exchange.mexc import MexcAnnouncementSource
from exchange.huobi import HuobiAnnouncementSource
from exchange.bybit import BybitAnnouncementSource
from exchange.bitget import BitgetAnnouncementSource
from exchange.coinex import CoinExAnnouncementSource


class TaggerTester:
    """标签规则测试器"""
    
    def __init__(self, config_file: str = "config.yaml", fetch_limit: int = 10):
        """
        初始化测试器
        
        Args:
            config_file: 配置文件路径
            fetch_limit: 每个交易所获取的公告数量
        """
        self.fetch_limit = fetch_limit
        self.tagger = RegexTitleTagger(config_file)
        
        # 配置所有交易所
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
        
        print(f"配置文件: {config_file}")
        print(f"已配置 {len(self.sources)} 个交易所")
        print(f"每个交易所获取: {self.fetch_limit} 条公告")
        print()
    
    def fetch_all(self) -> List[RawAnnouncement]:
        """获取所有交易所的公告"""
        all_announcements = []
        
        print("=" * 100)
        print("开始获取公告")
        print("=" * 100)
        
        for source in self.sources:
            try:
                exchange_name = source.exchange
                print(f"[{exchange_name:8}] 正在获取...", end=" ")
                
                announcements = source.fetch_latest(limit=self.fetch_limit)
                all_announcements.extend(announcements)
                
                print(f"✓ 获取到 {len(announcements)} 条")
            except Exception as e:
                print(f"✗ 失败: {e}")
        
        print(f"\n总计获取: {len(all_announcements)} 条公告\n")
        return all_announcements
    
    def test_tagging(self, raw_announcements: List[RawAnnouncement]) -> List[Announcement]:
        """
        测试打标签
        
        Args:
            raw_announcements: 原始公告列表
            
        Returns:
            打好标签的公告列表
        """
        announcements = []
        
        print("=" * 100)
        print("打标签测试")
        print("=" * 100)
        
        for raw in raw_announcements:
            ann = self.tagger.tag(raw)
            announcements.append(ann)
        
        print(f"✓ 已为 {len(announcements)} 条公告打标签\n")
        return announcements
    
    def print_results(self, announcements: List[Announcement]) -> None:
        """
        输出标题与标签
        
        Args:
            announcements: 公告列表
        """
        print("=" * 100)
        print("标签结果")
        print("=" * 100)
        
        # 统计标签分布
        tag_stats = {}
        for ann in announcements:
            tag = ann.tag or "无标签"
            tag_stats[tag] = tag_stats.get(tag, 0) + 1
        
        # 显示统计
        print("\n标签统计:")
        for tag, count in sorted(tag_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  [{tag}]: {count} 条")
        
        print("\n" + "=" * 100)
        print("详细列表")
        print("=" * 100)
        
        # 按标签分组输出
        for tag in sorted(tag_stats.keys()):
            tag_announcements = [ann for ann in announcements if (ann.tag or "无标签") == tag]
            
            print(f"\n【{tag}】 共 {len(tag_announcements)} 条")
            print("-" * 100)
            
            for idx, ann in enumerate(tag_announcements, 1):
                # 截断过长的标题
                title = ann.title
                if len(title) > 80:
                    title = title[:77] + "..."
                
                print(f"  {idx}. [{ann.exchange:8}] {title}")
        
        print("\n" + "=" * 100)
    
    def run(self) -> None:
        """执行测试流程"""
        try:
            # 1. 获取公告
            raw_announcements = self.fetch_all()
            
            if not raw_announcements:
                print("[完成] 没有获取到任何公告")
                return
            
            # 2. 打标签
            announcements = self.test_tagging(raw_announcements)
            
            # 3. 输出结果
            self.print_results(announcements)
            
        except Exception as e:
            print(f"\n[错误] 测试失败: {e}")
            raise


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='测试标签规则')
    parser.add_argument('-c', '--config', default='config.yaml',
                        help='配置文件路径 (默认: config.yaml)')
    parser.add_argument('-l', '--limit', type=int, default=10,
                        help='每个交易所获取的公告数量 (默认: 10)')
    
    args = parser.parse_args()
    
    # 创建测试器并运行
    tester = TaggerTester(
        config_file=args.config,
        fetch_limit=args.limit
    )
    
    tester.run()


if __name__ == "__main__":
    main()
