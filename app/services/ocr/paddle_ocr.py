from PIL import Image
import numpy as np
from typing import List
import cv2

from .base import OCRService
from app.models.models import PageResult, OCRResult, BoundingBox

class PaddleOCRService(OCRService):
    """
    基于 PaddleX (飞桨) 的 OCR 产线实现的本地 OCR 服务。
    PaddleOCR 在中文识别精度上通常表现优异，但其依赖库较多，在某些环境下的安装和配置可能较为复杂。
    参考文档: https://paddlepaddle.github.io/PaddleX/latest/pipeline_usage/tutorials/ocr_pipelines/OCR.html
    """
    def __init__(self):
        """
        初始化 PaddleOCR 服务。
        加载 PaddleX 的 OCR 预测管道 (Pipeline)。
        """
        print("DEBUG: 正在初始化 PaddleOCR...")
        import os
        # 强制禁用 MKLDNN 加速。
        # 在某些 CPU 环境下，开启 MKLDNN 可能会导致底层 C++ 库冲突或崩溃 (如 OMP Error #15)。
        os.environ["FLAGS_use_mkldnn"] = "0"
        
        from paddlex import create_pipeline
        # 初始化 PaddleX 的通用 OCR 产线
        # 该产线通常包含文本检测 (Detection) 和文本识别 (Recognition) 两个模型
        self.pipeline = create_pipeline(pipeline="OCR")
        print("DEBUG: PaddleOCR 初始化完成！")

    def recognize(self, images: List[Image.Image], **kwargs) -> List[PageResult]:
        """
        使用 PaddleX 对传入的图像列表进行文字识别。
        
        Args:
            images: 包含 PIL.Image 对象的列表。
            **kwargs: 接收其他可选参数 (当前未使用)。
            
        Returns:
            包含每页识别结果的 PageResult 列表。
        """
        all_pages_results: List[PageResult] = []

        # 遍历每一页图像
        for page_idx, image in enumerate(images):
            # 记录原始图像的尺寸，用于后续坐标校验，防止越界
            original_width, original_height = image.size
            
            # 图像格式转换：
            # PaddleX 底层通常使用 OpenCV (cv2) 处理图像，期望的格式是 BGR 颜色空间的 numpy 数组。
            # 而传入的 image 是 PIL.Image 对象 (通常是 RGB 格式)。
            image_np = np.array(image)
            # 检查图像是否为 3 通道 (彩色图像)
            if len(image_np.shape) == 3 and image_np.shape[2] == 3:
                # 将 RGB 转换为 BGR
                image_cv2 = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
            else:
                # 如果是灰度图或其他格式，直接使用
                image_cv2 = image_np
            
            print(f"DEBUG: 开始识别第 {page_idx + 1} 页... 图像尺寸: {original_width}x{original_height}")
            
            # 执行 PaddleX 预测
            # 参数说明:
            # - input: 输入的图像数据 (BGR 格式的 numpy 数组)
            # - use_doc_orientation_classify: 是否使用文档方向分类器 (这里设为 False 以加快速度，假设输入图像方向正确)
            # - use_doc_unwarping: 是否使用文档去畸变 (设为 False)
            # - use_textline_orientation: 是否使用文本行方向分类器 (设为 False)
            output = self.pipeline.predict(
                input=image_cv2,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
            
            ocr_results_for_page: List[OCRResult] = []
            
            # 解析 PaddleX 的预测输出
            # output 通常是一个生成器或列表，包含预测结果对象
            for res in output:
                # 获取结果的 JSON 字典表示
                # 注意：不同版本的 PaddleX 返回结构可能略有差异，这里做了兼容处理
                res_dict = res.json.get('res', res.json)
                
                # 提取识别出的文本列表、置信度列表和多边形坐标列表
                rec_texts = res_dict.get('rec_texts', [])
                rec_scores = res_dict.get('rec_scores', [])
                rec_polys = res_dict.get('rec_polys', [])
                
                # 将三个列表打包在一起遍历
                for text, score, poly in zip(rec_texts, rec_scores, rec_polys):
                    try:
                        # 解析多边形坐标 (poly 通常是包含 4 个顶点的列表，如 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]])
                        # 使用 max(0, min(val, max_val)) 确保坐标值不会超出图像的实际边界
                        x_coordinates = [max(0, min(float(p[0]), original_width)) for p in poly]
                        y_coordinates = [max(0, min(float(p[1]), original_height)) for p in poly]
                        
                        # 计算外接矩形的边界框
                        box = BoundingBox(
                            x_min=min(x_coordinates),
                            y_min=min(y_coordinates),
                            x_max=max(x_coordinates),
                            y_max=max(y_coordinates)
                        )
                        
                        # 组装单个识别结果对象
                        ocr_results_for_page.append(OCRResult(
                            text=str(text),
                            box=box,
                            confidence=float(score)
                        ))
                    except Exception as e:
                        # 捕获单个文本块解析时的异常，避免影响整个页面的识别
                        print(f"DEBUG: 解析坐标时出错: {e}")
                        continue

            # 获取原始图像尺寸
            width, height = image.size
            # 组装整页的识别结果对象
            all_pages_results.append(PageResult(
                page_number=page_idx + 1,
                ocr_results=ocr_results_for_page,
                image_width=width,
                image_height=height
            ))
            
        return all_pages_results
