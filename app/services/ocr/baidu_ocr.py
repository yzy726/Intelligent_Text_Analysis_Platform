import requests
import base64
import io
from typing import List
from PIL import Image

from .base import OCRService
from app.models.models import PageResult, OCRResult, BoundingBox

class BaiduOCRService(OCRService):
    """
    百度云 OCR 服务实现类。
    调用百度智能云的“通用文字识别（高精度含位置版）”API 进行文字识别。
    需要用户在百度智能云控制台创建应用并获取 API Key (AK) 和 Secret Key (SK)。
    """
    
    # 百度鉴权接口地址，用于获取 Access Token
    TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
    # 百度 OCR 通用文字识别（高精度含位置版）接口地址
    OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/accurate"

    def recognize(self, images: List[Image.Image], **kwargs) -> List[PageResult]:
        """
        调用百度 API 对图像列表进行识别。
        
        Args:
            images: PIL.Image 对象列表。
            **kwargs: 必须包含 'api_key' 和 'api_secret'。
            
        Returns:
            包含每页识别结果的 PageResult 列表。
        """
        # 从 kwargs 中提取鉴权信息
        api_key = kwargs.get("api_key")
        api_secret = kwargs.get("api_secret")
        
        if not api_key or not api_secret:
            raise ValueError("使用百度OCR服务必须提供 'api_key' 和 'api_secret'")

        # 1. 获取 Access Token (百度 API 调用的凭证)
        access_token = self._get_access_token(api_key, api_secret)
        
        all_pages_results: List[PageResult] = []

        # 遍历每一页图像进行处理
        for i, image in enumerate(images):
            # 2. 图像预处理：将 PIL Image 转换为 Base64 编码字符串，以符合百度 API 的要求
            img_byte_arr = io.BytesIO()
            # 百度 API 不支持 RGBA 格式 (带透明通道)，需要转换为 RGB
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            # 将图像保存为 JPEG 格式的字节流
            image.save(img_byte_arr, format='JPEG')
            img_bytes = img_byte_arr.getvalue()
            # 进行 Base64 编码
            base64_str = base64.b64encode(img_bytes).decode('utf-8')
            
            # 3. 构造请求参数并调用 OCR 接口
            params = {
                "image": base64_str,
                "vertexes_location": "true", # 要求返回文字外接多边形的顶点坐标
                "probability": "true"        # 要求返回识别结果的置信度
            }
            # 将 access_token 拼接到 URL 中
            request_url = f"{self.OCR_URL}?access_token={access_token}"
            # 百度 API 要求使用表单格式提交数据
            headers = {'content-type': 'application/x-www-form-urlencoded'}
            
            # 发送 POST 请求
            response = requests.post(request_url, data=params, headers=headers)
            result_json = response.json()
            
            # 检查 API 是否返回错误
            if "error_code" in result_json:
                error_msg = result_json.get("error_msg", "未知错误")
                raise Exception(f"百度OCR调用失败: {error_msg}")
            
            # 4. 解析百度 API 的返回结果，转换为系统统一的内部模型
            ocr_results_for_page: List[OCRResult] = []
            # 百度 API 的识别结果存储在 'words_result' 数组中
            words_result = result_json.get("words_result", [])
            
            for item in words_result:
                text = item.get("words", "")
                location = item.get("location", {})
                probability = item.get("probability", {})
                
                # 百度返回的坐标格式为 {top, left, width, height}
                # 需要将其转换为系统的 {x_min, y_min, x_max, y_max} 格式
                left = location.get("left", 0)
                top = location.get("top", 0)
                width = location.get("width", 0)
                height = location.get("height", 0)
                
                box = BoundingBox(
                    x_min=float(left),
                    y_min=float(top),
                    x_max=float(left + width),
                    y_max=float(top + height)
                )
                
                # 解析置信度：百度 API 返回的 probability 可能是个字典 (包含平均置信度、方差等)，也可能是个直接的数值
                confidence = 0.0
                if isinstance(probability, dict):
                    confidence = float(probability.get("average", 0.0))
                elif isinstance(probability, (int, float)):
                    confidence = float(probability)

                # 组装单个识别结果
                ocr_results_for_page.append(OCRResult(
                    text=text,
                    box=box,
                    confidence=confidence
                ))

            # 获取原始图像尺寸
            width, height = image.size
            # 组装整页的识别结果
            all_pages_results.append(PageResult(
                page_number=i + 1,
                ocr_results=ocr_results_for_page,
                image_width=width,
                image_height=height
            ))
            
        return all_pages_results

    def _get_access_token(self, api_key: str, api_secret: str) -> str:
        """
        内部辅助方法：使用 API Key (AK) 和 Secret Key (SK) 向百度鉴权服务器请求 Access Token。
        Access Token 的有效期通常为 30 天，实际生产环境中建议将其缓存起来，避免每次请求都重新获取。
        """
        params = {
            "grant_type": "client_credentials", # 固定值
            "client_id": api_key,
            "client_secret": api_secret
        }
        response = requests.post(self.TOKEN_URL, params=params)
        result = response.json()
        
        # 检查是否成功获取到 token
        if "access_token" not in result:
            error_desc = result.get("error_description", "未知错误")
            raise ValueError(f"获取百度Access Token失败: {error_desc}")
            
        return result["access_token"]