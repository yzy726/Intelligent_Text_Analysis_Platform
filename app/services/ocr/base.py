from abc import ABC, abstractmethod
from typing import List
from PIL import Image
from app.models.models import PageResult

class OCRService(ABC):
    """
    OCR 服务的抽象基类 (接口)。
    定义了所有具体 OCR 服务 (如 EasyOCR, PaddleOCR, BaiduOCR) 必须遵循的规范。
    通过面向接口编程，使得上层业务逻辑与具体的 OCR 实现解耦，方便后续扩展和替换。
    """

    @abstractmethod
    def recognize(self, images: List[Image.Image], **kwargs) -> List[PageResult]:
        """
        核心识别方法：对传入的图像列表执行光学字符识别 (OCR)。
        子类必须实现此方法。

        Args:
            images: 一个包含 PIL.Image 对象的列表，每个对象代表文档的一页。
            **kwargs: 可选的额外参数，用于传递特定服务所需的配置 (例如云服务的 api_key 和 api_secret)。

        Returns:
            List[PageResult]: 一个列表，其中每个元素对应一页的识别结果 (包含文本、坐标、置信度等)。
        """
        pass
