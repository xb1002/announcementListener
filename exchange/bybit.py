"""
Bybit 交易所公告监听实现

支持的公告类型:
- 退市公告: https://announcements.bybit.com/zh-MY/?category=delistings
- 维护更新: https://announcements.bybit.com/zh-MY/?category=maintenance_updates

如果需要监听其他类型公告，请参考 Bybit 公告页面获取对应的 category 参数
并且添加到 CATEGORIES 字典中。
"""

import requests
from typing import Sequence, List, Optional, Dict
from datetime import datetime, timezone
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class BybitAnnouncementSource(AnnouncementSource):
    """Bybit 交易所公告数据源"""
    
    exchange = "Bybit"
    
    # Bybit 官方公告 API
    API_URL = "https://api.bybit.com/v5/announcements/index"
    
    # 公告分类
    CATEGORIES = {
        "delistings": "delistings",              # 退市公告
        "maintenance": "maintenance_updates",    # 维护更新
        # "all": "",                                # 所有公告
    }
    
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
            # 默认监听所有类型
            self.categories = list(self.CATEGORIES.values())
        else:
            self.categories = categories
        
        self.lang = self._normalize_lang(lang)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "announcementListener/1.0",
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
        try:
            response = self.session.get(
                self.API_URL,
                params={
                    "locale": self.lang,
                    "type": category,
                    "limit": limit,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"Bybit 公告 API 请求失败: {exc}") from exc

        if payload.get("retCode") != 0:
            raise RuntimeError(
                f"Bybit 公告 API 返回错误: {payload.get('retMsg', '未知错误')}"
            )

        items = (payload.get("result") or {}).get("list") or []
        return self._parse_items(items[:limit], category)
    
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
                publish_time = self._parse_timestamp(
                    item.get("publishTime") or item.get("dateTimestamp")
                )
                
                if publish_time is None:
                    continue
                
                # 获取标题
                title = item.get("title", "").strip()
                if not title:
                    continue
                
                # 获取 URL
                url_value = (item.get("url") or "").strip()
                if not url_value:
                    continue
                
                announcement = RawAnnouncement(
                    exchange=self.exchange,
                    title=title,
                    announcement_time=publish_time,
                    url=url_value
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
            iv = int(value)
            # Heuristic: treat millisecond timestamps
            if iv > 10**12:
                iv = iv / 1000
            return datetime.fromtimestamp(iv, tz=timezone.utc)
        except (TypeError, ValueError):
            try:
                fv = float(value)
                if fv > 10**12:
                    fv = fv / 1000
                return datetime.fromtimestamp(fv, tz=timezone.utc)
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
