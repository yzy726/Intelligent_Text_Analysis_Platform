from PIL import Image, ImageDraw
from typing import List, Union
from app.models.models import BoundingBox, OCRResult, ExtractedItem

def draw_boxes_on_image(image: Image.Image, items: List[Union[OCRResult, ExtractedItem]], color: str = "red", width: int = 3) -> Image.Image:
    """
    在给定的图片上绘制边界框 (Bounding Boxes)。
    主要用于可视化 OCR 识别结果或信息提取结果，方便用户直观地看到文本在原图中的位置。
    
    Args:
        image: 原始图片对象 (PIL.Image.Image)。
        items: 需要绘制的对象列表。这些对象可以是 OCRResult (原始识别结果)
               或 ExtractedItem (提取出的结构化字段)，只要它们包含 `box` 属性即可。
        color: 边框的颜色，默认为红色 ("red")。支持 PIL 识别的颜色名称或 RGB 元组。
        width: 边框的线条宽度 (像素)，默认为 3。
        
    Returns:
        Image.Image: 绘制了边框后的新图片对象。原始图片不会被修改。
    """
    # 创建原始图片的副本，确保绘制操作不会污染原图数据
    draw_image = image.copy()
    # 创建一个 ImageDraw 对象，用于在副本图片上进行 2D 图形绘制
    draw = ImageDraw.Draw(draw_image)
    
    # 遍历需要绘制的项目列表
    for item in items:
        # 获取对象的边界框属性
        box = item.box
        # 只有当 box 存在且不为 None 时才进行绘制
        if box:
            # 使用 ImageDraw.rectangle 绘制矩形框
            # 参数格式要求为 [左上角X, 左上角Y, 右下角X, 右下角Y]
            draw.rectangle(
                [box.x_min, box.y_min, box.x_max, box.y_max],
                outline=color, # 设置边框颜色
                width=width    # 设置边框宽度
            )
            
    # 返回绘制完成的图片副本
    return draw_image