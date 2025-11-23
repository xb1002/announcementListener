"""
Bybit 交易所公告监听实现

支持的公告类型:
- 退市公告: https://announcements.bybit.com/zh-MY/?category=delistings
- 维护更新: https://announcements.bybit.com/zh-MY/?category=maintenance_updates

如果需要监听其他类型公告，请参考 Bybit 公告页面获取对应的 category 参数
并且添加到 CATEGORIES 字典中。
"""

import re
import json
import requests
from typing import Sequence, List, Optional, Dict
from datetime import datetime, timezone
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class BybitAnnouncementSource(AnnouncementSource):
    """Bybit 交易所公告数据源"""
    
    exchange = "Bybit"
    
    # Bybit 公告基础URL
    BASE_URL = "https://announcements.bybit.com"
    
    # 公告分类
    CATEGORIES = {
        "delistings": "delistings",              # 退市公告
        "maintenance": "maintenance_updates",    # 维护更新
        # "new_crypto": "new_crypto",              # 新币上线
    }
    
    # __NEXT_DATA__ script 标签匹配模式
    _NEXT_DATA_PATTERN = re.compile(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    
    # 语言别名映射
    _LANG_ALIASES: Dict[str, str] = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh_hans": "zh-CN",
        "zh-my": "zh-MY",
        "zh_my": "zh-MY",
        "zh-hant": "zh-TW",
        "zh_hant": "zh-TW",
        "zh-tw": "zh-TW",
        "zh_tw": "zh-TW",
        "en": "en-US",
        "en-us": "en-US",
        "en_us": "en-US",
        "en-gb": "en-GB",
        "en_gb": "en-GB",
    }
    
    def __init__(
        self, 
        categories: Optional[List[str]] = None, 
        lang: str = "zh-MY",
        timeout: int = 20
    ):
        """
        初始化 Bybit 公告源
        
        Args:
            categories: 要监听的公告分类列表，默认监听 delistings 和 maintenance
            lang: 语言代码 (zh-MY, zh-CN, en-US 等)
            timeout: API请求超时时间（秒）
        """
        if categories is None:
            # 默认监听退市公告和维护更新
            self.categories = [
                self.CATEGORIES["delistings"],
                self.CATEGORIES["maintenance"]
            ]
        else:
            self.categories = categories
        
        self.lang = self._normalize_lang(lang)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': self._get_accept_language(),
            'Cache-Control': 'no-cache',
        })
    
    @classmethod
    def _normalize_lang(cls, lang: str) -> str:
        """标准化语言代码"""
        candidate = lang or "zh-MY"
        normalized = candidate.replace("_", "-").strip()
        alias = cls._LANG_ALIASES.get(normalized.lower())
        if alias:
            return alias
        if "-" in normalized:
            parts = normalized.split("-", 1)
            return f"{parts[0].lower()}-{parts[1].upper()}"
        return normalized
    
    def _get_accept_language(self) -> str:
        """根据语言代码生成 Accept-Language header"""
        if self.lang.lower().startswith("zh"):
            return f"{self.lang},zh;q=0.9,en;q=0.8"
        if self.lang.lower().startswith("en"):
            return f"{self.lang},en;q=0.9"
        return f"{self.lang},en;q=0.8"
    
    def _build_listing_url(self, category: str) -> str:
        """构建分类列表 URL"""
        return f"{self.BASE_URL}/{self.lang}/?category={category}"
    
    def _build_article_url(self, path: str, category: str) -> str:
        """构建文章 URL"""
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.BASE_URL}/{self.lang}{path}?category={category}"
    
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """
        拉取最近的公告
        
        Args:
            limit: 每个分类拉取的公告数量
            
        Returns:
            RawAnnouncement 列表，按时间倒序排列
        """
        all_announcements = []
        
        for category in self.categories:
            try:
                announcements = self._fetch_by_category(category, limit)
                all_announcements.extend(announcements)
            except Exception as e:
                print(f"获取 Bybit 公告失败 (category={category}): {e}")
                continue
        
        # 按公告时间倒序排列
        all_announcements.sort(key=lambda x: x.announcement_time, reverse=True)
        
        return all_announcements
    
    def _fetch_by_category(self, category: str, limit: int) -> List[RawAnnouncement]:
        """
        根据分类拉取公告
        
        Args:
            category: 公告分类
            limit: 拉取数量
            
        Returns:
            RawAnnouncement 列表
        """
        url = self._build_listing_url(category)
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            
            # 从 HTML 中提取 __NEXT_DATA__ 数据
            next_data = self._extract_next_data(response.text)
            
            # 解析公告列表
            items = self._extract_items(next_data)
            
            if not items:
                raise Exception(f"未找到公告数据")
            
            # 限制返回数量
            items = items[:limit]
            
            return self._parse_items(items, category)
            
        except requests.RequestException as e:
            raise Exception(f"API请求失败: {e}")
    
    def _extract_next_data(self, html: str) -> dict:
        """从 HTML 中提取 __NEXT_DATA__ JSON 数据"""
        match = self._NEXT_DATA_PATTERN.search(html)
        if not match:
            raise Exception("未找到 __NEXT_DATA__ 数据")
        
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise Exception(f"解析 __NEXT_DATA__ JSON 失败: {e}")
    
    def _extract_items(self, next_data: dict) -> List[dict]:
        """从 __NEXT_DATA__ 中提取公告列表"""
        page_props = next_data.get("props", {}).get("pageProps", {})
        article_entity = page_props.get("articleInitEntity")
        
        if not isinstance(article_entity, dict):
            raise Exception("未找到文章列表数据")
        
        return article_entity.get("list", [])
    
    def _parse_items(self, items: List[dict], category: str) -> List[RawAnnouncement]:
        """
        解析公告数据为 RawAnnouncement
        
        Args:
            items: API返回的公告列表
            category: 公告分类
            
        Returns:
            RawAnnouncement 列表
        """
        announcements = []
        
        for item in items:
            try:
                # 解析发布时间（Unix 时间戳）
                publish_time = self._parse_timestamp(item.get("publish_time"))
                if publish_time is None:
                    publish_time = self._parse_timestamp(item.get("date_timestamp"))
                
                if publish_time is None:
                    continue
                
                # 获取标题
                title = item.get("title", "").strip()
                if not title:
                    continue
                
                # 获取 URL
                url_value = item.get("url", "").strip()
                if not url_value:
                    continue
                
                announcement = RawAnnouncement(
                    exchange=self.exchange,
                    title=title,
                    announcement_time=publish_time,
                    url=self._build_article_url(url_value, category)
                )
                
                announcements.append(announcement)
                
            except Exception as e:
                print(f"解析公告失败: {e}, item: {item}")
                continue
        
        return announcements
    
    @staticmethod
    def _parse_timestamp(value) -> Optional[datetime]:
        """解析 Unix 时间戳"""
        if value in (None, ""):
            return None
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (TypeError, ValueError):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (TypeError, ValueError):
                return None
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 Bybit 公告源
    source = BybitAnnouncementSource()
    
    # 拉取最近20条公告
    announcements = source.fetch_latest(limit=20)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)