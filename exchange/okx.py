"""
OKX 交易所公告监听实现

支持的公告类型:
- 最新公告: https://www.okx.com/zh-hans/help/section/announcements-latest-announcements

如果需要监听其他类型公告，请参考 OKX 帮助中心获取对应的 section path
并且添加到 SECTION_PATHS 字典中。
"""

import re
import json
import requests
from typing import Sequence, List, Optional
from datetime import datetime, date
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class OKXAnnouncementSource(AnnouncementSource):
    """OKX 交易所公告数据源"""
    
    exchange = "OKX"
    
    # 公告分类路径
    SECTION_PATHS = {
        "latest": "announcements-latest-announcements",  # 最新公告
        # "delistings": "announcements-delistings",        # 退市公告
        # 如需添加更多分类，访问 https://www.okx.com/zh-hans/help 查看可用路径
    }
    
    # appState script 标签匹配模式
    _APP_STATE_PATTERN = re.compile(
        r'<script[^>]*id="appState"[^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    
    def __init__(
        self, 
        section_paths: Optional[List[str]] = None, 
        lang: str = "zh-hans",
        timeout: int = 20
    ):
        """
        初始化 OKX 公告源
        
        Args:
            section_paths: 要监听的公告分类路径列表，默认监听 latest 和 delistings
            lang: 语言代码 (zh-hans, zh-hant, en 等)
            timeout: API请求超时时间（秒）
        """
        if section_paths is None:
            # 默认监听最新公告和退市公告
            self.section_paths = [
                self.SECTION_PATHS["latest"],
                self.SECTION_PATHS["delistings"]
            ]
        else:
            self.section_paths = section_paths
        
        self.lang = lang
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': self._get_accept_language(),
            'Cache-Control': 'no-cache',
        })
    
    def _get_accept_language(self) -> str:
        """根据语言代码生成 Accept-Language header"""
        normalized = self.lang.lower()
        if normalized.startswith("zh"):
            return "zh-CN,zh;q=0.9,en;q=0.8"
        if normalized.startswith("en"):
            return "en-US,en;q=0.9"
        return f"{normalized},en;q=0.8"
    
    def _build_section_url(self, section_path: str) -> str:
        """构建 section URL"""
        normalized_lang = self.lang.strip().lower()
        if normalized_lang == "en":
            return f"https://www.okx.com/help/section/{section_path}"
        return f"https://www.okx.com/{normalized_lang}/help/section/{section_path}"
    
    def _build_article_url(self, slug: str) -> str:
        """构建文章 URL"""
        normalized_lang = self.lang.strip().lower()
        prefix = "https://www.okx.com"
        if normalized_lang != "en":
            prefix = f"{prefix}/{normalized_lang}"
        return f"{prefix}/help/{slug}"
    
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """
        拉取最近的公告
        
        Args:
            limit: 每个分类拉取的公告数量
            
        Returns:
            RawAnnouncement 列表，按时间倒序排列
        """
        all_announcements = []
        
        for section_path in self.section_paths:
            try:
                announcements = self._fetch_by_section(section_path, limit)
                all_announcements.extend(announcements)
            except Exception as e:
                print(f"获取 OKX 公告失败 (section={section_path}): {e}")
                continue
        
        # 按公告时间倒序排列
        all_announcements.sort(key=lambda x: x.announcement_time, reverse=True)
        
        return all_announcements
    
    def _fetch_by_section(self, section_path: str, limit: int) -> List[RawAnnouncement]:
        """
        根据 section path 拉取公告
        
        Args:
            section_path: 公告分类路径
            limit: 拉取数量
            
        Returns:
            RawAnnouncement 列表
        """
        url = self._build_section_url(section_path)
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = "utf-8"
            
            # 从 HTML 中提取 appState 数据
            app_state = self._extract_app_state(response.text)
            
            # 解析公告列表
            items = self._extract_items(app_state)
            
            if not items:
                raise Exception(f"未找到公告数据")
            
            # 限制返回数量
            items = items[:limit]
            
            return self._parse_items(items)
            
        except requests.RequestException as e:
            raise Exception(f"API请求失败: {e}")
    
    def _extract_app_state(self, html: str) -> dict:
        """从 HTML 中提取 appState JSON 数据"""
        match = self._APP_STATE_PATTERN.search(html)
        if not match:
            raise Exception("未找到 appState 数据")
        
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise Exception(f"解析 appState JSON 失败: {e}")
    
    def _extract_items(self, app_state: dict) -> List[dict]:
        """从 appState 中提取公告列表"""
        section_data = (
            app_state.get("appContext", {})
            .get("initialProps", {})
            .get("sectionData", {})
        )
        article_list = section_data.get("articleList", {})
        return article_list.get("items", [])
    
    def _parse_items(self, items: List[dict]) -> List[RawAnnouncement]:
        """
        解析公告数据为 RawAnnouncement
        
        Args:
            items: API返回的公告列表
            
        Returns:
            RawAnnouncement 列表
        """
        announcements = []
        
        for item in items:
            try:
                # 解析发布时间 (ISO 8601 格式)
                publish_time_str = item.get("publishTime")
                if not publish_time_str:
                    continue
                
                announcement_time = self._parse_iso8601(publish_time_str)
                if announcement_time is None:
                    continue
                
                # 获取 slug
                slug = item.get("slug", "")
                if not slug:
                    continue
                
                announcement = RawAnnouncement(
                    exchange=self.exchange,
                    title=item.get("title", ""),
                    announcement_time=announcement_time,
                    url=self._build_article_url(slug)
                )
                
                announcements.append(announcement)
                
            except Exception as e:
                print(f"解析公告失败: {e}, item: {item}")
                continue
        
        return announcements
    
    @staticmethod
    def _parse_iso8601(value: str) -> Optional[datetime]:
        """解析 ISO 8601 格式的时间字符串"""
        if not value:
            return None
        try:
            # 处理 Z 结尾的 UTC 时间
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 OKX 公告源
    source = OKXAnnouncementSource()
    
    # 拉取最近20条公告
    announcements = source.fetch_latest(limit=20)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)