from abc import ABC, abstractmethod
from typing import Sequence
from core.model import RawAnnouncement, Announcement

class AnnouncementSource(ABC):
    exchange: str

    @abstractmethod
    def fetch_latest(self, limit: int = 20) -> Sequence[RawAnnouncement]:
        """返回最近 limit 条 RawAnnouncement（不带tag）"""
        ...

class TitleTagger(ABC):
    @abstractmethod
    def tag(self, raw: RawAnnouncement) -> Announcement:
        """根据标题更新 tag，返回 Announcement"""
        ...

class Notifier(ABC):
    @abstractmethod
    def notify(self, ann: Announcement) -> None:
        ...
        """
        发送公告通知,这里需要额外做一步，当推送公告之后需要将announcement的hash存储到本地
        Notifier需要有一个变量记录已经推送过的announcement hash列表
        每次重启时需要从本地加载这个hash列表
        以防止重复推送
        """