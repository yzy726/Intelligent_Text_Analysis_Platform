from .base import OCRService
from .paddle_ocr import PaddleOCRService
from .easy_ocr import EasyOCRService
from .baidu_ocr import BaiduOCRService

# 全局缓存字典，用于存储已实例化的 OCR 服务对象。
# 这样可以避免在每次请求时都重新加载模型 (特别是本地模型如 EasyOCR/PaddleOCR，加载非常耗时)，从而提高响应速度。
_service_cache = {}

def get_ocr_service(service_name: str) -> OCRService:
    """
    OCR 服务工厂函数 (Factory Pattern)。

    根据传入的服务名称，动态创建并返回对应的 OCR 服务实例。
    如果该服务之前已经被实例化过，则直接从缓存中返回，实现单例效果。

    Args:
        service_name: OCR 服务的名称标识 (例如 'local', 'paddle', 'baidu')。

    Returns:
        实现了 OCRService 接口的具体服务实例。

    Raises:
        ValueError: 如果请求了系统不支持的 OCR 服务名称。
    """
    # 1. 检查缓存：如果服务实例已存在，直接返回
    if service_name in _service_cache:
        return _service_cache[service_name]

    # 2. 实例化服务：根据名称创建对应的服务对象
    service = None
    if service_name == "local":
        # 'local' 默认映射到 EasyOCR (轻量级本地模型)
        service = EasyOCRService()
    elif service_name == "paddle":
        # 'paddle' 映射到 PaddleOCR (精度更高的本地模型)
        service = PaddleOCRService()
    elif service_name == "baidu":
        # 'baidu' 映射到百度云 OCR API
        service = BaiduOCRService()
    
    # 3. 缓存并返回：如果成功创建了实例，将其加入缓存并返回
    if service:
        _service_cache[service_name] = service
        return service

    # 4. 错误处理：如果传入了未知的服务名称，抛出异常
    raise ValueError(f"不支持的OCR服务: '{service_name}'")
