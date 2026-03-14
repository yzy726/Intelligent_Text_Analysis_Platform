import easyocr
import numpy as np
import os
from typing import List
from PIL import Image

from .base import OCRService
from app.models.models import PageResult, OCRResult, BoundingBox

class EasyOCRService(OCRService):
    """
    基于 EasyOCR 库实现的本地 OCR 服务。
    EasyOCR 是一个基于 PyTorch 的开源 OCR 库，支持多种语言。
    相比 PaddleOCR，它在 Windows 环境下的安装和兼容性通常更好，适合作为默认的本地回退方案。
    """
    # 类级别的变量，用于存储 EasyOCR 的 Reader 实例，实现单例模式
    _reader_instance = None

    def __init__(self):
        """
        初始化 EasyOCR 服务。
        由于加载深度学习模型非常耗时且占用大量内存，这里使用单例模式确保模型只被加载一次。
        """
        # 如果实例尚未创建，则进行初始化
        if EasyOCRService._reader_instance is None:
            print("DEBUG: 正在初始化 EasyOCR 模型...")
            
            # 指定模型文件的存储目录为项目根目录下的 resources/models/easyocr
            # 这样可以避免每次运行都去默认的 ~/.EasyOCR 目录查找，方便项目打包和迁移
            model_dir = os.path.join(os.getcwd(), "resources", "models", "easyocr")
            if not os.path.exists(model_dir):
                os.makedirs(model_dir, exist_ok=True)
                
            print(f"DEBUG: 模型目录: {model_dir}")
            
            # 检查系统是否有可用的 GPU (CUDA)
            # 如果有 GPU，EasyOCR 的识别速度会大幅提升
            import torch
            use_gpu = torch.cuda.is_available()
            if use_gpu:
                print("DEBUG: 检测到可用的 GPU，EasyOCR 将使用 GPU 加速。")
            else:
                print("DEBUG: 未检测到可用的 GPU，EasyOCR 将回退到 CPU 模式。")

            # 初始化 EasyOCR Reader
            # 参数说明:
            # - ['ch_sim', 'en']: 指定需要识别的语言列表，这里支持简体中文和英文
            # - gpu=use_gpu: 是否使用 GPU 加速
            # - model_storage_directory: 指定模型文件的本地存储路径
            # - download_enabled=False: 禁止自动从网络下载模型，强制使用本地已有的模型文件 (需提前下载好)
            EasyOCRService._reader_instance = easyocr.Reader(
                ['ch_sim', 'en'],
                gpu=use_gpu,
                model_storage_directory=model_dir,
                download_enabled=False
            )
            print("DEBUG: EasyOCR 模型初始化完成")
        
        # 将类级别的单例赋值给实例属性，方便后续调用
        self.reader = EasyOCRService._reader_instance

    def recognize(self, images: List[Image.Image], **kwargs) -> List[PageResult]:
        """
        使用 EasyOCR 对传入的图像列表进行文字识别。
        
        Args:
            images: 包含 PIL.Image 对象的列表。
            **kwargs: 接收其他可选参数 (当前未使用)。
            
        Returns:
            包含每页识别结果的 PageResult 列表。
        """
        all_pages_results: List[PageResult] = []

        # 遍历每一页图像
        for i, image in enumerate(images):
            # EasyOCR 的 readtext 方法支持直接处理 numpy 数组格式的图像
            # 将 PIL Image 转换为 numpy 数组
            image_np = np.array(image)
            
            # 执行 OCR 识别
            # 参数说明:
            # - detail=1: 返回详细的识别结果，包括边界框坐标、文本内容和置信度
            # - paragraph=False: 不将相邻的文本行合并为段落，保持单行级别的识别结果，这对于后续的结构化提取更有利
            results = self.reader.readtext(image_np, detail=1, paragraph=False)
            
            ocr_results_for_page: List[OCRResult] = []
            
            # 解析 EasyOCR 的返回结果
            for item in results:
                # EasyOCR 返回的 item 结构为: [ [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, confidence ]
                # 其中坐标是多边形的四个顶点
                points = item[0]
                text = item[1]
                confidence = item[2]
                
                # 提取所有顶点的 X 和 Y 坐标
                x_coordinates = [p[0] for p in points]
                y_coordinates = [p[1] for p in points]
                
                # 计算外接矩形的边界框 (BoundingBox)
                # 取所有顶点中最小的 X/Y 作为左上角，最大的 X/Y 作为右下角
                box = BoundingBox(
                    x_min=float(min(x_coordinates)),
                    y_min=float(min(y_coordinates)),
                    x_max=float(max(x_coordinates)),
                    y_max=float(max(y_coordinates))
                )
                
                # 组装单个识别结果对象
                ocr_results_for_page.append(OCRResult(
                    text=text,
                    box=box,
                    confidence=float(confidence)
                ))

            # 获取原始图像的宽度和高度
            width, height = image.size
            # 组装整页的识别结果对象
            all_pages_results.append(PageResult(
                page_number=i + 1,
                ocr_results=ocr_results_for_page,
                image_width=width,
                image_height=height
            ))
            
        return all_pages_results