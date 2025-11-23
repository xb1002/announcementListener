"""
CoinEx 交易所公告监听实现

支持的公告类型:
- 最新公告: https://www.coinex.com/zh-hans/announcements

注意: CoinEx 使用 Cloudflare 保护，需要通过 r.jina.ai 代理访问

如果需要监听其他类型公告，请参考 CoinEx 公告页面获取对应的 category ID
并且添加到 CATEGORY_IDS 字典中。
"""

import re
import time
import requests
from typing import Sequence, List, Optional, Dict, Tuple
from datetime import datetime, date, timedelta, timezone
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class CoinExAnnouncementSource(AnnouncementSource):
    """CoinEx 交易所公告数据源"""
    
    exchange = "CoinEx"
    
    # CoinEx 基础URL
    BASE_URL = "https://www.coinex.com"
    
    # r.jina.ai 代理（用于绕过 Cloudflare）
    PROXY_PREFIX = "https://r.jina.ai/"
    
    # 公告分类 Category ID
    CATEGORY_IDS = {
        # "delistings": "14108182730900",  # 退市公告
        "latest": None,                   # 最新公告（不指定category）
    }
    
    # 请求配置
    REQUEST_TIMEOUT = 30
    MAX_RETRIES = 3
    RETRY_BACKOFF_SECONDS = 5
    
    # Markdown 解析模式
    _LINK_PATTERN = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>https://[^\)]+)\)")
    _LISTING_PUBLISHED_PATTERN = re.compile(
        r"发布时间：(?P<date>\d{4}-\d{2}-\d{2})"
    )
    
    # 语言别名映射
    _LANG_ALIASES: Dict[str, str] = {
        "zh": "zh-hans",
        "zh_cn": "zh-hans",
        "zh-cn": "zh-hans",
        "zh-hans": "zh-hans",
        "zh-hant": "zh-hant",
        "zh_tw": "zh-hant",
        "zh-tw": "zh-hant",
        "en": "en",
        "en-us": "en",
        "en-gb": "en",
    }
    
    def __init__(
        self, 
        category_ids: Optional[List[Optional[str]]] = None, 
        lang: str = "zh-hans",
        use_proxy: bool = True,
        timeout: int = 30
    ):
        """
        初始化 CoinEx 公告源
        
        Args:
            category_ids: 要监听的公告分类 ID 列表，默认监听 latest
            lang: 语言代码 (zh-hans, zh-hant, en 等)
            use_proxy: 是否使用 jina.ai 代理绕过 Cloudflare
            timeout: API请求超时时间（秒）
        """
        if category_ids is None:
            # 默认监听退市公告和最新公告
            self.category_ids = [
                # self.CATEGORY_IDS["delistings"],
                self.CATEGORY_IDS["latest"]
            ]
        else:
            self.category_ids = category_ids
        
        self.lang = self._normalize_lang(lang)
        self.use_proxy = use_proxy
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
        })
    
    @classmethod
    def _normalize_lang(cls, lang: str) -> str:
        """标准化语言代码"""
        candidate = (lang or "zh-hans").strip().lower().replace("_", "-")
        return cls._LANG_ALIASES.get(candidate, candidate)
    
    def _build_listing_url(self, category_id: Optional[str]) -> str:
        """构建列表页 URL"""
        if category_id:
            return f"{self.BASE_URL}/{self.lang}/announcements?category={category_id}"
        return f"{self.BASE_URL}/{self.lang}/announcements"
    
    def _proxied_url(self, url: str) -> str:
        """添加代理前缀"""
        if self.use_proxy:
            return f"{self.PROXY_PREFIX}{url}"
        return url
    
    def _get_with_retries(self, url: str) -> requests.Response:
        """带重试的 GET 请求"""
        last_exc = None
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=self.timeout)
                
                # 处理限流和服务不可用
                if response.status_code in {429, 503}:
                    if attempt < self.MAX_RETRIES:
                        time.sleep(self.RETRY_BACKOFF_SECONDS * attempt)
                        continue
                
                response.raise_for_status()
                return response
                
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_BACKOFF_SECONDS * attempt)
                    continue
        
        if last_exc:
            raise last_exc
        raise Exception("Failed to fetch URL without capturing an exception.")
    
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
        
        for category_id in self.category_ids:
            try:
                announcements = self._fetch_by_category(category_id, limit)
                # 去重
                for ann in announcements:
                    if ann.url not in seen_urls:
                        all_announcements.append(ann)
                        seen_urls.add(ann.url)
            except Exception as e:
                print(f"获取 CoinEx 公告失败 (category_id={category_id}): {e}")
                continue
        
        # 按公告时间倒序排列
        all_announcements.sort(key=lambda x: x.announcement_time, reverse=True)
        
        return all_announcements
    
    def _fetch_by_category(self, category_id: Optional[str], limit: int) -> List[RawAnnouncement]:
        """
        根据分类 ID 拉取公告
        
        Args:
            category_id: 公告分类 ID（None 表示所有公告）
            limit: 拉取数量
            
        Returns:
            RawAnnouncement 列表
        """
        listing_url = self._build_listing_url(category_id)
        proxied_url = self._proxied_url(listing_url)
        
        try:
            response = self._get_with_retries(proxied_url)
            response.encoding = "utf-8"
            
            # 从 Markdown 中解析公告条目
            entries = self._extract_listing_entries(response.text)
            
            if not entries:
                raise Exception("未找到公告数据")
            
            # 转换为 RawAnnouncement
            announcements = self._convert_entries(entries)
            
            # 限制返回数量
            return announcements[:limit]
            
        except Exception as e:
            raise Exception(f"请求失败: {e}")
    
    def _extract_listing_entries(self, listing_text: str) -> List[Tuple[str, str, Optional[date]]]:
        """
        从 Markdown 文本中提取公告条目
        
        Args:
            listing_text: Markdown 文本
            
        Returns:
            (标题, URL, 发布日期) 元组列表
        """
        entries = []
        lines = listing_text.splitlines()
        total = len(lines)
        index = 0
        
        while index < total:
            line = lines[index].strip()
            match = self._LINK_PATTERN.match(line)
            
            if match and "/announcements/detail/" in match.group("url"):
                title = match.group("title").strip()
                url = match.group("url").strip()
                release_date = None
                
                # 向前查找发布日期
                lookahead = index + 1
                while lookahead < total:
                    candidate = lines[lookahead].strip()
                    if not candidate:
                        lookahead += 1
                        continue
                    
                    publish_match = self._LISTING_PUBLISHED_PATTERN.search(candidate)
                    if publish_match:
                        try:
                            release_date = datetime.strptime(
                                publish_match.group("date"), "%Y-%m-%d"
                            ).date()
                        except ValueError:
                            release_date = None
                        break
                    break
                
                entries.append((title, url, release_date))
                index = lookahead
            
            index += 1
        
        return entries
    
    def _convert_entries(self, entries: List[Tuple[str, str, Optional[date]]]) -> List[RawAnnouncement]:
        """
        将条目转换为 RawAnnouncement
        
        Args:
            entries: (标题, URL, 发布日期) 元组列表
            
        Returns:
            RawAnnouncement 列表
        """
        announcements = []
        tz_utc_plus_8 = timezone(timedelta(hours=8))
        
        for title, url, release_date in entries:
            # 构造发布时间
            if release_date:
                announcement_time = datetime.combine(
                    release_date,
                    datetime.min.time(),
                    tzinfo=tz_utc_plus_8,
                )
            else:
                announcement_time = datetime.now(timezone.utc)
            
            announcement = RawAnnouncement(
                exchange=self.exchange,
                title=title,
                announcement_time=announcement_time,
                url=url
            )
            
            announcements.append(announcement)
        
        return announcements
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 CoinEx 公告源（使用代理）
    source = CoinExAnnouncementSource(use_proxy=True)
    
    # 拉取最近20条公告
    announcements = source.fetch_latest(limit=20)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)