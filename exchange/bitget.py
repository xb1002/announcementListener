"""
Bitget 交易所公告监听实现

支持的公告类型:
- 最新公告: https://www.bitget.com/zh-CN/support/sections/12508313443483

注意: Bitget 使用 Cloudflare 保护，可能需要通过 r.jina.ai 代理访问

如果需要监听其他类型公告，请参考 Bitget 帮助中心获取对应的 section ID
并且添加到 SECTION_IDS 字典中。
"""

import re
import requests
from typing import Sequence, List, Optional, Dict, Union
from datetime import datetime, timedelta, timezone
from core.interface import AnnouncementSource
from core.model import RawAnnouncement

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None  # type: ignore
    ZoneInfoNotFoundError = Exception  # type: ignore


class BitgetAnnouncementSource(AnnouncementSource):
    """Bitget 交易所公告数据源"""
    
    exchange = "Bitget"
    
    # Bitget 支持中心基础URL
    BASE_URL = "https://www.bitget.com"
    
    # r.jina.ai 代理（用于绕过 Cloudflare）
    PROXY_BASE = "https://r.jina.ai"
    
    # 公告分类 Section ID
    SECTION_IDS = {
        "latest": "12508313443483",      # 最新公告
        # "delistings": "12508313443290",  # 退市公告
    }
    
    # Markdown 解析模式
    _ARTICLE_LINK_PATTERN = re.compile(
        r"\[(?P<title>[^\]]+)\]\((?P<url>https?://www\.bitget\.com/[^)]+/support/articles/(?P<id>\d+)[^)]*)\)"
    )
    _METRICS_PATTERN = re.compile(r"^\d+(?:\s+\d+){0,2}$")
    _DATETIME_PATTERN = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2})$")
    
    @staticmethod
    def _asia_shanghai():
        """获取亚洲/上海时区"""
        if ZoneInfo is not None:
            try:
                return ZoneInfo("Asia/Shanghai")  # type: ignore
            except ZoneInfoNotFoundError:
                pass
        # 回退到固定偏移 (UTC+8)
        return timezone(timedelta(hours=8))
    
    _ASIA_SHANGHAI = _asia_shanghai()
    
    def __init__(
        self, 
        section_ids: Optional[List[str]] = None, 
        lang: str = "zh-CN",
        use_proxy: bool = True,
        timeout: int = 60
    ):
        """
        初始化 Bitget 公告源
        
        Args:
            section_ids: 要监听的公告分类 Section ID 列表，默认监听 latest
            lang: 语言代码 (zh-CN, en 等)
            use_proxy: 是否使用 jina.ai 代理绕过 Cloudflare
            timeout: API请求超时时间（秒）
        """
        if section_ids is None:
            # 默认监听退市公告和最新公告
            self.section_ids = [
                # self.SECTION_IDS["delistings"],
                self.SECTION_IDS["latest"]
            ]
        else:
            self.section_ids = section_ids
        
        self.lang = self._normalize_lang(lang)
        self.use_proxy = use_proxy
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
        })
    
    @staticmethod
    def _normalize_lang(lang: str) -> str:
        """标准化语言代码"""
        candidate = (lang or "zh-CN").strip()
        return candidate.replace("_", "-") or "zh-CN"
    
    def _build_page_url(self, section_id: str, page: int = 1) -> str:
        """构建页面 URL"""
        suffix = "" if page <= 1 else f"/{page}"
        original_url = f"{self.BASE_URL}/{self.lang}/support/sections/{section_id}{suffix}"
        
        if self.use_proxy:
            return f"{self.PROXY_BASE}/{original_url}"
        return original_url
    
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """
        拉取最近的公告
        
        Args:
            limit: 每个分类拉取的公告数量
            
        Returns:
            RawAnnouncement 列表，按时间倒序排列
        """
        all_announcements = []
        
        for section_id in self.section_ids:
            try:
                announcements = self._fetch_by_section(section_id, limit)
                all_announcements.extend(announcements)
            except Exception as e:
                print(f"获取 Bitget 公告失败 (section_id={section_id}): {e}")
                continue
        
        # 按公告时间倒序排列
        all_announcements.sort(key=lambda x: x.announcement_time, reverse=True)
        
        return all_announcements
    
    def _fetch_by_section(self, section_id: str, limit: int) -> List[RawAnnouncement]:
        """
        根据 section ID 拉取公告
        
        Args:
            section_id: 公告分类 ID
            limit: 拉取数量
            
        Returns:
            RawAnnouncement 列表
        """
        url = self._build_page_url(section_id, page=1)
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            
            # 从 Markdown 中解析公告
            announcements = self._parse_markdown(response.text)
            
            if not announcements:
                raise Exception(f"未找到公告数据")
            
            # 限制返回数量
            return announcements[:limit]
            
        except requests.RequestException as e:
            raise Exception(f"API请求失败: {e}")
    
    def _parse_markdown(self, markdown: str) -> List[RawAnnouncement]:
        """
        解析 Markdown 格式的公告数据
        
        Args:
            markdown: Markdown 文本
            
        Returns:
            RawAnnouncement 列表
        """
        announcements = []
        seen_ids = set()
        lines = markdown.splitlines()
        total = len(lines)
        index = 0
        
        while index < total:
            line = lines[index].strip()
            match = self._ARTICLE_LINK_PATTERN.match(line)
            
            if not match:
                index += 1
                continue
            
            article_id = match.group("id")
            if article_id in seen_ids:
                index += 1
                continue
            seen_ids.add(article_id)
            
            title = match.group("title").strip()
            article_url = match.group("url").replace("http://", "https://", 1)
            
            # 跳过空行
            cursor = index + 1
            while cursor < total and not lines[cursor].strip():
                cursor += 1
            
            # 跳过指标行（如果有）
            if cursor < total and self._METRICS_PATTERN.match(lines[cursor].strip()):
                cursor += 1
                while cursor < total and not lines[cursor].strip():
                    cursor += 1
            
            if cursor >= total:
                index += 1
                continue
            
            # 解析时间
            datetime_line = lines[cursor].strip()
            dt_match = self._DATETIME_PATTERN.match(datetime_line)
            
            if not dt_match:
                index += 1
                continue
            
            try:
                publish_dt = datetime.strptime(
                    dt_match.group(0),
                    "%Y-%m-%d %H:%M",
                ).replace(tzinfo=self._ASIA_SHANGHAI)
            except ValueError:
                index += 1
                continue
            
            announcement = RawAnnouncement(
                exchange=self.exchange,
                title=title,
                announcement_time=publish_dt,
                url=article_url
            )
            
            announcements.append(announcement)
            index = cursor + 1
        
        return announcements
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 Bitget 公告源（使用代理）
    source = BitgetAnnouncementSource(use_proxy=True)
    
    # 拉取最近20条公告
    announcements = source.fetch_latest(limit=20)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)