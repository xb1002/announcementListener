"""
Gate 交易所公告监听实现

支持的公告类型:
- 最新公告: https://www.gate.com/zh/announcements/lastest
- 退市公告: https://www.gate.com/zh/announcements/delisted

如果需要监听其他类型公告，请参考 Gate 公告页面获取对应的路径
并且添加到 LISTING_PATHS 字典中。
"""

import re
import json
import requests
from typing import Sequence, List, Optional, Dict
from datetime import datetime, timezone
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class GateAnnouncementSource(AnnouncementSource):
    """Gate 交易所公告数据源"""
    
    exchange = "Gate"
    
    # Gate 基础URL
    BASE_URL = "https://www.gate.com"
    
    # 公告分类路径
    LISTING_PATHS = {
        "latest": "announcements/lastest",    # 最新公告
        "delisted": "announcements/delisted", # 退市公告
    }
    
    # __NEXT_DATA__ script 标签匹配模式
    _NEXT_DATA_PATTERN = re.compile(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    
    # 文章ID提取模式
    _ARTICLE_ID_PATTERN = re.compile(r"/article/(\d+)")
    
    # 语言别名映射
    _LANG_ALIASES: Dict[str, str] = {
        "zh-cn": "zh",
        "zh_cn": "zh",
        "zh-hans": "zh",
        "zh_hans": "zh",
        "zh-hant": "zh-tw",
        "zh_hant": "zh-tw",
        "zh-tw": "zh-tw",
        "zh_tw": "zh-tw",
        "zh-hk": "zh-tw",
        "zh_hk": "zh-tw",
        "en-us": "en",
        "en_us": "en",
        "en-gb": "en",
        "en_gb": "en",
    }
    
    # 语言到Cookie值的映射
    _LANG_COOKIE_MAP: Dict[str, str] = {
        "zh": "cn",
        "zh-tw": "tw",
        "en": "en",
    }
    
    def __init__(
        self, 
        listing_paths: Optional[List[str]] = None, 
        lang: str = "zh",
        fetch_details: bool = True,
        timeout: int = 20
    ):
        """
        初始化 Gate 公告源
        
        Args:
            listing_paths: 要监听的公告分类路径列表，默认监听 delisted 和 latest
            lang: 语言代码 (zh, zh-tw, en 等)
            fetch_details: 是否获取详情页以获得本地化标题
            timeout: API请求超时时间（秒）
        """
        if listing_paths is None:
            # 默认监听退市公告和最新公告
            self.listing_paths = [
                self.LISTING_PATHS["delisted"],
                self.LISTING_PATHS["latest"]
            ]
        else:
            self.listing_paths = listing_paths
        
        self.lang = self._normalize_lang(lang)
        self.fetch_details = fetch_details
        self.timeout = timeout
        self.session = requests.Session()
        # 使用默认 headers
        self.session.headers.update(requests.utils.default_headers())
        self.session.headers.update({
            'Accept-Language': self._get_accept_language(),
        })
        self._apply_lang_cookie()
    
    @classmethod
    def _normalize_lang(cls, lang: str) -> str:
        """标准化语言代码"""
        if not lang:
            return "zh"
        normalized = lang.replace("_", "-").strip().lower()
        return cls._LANG_ALIASES.get(normalized, normalized)
    
    def _get_accept_language(self) -> str:
        """根据语言代码生成 Accept-Language header"""
        if self.lang.startswith("zh"):
            return "zh-CN,zh;q=0.9,en;q=0.8"
        if self.lang.startswith("en"):
            return "en-US,en;q=0.9"
        return f"{self.lang},en;q=0.8"
    
    def _apply_lang_cookie(self) -> None:
        """设置语言 Cookie"""
        cookie_value = self._LANG_COOKIE_MAP.get(self.lang)
        if cookie_value:
            self.session.cookies.set("lang", cookie_value, domain="www.gate.com")
    
    def _build_listing_url(self, listing_path: str) -> str:
        """构建列表页 URL"""
        if self.lang:
            return f"{self.BASE_URL}/{self.lang}/{listing_path}"
        return f"{self.BASE_URL}/{listing_path}"
    
    def _build_article_url(self, article_id: str) -> str:
        """构建文章 URL"""
        prefix = self.BASE_URL
        if self.lang:
            prefix = f"{prefix}/{self.lang}"
        return f"{prefix}/announcements/article/{article_id}"
    
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
                print(f"获取 Gate 公告失败 (path={listing_path}): {e}")
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
            # 先尝试直接访问
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                # 403 错误，尝试使用 jina.ai 代理
                print(f"直接访问被拒绝(403)，尝试使用代理...")
                proxy_url = f"https://r.jina.ai/{url}"
                response = self.session.get(proxy_url, timeout=self.timeout)
                response.raise_for_status()
            else:
                raise
        
        response.encoding = "utf-8"
        
        # 从 HTML 中提取 __NEXT_DATA__ 数据
        next_data = self._extract_next_data(response.text)
        
        # 解析公告列表
        items = self._extract_items(next_data)
        
        if not items:
            raise Exception("未找到公告数据")
        
        # 转换为 RawAnnouncement
        announcements = []
        for item in items[:limit]:
            try:
                ann = self._parse_item(item)
                if ann:
                    announcements.append(ann)
            except Exception as e:
                print(f"解析公告失败: {e}")
                continue
        
        return announcements
    
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
        list_data = page_props.get("listData")
        
        if not isinstance(list_data, dict):
            raise Exception("未找到公告列表数据")
        
        return list_data.get("list", [])
    
    def _parse_item(self, item: dict) -> Optional[RawAnnouncement]:
        """
        解析公告条目
        
        Args:
            item: 公告条目数据
            
        Returns:
            RawAnnouncement 或 None
        """
        # 解析发布时间
        announcement_time = self._parse_release_datetime(item)
        if not announcement_time:
            return None
        
        # 提取文章 ID
        article_id = self._extract_article_id(item)
        if not article_id:
            return None
        
        # 获取标题（优先使用详情页标题以获得本地化）
        title = item.get("title", "")
        if self.fetch_details:
            detail = self._fetch_article_detail(article_id)
            if detail and detail.get("title"):
                title = detail["title"]
        
        # 构造 URL
        url = self._build_article_url(article_id)
        
        return RawAnnouncement(
            exchange=self.exchange,
            title=title,
            announcement_time=announcement_time,
            url=url
        )
    
    def _parse_release_datetime(self, item: dict) -> Optional[datetime]:
        """解析发布时间"""
        # 尝试从时间戳字段获取
        for key in ("release_timestamp", "created_t", "updated_t"):
            raw_value = item.get(key)
            if raw_value:
                dt = self._datetime_from_timestamp(raw_value)
                if dt:
                    return dt
        
        # 尝试从字符串日期获取
        release_time = item.get("release_time")
        if release_time:
            release_time = release_time.replace("UTC", "").strip()
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(release_time, fmt)
                    return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
                except ValueError:
                    continue
        
        return None
    
    @staticmethod
    def _datetime_from_timestamp(raw_value) -> Optional[datetime]:
        """从时间戳解析 datetime"""
        if raw_value in (None, ""):
            return None
        try:
            return datetime.fromtimestamp(int(raw_value), tz=timezone.utc)
        except (TypeError, ValueError):
            try:
                return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
            except (TypeError, ValueError):
                return None
    
    def _extract_article_id(self, item: dict) -> Optional[str]:
        """提取文章 ID"""
        if "id" in item and item["id"]:
            return str(item["id"])
        
        url_value = item.get("url")
        if not url_value:
            return None
        
        match = self._ARTICLE_ID_PATTERN.search(url_value)
        if match:
            return match.group(1)
        
        return None
    
    def _fetch_article_detail(self, article_id: str) -> Optional[dict]:
        """获取文章详情（用于获取本地化标题）"""
        try:
            url = self._build_article_url(article_id)
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            
            next_data = self._extract_next_data(response.text)
            detail = next_data.get("props", {}).get("pageProps", {}).get("detail")
            
            if isinstance(detail, dict) and detail.get("title"):
                return detail
        except Exception:
            pass
        
        return None
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 Gate 公告源
    source = GateAnnouncementSource(fetch_details=True)
    
    # 拉取最近5条公告
    announcements = source.fetch_latest(limit=5)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)