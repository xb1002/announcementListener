"""
Huobi (HTX) 交易所公告监听实现

支持的公告类型:
- 重要公告: oneLevelId=360000031902, twoLevelId=360000039481
- 合约交易: oneLevelId=360000032161, twoLevelId=360000061481
- 币币交易: oneLevelId=115000389432, twoLevelId=900000741690

如果需要监听其他类型公告，请参考 HTX 支持中心获取对应的 oneLevelId 和 twoLevelId
并且添加到 CATEGORY_PAIRS 字典中。
"""

import requests
from typing import Sequence, List, Optional, Dict, Tuple
from datetime import datetime, timezone
from core.interface import AnnouncementSource
from core.model import RawAnnouncement


class HuobiAnnouncementSource(AnnouncementSource):
    """Huobi (HTX) 交易所公告数据源"""
    
    exchange = "HTX"
    
    # HTX API 端点
    LIST_API = "https://www.htx.com/-/x/support/public/getList/v2"
    
    # 文章 URL 模板
    ARTICLE_URL_TEMPLATE = "https://www.htx.com/{lang}/support/{article_id}"
    
    # 公告分类 (oneLevelId, twoLevelId) 配对
    CATEGORY_PAIRS: Dict[str, Tuple[str, str]] = {
        "important": ("360000031902", "360000039481"),      # 重要公告
        "futures": ("360000032161", "360000061481"),        # 合约交易
        "spot": ("115000389432", "900000741690"),           # 币币交易
    }
    
    # 语言别名映射
    _LANG_ALIASES: Dict[str, str] = {
        "zh": "zh-cn",
        "zh_cn": "zh-cn",
        "zh-cn": "zh-cn",
        "zh-hans": "zh-cn",
        "zh_hans": "zh-cn",
        "zh-tw": "zh-tw",
        "zh_tw": "zh-tw",
        "zh-hant": "zh-tw",
        "zh_hant": "zh-tw",
        "en": "en-us",
        "en_us": "en-us",
        "en-us": "en-us",
    }
    
    def __init__(
        self, 
        category_pairs: Optional[List[Tuple[str, str]]] = None,
        lang: str = "zh-cn",
        timeout: int = 20
    ):
        """
        初始化 Huobi 公告源
        
        Args:
            category_pairs: 要监听的公告分类 (oneLevelId, twoLevelId) 列表，默认监听合约和重要公告
            lang: 语言代码 (zh-cn, zh-tw, en-us 等)
            timeout: API请求超时时间（秒）
        """
        if category_pairs is None:
            # 默认监听合约交易和重要公告
            self.category_pairs = [
                self.CATEGORY_PAIRS["futures"],
                self.CATEGORY_PAIRS["important"],
                self.CATEGORY_PAIRS["spot"],
            ]
        else:
            self.category_pairs = category_pairs
        
        self.lang = self._normalize_lang(lang)
        self.timeout = timeout
        self.session = requests.Session()
        # 使用默认 headers
        self.session.headers.update(requests.utils.default_headers())
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
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
            标准化后的语言代码 (如 zh-cn, en-us)
        """
        if not lang:
            return "zh-cn"
        
        normalized = lang.replace("_", "-").strip().lower()
        return cls._LANG_ALIASES.get(normalized, normalized)
    
    def _build_article_url(self, article_id: int) -> str:
        """
        构建文章 URL
        
        Args:
            article_id: 文章ID
            
        Returns:
            文章完整URL
        """
        return self.ARTICLE_URL_TEMPLATE.format(lang=self.lang, article_id=article_id)
    
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """
        拉取最近的公告
        
        Args:
            limit: 每个分类拉取的公告数量
            
        Returns:
            RawAnnouncement 列表，按时间倒序排列
        """
        all_announcements = []
        seen_article_ids = set()
        
        for one_level_id, two_level_id in self.category_pairs:
            try:
                announcements = self._fetch_by_category(one_level_id, two_level_id, limit)
                # 去重
                for ann in announcements:
                    article_id = ann.url.split("/")[-1]
                    if article_id not in seen_article_ids:
                        all_announcements.append(ann)
                        seen_article_ids.add(article_id)
            except Exception as e:
                print(f"获取 HTX 公告失败 (oneLevelId={one_level_id}, twoLevelId={two_level_id}): {e}")
                continue
        
        # 按公告时间倒序排列
        all_announcements.sort(key=lambda x: x.announcement_time, reverse=True)
        
        return all_announcements
    
    def _fetch_by_category(
        self, 
        one_level_id: str, 
        two_level_id: str, 
        limit: int
    ) -> List[RawAnnouncement]:
        """
        根据分类ID拉取公告
        
        Args:
            one_level_id: 一级分类ID
            two_level_id: 二级分类ID
            limit: 拉取数量
            
        Returns:
            RawAnnouncement 列表
        """
        params = {
            "language": self.lang,
            "page": 1,
            "limit": min(limit, 50),  # API 最多支持 50 条
            "oneLevelId": one_level_id,
            "twoLevelId": two_level_id,
        }
        
        try:
            response = self.session.get(
                self.LIST_API,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # 解析 JSON 响应
            payload = response.json()
            
            # 检查响应码
            if payload.get("code") != 200:
                raise Exception(f"API 返回错误码: {payload.get('code')}")
            
            # 提取公告列表
            data = payload.get("data") or {}
            items = data.get("list") or []
            
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
            
        except requests.RequestException as e:
            raise Exception(f"API请求失败: {e}")
    
    def _parse_item(self, item: dict) -> Optional[RawAnnouncement]:
        """
        解析公告条目
        
        Args:
            item: 公告条目数据
            
        Returns:
            RawAnnouncement 或 None
        """
        # 获取文章ID
        article_id = item.get("id")
        if not article_id:
            return None
        
        # 获取标题
        title = (item.get("title") or "").strip()
        if not title:
            return None
        
        # 解析发布时间（毫秒时间戳）
        show_time = item.get("showTime")
        if not show_time:
            return None
        
        try:
            announcement_time = datetime.fromtimestamp(
                show_time / 1000,
                tz=timezone.utc
            )
        except (ValueError, OSError) as e:
            print(f"解析时间失败: {e}")
            return None
        
        # 构造 URL
        url = self._build_article_url(int(article_id))
        
        return RawAnnouncement(
            exchange=self.exchange,
            title=title,
            announcement_time=announcement_time,
            url=url
        )
    
    def __del__(self):
        """关闭会话"""
        if hasattr(self, 'session'):
            self.session.close()


# 使用示例
if __name__ == "__main__":
    # 创建 Huobi 公告源
    source = HuobiAnnouncementSource()
    
    # 拉取最近5条公告
    announcements = source.fetch_latest(limit=5)
    
    print(f"共获取 {len(announcements)} 条公告:\n")
    
    for ann in announcements:
        print(f"[{ann.exchange}] {ann.announcement_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"标题: {ann.title}")
        print(f"链接: {ann.url}")
        print("-" * 80)

