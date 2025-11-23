"""
MEXC 交易所公告监听实现

支持的公告类型:
- 退市公告: https://www.mexc.com/zh-MY/announcements/delistings
- 维护更新: https://www.mexc.com/zh-MY/announcements/maintenance-updates
- 交易更新: https://www.mexc.com/zh-MY/announcements/trading-updates

如果需要监听其他类型公告，请参考 MEXC 公告页面获取对应的路径
并且添加到 LISTING_PATHS 字典中。
"""

import re
import json
import requests
from typing import Sequence, List, Optional, Dict
from datetime import datetime, timezone
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class MexcAnnouncementSource(AnnouncementSource):
    """MEXC 交易所公告数据源"""
    
    exchange = "MEXC"
    
    # MEXC 基础URL
    BASE_URL = "https://www.mexc.com"
    
    # 公告分类路径
    LISTING_PATHS = {
        "delistings": "announcements/delistings",              # 退市公告
        "maintenance": "announcements/maintenance-updates",    # 维护更新
        "trading": "announcements/trading-updates",            # 交易更新
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
        listing_paths: Optional[List[str]] = None, 
        lang: str = "zh-MY",
        timeout: int = 20
    ):
        """
        初始化 MEXC 公告源
        
        Args:
            listing_paths: 要监听的公告分类路径列表，默认监听 delistings
            lang: 语言代码 (zh-MY, zh-CN, en-US 等)
            timeout: API请求超时时间（秒）
        """
        if listing_paths is None:
            # 默认监听退市公告
            self.listing_paths = [
                self.LISTING_PATHS["delistings"],
                self.LISTING_PATHS["maintenance"],
                self.LISTING_PATHS["trading"]
            ]
        else:
            self.listing_paths = listing_paths
        
        self.lang = self._normalize_lang(lang)
        self.timeout = timeout
        self.session = requests.Session()
        # 使用默认 headers
        self.session.headers.update(requests.utils.default_headers())
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })
    
    @classmethod
    def _normalize_lang(cls, lang: str) -> str:
        """
        标准化语言代码
        
        Args:
            lang: 输入的语言代码
            
        Returns:
            标准化后的语言代码 (如 zh-MY, en-US)
        """
        if not lang:
            return "zh-MY"
        
        normalized = lang.replace("_", "-").strip().lower()
        alias = cls._LANG_ALIASES.get(normalized)
        
        if alias:
            return alias
        
        # 处理未知语言代码，确保格式为 xx-XX
        if "-" in normalized:
            primary, region = normalized.split("-", 1)
            return f"{primary.lower()}-{region.upper()}"
        
        return normalized.lower()
    
    def _build_listing_url(self, listing_path: str) -> str:
        """构建列表页 URL"""
        if self.lang:
            return f"{self.BASE_URL}/{self.lang}/{listing_path}"
        return f"{self.BASE_URL}/{listing_path}"
    
    def _build_article_url(self, article_id: str, slug: Optional[str] = None) -> str:
        """
        构建文章 URL
        
        Args:
            article_id: 文章ID
            slug: URL slug（可选）
            
        Returns:
            文章完整URL
        """
        base = f"{self.BASE_URL}/{self.lang}" if self.lang else self.BASE_URL
        
        if article_id:
            return f"{base}/announcements/{article_id}"
        
        if slug:
            normalized = slug.lstrip("/")
            return f"{self._build_listing_url('')}/{normalized}"
        
        return base
    
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """
        拉取最近的公告
        
        Args:
            limit: 每个分类拉取的公告数量
            
        Returns:
            RawAnnouncement 列表，按时间倒序排列
        """
        all_announcements = []
        seen_urls = set()
        
        for listing_path in self.listing_paths:
            try:
                announcements = self._fetch_by_path(listing_path, limit)
                # 去重
                for ann in announcements:
                    if ann.url not in seen_urls:
                        all_announcements.append(ann)
                        seen_urls.add(ann.url)
            except Exception as e:
                print(f"获取 MEXC 公告失败 (path={listing_path}): {e}")
                continue
        
        # 按公告时间倒序排列
        all_announcements.sort(key=lambda x: x.announcement_time, reverse=True)
        
        return all_announcements
    
    def _fetch_by_path(self, listing_path: str, limit: int) -> List[RawAnnouncement]:
        """
        根据路径拉取公告
        
        Args:
            listing_path: 公告分类路径
            limit: 拉取数量
            
        Returns:
            RawAnnouncement 列表
        """
        url = self._build_listing_url(listing_path)
        
        try:
            # 设置 Referer
            headers = {'Referer': url}
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            
            # 从 HTML 中提取 __NEXT_DATA__ 数据
            next_data = self._extract_next_data(response.text)
            
            # 解析公告列表
            articles = self._extract_articles(next_data)
            
            if not articles:
                raise Exception("未找到公告数据")
            
            # 转换为 RawAnnouncement
            announcements = []
            for item in articles[:limit]:
                try:
                    ann = self._parse_article(item)
                    if ann:
                        announcements.append(ann)
                except Exception as e:
                    print(f"解析公告失败: {e}")
                    continue
            
            return announcements
            
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
    
    def _extract_articles(self, next_data: dict) -> List[dict]:
        """从 __NEXT_DATA__ 中提取公告列表"""
        articles = (
            next_data.get("props", {})
            .get("pageProps", {})
            .get("_sectionArticles", [])
        )
        
        if not isinstance(articles, list):
            raise Exception("公告列表数据格式错误")
        
        return articles
    
    def _parse_article(self, item: dict) -> Optional[RawAnnouncement]:
        """
        解析公告条目
        
        Args:
            item: 公告条目数据
            
        Returns:
            RawAnnouncement 或 None
        """
        # 获取标题
        title = item.get("title", "")
        if not title:
            return None
        
        # 解析发布时间
        announcement_time = self._parse_announcement_time(item)
        if not announcement_time:
            return None
        
        # 提取文章 ID 和 slug
        article_id = str(item.get("id", "")) if item.get("id") else ""
        slug = item.get("enPath", "")
        
        # 构造 URL
        url = self._build_article_url(article_id, slug)
        
        return RawAnnouncement(
            exchange=self.exchange,
            title=title,
            announcement_time=announcement_time,
            url=url
        )
    
    def _parse_announcement_time(self, item: dict) -> Optional[datetime]:
        """
        解析发布时间
        
        尝试从多个字段中获取时间戳（毫秒）
        """
        for key in ("displayTime", "publishTime", "updateTime"):
            value = item.get(key)
            if value:
                dt = self._datetime_from_ms(value)
                if dt:
                    return dt
        
        return None
    
    @staticmethod
    def _datetime_from_ms(value) -> Optional[datetime]:
        """
        从毫秒时间戳解析 datetime
        
        Args:
            value: 毫秒时间戳
            
        Returns:
            datetime 对象或 None
        """
        if value in (None, ""):
            return None
        
        try:
            milliseconds = int(value)
        except (TypeError, ValueError):
            return None
        
        if milliseconds <= 0:
            return None
        
        return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 MEXC 公告源
    source = MexcAnnouncementSource()
    
    # 拉取最近5条公告
    announcements = source.fetch_latest(limit=5)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)


