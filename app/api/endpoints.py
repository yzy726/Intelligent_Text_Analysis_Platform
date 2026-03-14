from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Body
from fastapi.responses import StreamingResponse
from typing import Optional, List, Union
from PIL import Image
import io

from app.models.models import (
    OcrResponse, ExtractionRequest, ExtractionResponse,
    ParsePromptRequest, ParsePromptResponse
)
from app.utils.pdf_processor import convert_pdf_to_images
from app.services.ocr.factory import get_ocr_service
from app.services.extraction_service import extract_with_llm, parse_fields_from_prompt
from app.utils.visualizer import draw_boxes_on_image
from app.config import settings

# 创建 API 路由器实例，用于组织和注册路由
router = APIRouter()

@router.post("/ocr", response_model=Union[OcrResponse, bytes], summary="步骤1: OCR识别", tags=["OCR识别"])
async def perform_ocr(
    file: UploadFile = File(...), # 接收上传的文件 (PDF 或图片)
    ocr_service: str = Form("local"), # 指定使用的 OCR 服务类型 (如 'local', 'baidu', 'paddle')
    api_key: Optional[str] = Form(None), # 可选的 API Key (用于云端 OCR 服务)
    api_secret: Optional[str] = Form(None), # 可选的 API Secret (用于云端 OCR 服务)
    return_image: bool = Form(False, description="是否返回标注了红框的图片（仅用于测试）") # 是否返回可视化结果
):
    """
    接收文档（PDF或图片），仅执行OCR，并返回原始识别结果。
    这是信息提取的第一步。
    """
    # 打印调试信息，帮助定位 400 错误原因 (文件类型或服务类型错误)
    print(f"DEBUG: 接收到文件: {file.filename}, Content-Type: {file.content_type}")
    print(f"DEBUG: OCR服务: {ocr_service}")

    # 宽松的文件类型检查：如果 Content-Type 识别不准，则检查文件后缀名
    # 判断是否为 PDF 文件
    is_pdf = file.content_type == "application/pdf" or file.filename.lower().endswith(".pdf")
    # 判断是否为支持的图片格式
    is_image = file.content_type.startswith("image/") or file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"))

    # 如果既不是 PDF 也不是图片，则抛出 400 错误
    if not is_pdf and not is_image:
        print(f"DEBUG: 文件类型校验失败")
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}。请上传PDF或图片文件。")

    # 读取文件内容到内存
    contents = await file.read()

    # 存储解析后的图像列表 (PDF 可能有多页，图片通常只有一页)
    images: List[Image.Image] = []
    if is_pdf:
        try:
            # 将 PDF 转换为图像列表
            images = convert_pdf_to_images(contents)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF处理失败: {e}")
    elif is_image:
        try:
            # 将图片字节流转换为 PIL Image 对象
            image = Image.open(io.BytesIO(contents))
            images.append(image)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"图片文件读取失败: {e}")

    # 确保至少提取到了一页图像
    if not images:
        raise HTTPException(status_code=500, detail="未能从文件中提取任何图像页面。")

    try:
        print("DEBUG: 正在获取OCR服务实例...")
        # 根据请求参数获取对应的 OCR 服务实例 (工厂模式)
        ocr_service_instance = get_ocr_service(ocr_service)
        print("DEBUG: OCR服务实例获取成功，开始识别...")
        
        # 如果前端没有传 api_key 和 api_secret，则尝试从后端配置中读取 (主要针对百度 OCR)
        if ocr_service == "baidu":
            if not api_key:
                api_key = settings.BAIDU_OCR_API_KEY
            if not api_secret:
                api_secret = settings.BAIDU_OCR_SECRET_KEY
                
        # 调用 OCR 服务的 recognize 方法进行识别，返回每页的识别结果列表
        ocr_pages_results = ocr_service_instance.recognize(images, api_key=api_key, api_secret=api_secret)
        print("DEBUG: 识别完成")
    except ValueError as e:
        # 捕获参数错误 (如不支持的 OCR 服务类型)
        print(f"DEBUG: 捕获到 ValueError: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 捕获其他 OCR 处理过程中的异常
        print(f"DEBUG: 捕获到其他异常: {e}")
        # 打印完整的错误堆栈到终端，方便调试
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"OCR处理失败: {e}")

    # 如果请求要求返回图片 (通常用于调试或可视化)
    if return_image and images:
        # 如果请求返回图片，则在第一页上绘制红框并返回
        # 注意：这里只返回第一页作为示例，实际应用中可能需要处理多页
        first_page_image = images[0]
        first_page_results = ocr_pages_results[0].ocr_results
        
        # 在图像上绘制 OCR 识别出的文本框
        annotated_image = draw_boxes_on_image(first_page_image, first_page_results)
        
        # 将标注后的图像转换为字节流
        img_byte_arr = io.BytesIO()
        annotated_image.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0) # 重置指针到开头
        
        # 返回图像流响应
        return StreamingResponse(img_byte_arr, media_type="image/jpeg")

    # 正常情况下，返回包含 OCR 结果的 JSON 响应
    return OcrResponse(
        filename=file.filename,
        ocr_service=ocr_service,
        pages=ocr_pages_results
    )

@router.post("/parse_prompt", response_model=ParsePromptResponse, summary="辅助: 自然语言解析字段", tags=["信息提取"])
async def parse_prompt(
    request: ParsePromptRequest = Body(...) # 接收包含自然语言提示词的请求体
):
    """
    接收用户的自然语言描述，调用大模型解析出结构化的字段列表。
    用于辅助用户快速生成提取规则。
    """
    # 如果请求中未提供 LLM 配置，则使用系统默认配置
    if not request.llm_config:
        from app.models.models import LlmConfig
        request.llm_config = LlmConfig(
            provider=settings.LLM_PROVIDER,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL
        )
        
    try:
        # 调用服务层函数，使用 LLM 解析提示词并生成字段规则列表
        fields = parse_fields_from_prompt(request.prompt, request.llm_config)
        return ParsePromptResponse(fields=fields)
    except Exception as e:
        # 捕获解析过程中的异常并返回 500 错误
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/extract_fields", response_model=ExtractionResponse, summary="步骤2: 按规则提取字段", tags=["信息提取"])
async def extract_fields(
    request: ExtractionRequest = Body(...) # 接收包含 OCR 结果和提取规则的请求体
):
    """
    接收OCR结果和用户定义的提取规则，调用大模型进行信息提取和校验。
    这是信息提取的第二步。
    """
    # 如果前端没有传 llm_config，则使用后端的默认配置
    if not request.llm_config:
        from app.models.models import LlmConfig
        request.llm_config = LlmConfig(
            provider=settings.LLM_PROVIDER,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL
        )

    # 调用大模型服务，传入OCR结果、规则以及LLM配置进行信息提取
    try:
        extracted_data = extract_with_llm(request.pages, request.rules, request.llm_config)
    except Exception as e:
        # 捕获提取过程中的异常并返回 500 错误
        raise HTTPException(status_code=500, detail=str(e))
    
    # 返回提取结果
    return ExtractionResponse(extracted_data=extracted_data)

@router.post("/generate_pdf", summary="工具: 生成双层PDF", tags=["辅助工具"])
async def generate_pdf_endpoint(
    ocr_data: str = Form(..., description="JSON字符串，包含OCR识别结果")
):
    """
    接收OCR结果，生成包含可复制文本的PDF文件 (双层 PDF)。
    不再需要上传原图，直接根据OCR结果中的尺寸创建页面，并将文本绘制在对应位置。
    """
    import json
    import os
    import io
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    
    try:
        # 解析传入的 JSON 格式的 OCR 数据
        data = json.loads(ocr_data)
        
        # 动态计算项目根目录，以确保无论从哪里运行脚本都能找到字体文件
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent

        # 使用项目根目录构建字体的绝对路径
        font_cn_path = os.path.join(project_root, 'fonts', 'AlibabaPuHuiTi-Regular.ttf')
        font_en_path = os.path.join(project_root, 'fonts', 'Roboto-Regular.ttf')
        
        if not os.path.exists(font_cn_path):
            raise FileNotFoundError(f"找不到中文字体文件: {font_cn_path}")
        if not os.path.exists(font_en_path):
            raise FileNotFoundError(f"找不到英文字体文件: {font_en_path}")

        # 注册字体（只需要注册一次）
        pdfmetrics.registerFont(TTFont('AlibabaPuHuiTi', font_cn_path))
        pdfmetrics.registerFont(TTFont('Roboto', font_en_path))

        # 创建一个内存中的字节流用于保存 PDF
        pdf_buffer = io.BytesIO()
        
        # 遍历每一页的 OCR 数据
        pages_data = data.get('pages', [])
        if not pages_data:
            raise ValueError("没有找到页面数据")
            
        # 初始化 canvas，使用第一页的尺寸
        first_page_width = pages_data[0].get('image_width', 800)
        first_page_height = pages_data[0].get('image_height', 1000)
        c = canvas.Canvas(pdf_buffer, pagesize=(first_page_width, first_page_height))
        
        # 必须在创建 canvas 后立即设置一个默认字体，否则在调用 setPageSize 等方法时可能会报错
        c.setFont('AlibabaPuHuiTi', 12)

        for page_idx, page_data in enumerate(pages_data):
            if page_idx > 0:
                # 如果不是第一页，则创建新页面并设置尺寸
                width = page_data.get('image_width', 800)
                height = page_data.get('image_height', 1000)
                c.setPageSize((width, height))
                c.showPage()
            else:
                width = first_page_width
                height = first_page_height

            # 兼容不同的 OCR 数据结构 (统一转换为标准格式)
            ocr_results = []
            
            # 兼容百度 OCR 的原始结构
            if 'words_result' in page_data:
                for item in page_data.get('words_result', []):
                    loc = item.get('location', {})
                    ocr_results.append({
                        'text': item.get('words', ''),
                        'box': {
                            'x_min': loc.get('left', 0),
                            'y_min': loc.get('top', 0),
                            'x_max': loc.get('left', 0) + loc.get('width', 0),
                            'y_max': loc.get('top', 0) + loc.get('height', 0)
                        }
                    })
            
            # 兼容 PaddleOCR 的原始结构
            if 'rec_texts' in page_data and 'rec_boxes' in page_data:
                texts = page_data.get('rec_texts', [])
                boxes = page_data.get('rec_boxes', [])
                for text, box in zip(texts, boxes):
                    if len(box) == 4:
                        ocr_results.append({
                            'text': text,
                            'box': {
                                'x_min': box[0],
                                'y_min': box[1],
                                'x_max': box[2],
                                'y_max': box[3]
                            }
                        })
                    elif len(box) == 8 or (len(box) == 4 and isinstance(box[0], list)):
                        if isinstance(box[0], list):
                            xs = [p[0] for p in box]
                            ys = [p[1] for p in box]
                        else:
                            xs = box[0::2]
                            ys = box[1::2]
                        ocr_results.append({
                            'text': text,
                            'box': {
                                'x_min': min(xs),
                                'y_min': min(ys),
                                'x_max': max(xs),
                                'y_max': max(ys)
                            }
                        })
            
            # 如果上面都没有找到，尝试从 page_data.get('ocr_results') 获取
            if not ocr_results and 'ocr_results' in page_data:
                ocr_results = page_data.get('ocr_results', [])

            # 遍历标准化后的 OCR 结果，将文本绘制到 PDF 页面中
            for res in ocr_results:
                text = res.get('text', '')
                if not text.strip():
                    continue
                    
                box = res.get('box', {})
                if isinstance(box, dict):
                    x0, y0, x1, y1 = box.get('x_min', 0), box.get('y_min', 0), box.get('x_max', 0), box.get('y_max', 0)
                else:
                    x0, y0, x1, y1 = getattr(box, 'x_min', 0), getattr(box, 'y_min', 0), getattr(box, 'x_max', 0), getattr(box, 'y_max', 0)
                
                try:
                    # 根据内容智能选择字体，并支持中英文混合渲染
                    box_width = x1 - x0
                    box_height = y1 - y0
                    
                    # reportlab 的坐标系原点在左下角，而图像/OCR坐标系原点在左上角
                    # 需要进行 Y 轴坐标转换
                    pdf_y = height - y1
                    
                    # 设置字体和颜色 (黑色，完全不透明，保证可见)
                    c.setFillColorRGB(0, 0, 0)
                    
                    if box_height > box_width * 1.5 and len(text) > 1:  # 竖向文字
                        fontsize = max(4, box_width * 0.8)
                        char_height = box_height / len(text)
                        for i, char in enumerate(text):
                            # 逐字判断使用何种字体
                            font_name = 'AlibabaPuHuiTi' if '\u4e00' <= char <= '\u9fff' else 'Roboto'
                            c.setFont(font_name, fontsize)
                            # 竖排文字逐个字符绘制，注意 Y 轴转换
                            char_y = height - (y0 + (i + 0.8) * char_height)
                            c.drawString(x0 + box_width * 0.1, char_y, char)
                    else:  # 横向文字
                        import re
                        fontsize = max(4, box_height * 0.8)
                        
                        # 将文本拆分为中文字段和非中文字段的列表
                        text_segments = [s for s in re.split(r'([\u4e00-\u9fa5]+)', text) if s]
                        
                        current_x = x0
                        pdf_y_baseline = pdf_y + box_height * 0.2

                        for segment in text_segments:
                            # 判断分段是中文还是英文/数字，选择相应字体
                            font_name = 'AlibabaPuHuiTi' if re.match(r'[\u4e00-\u9fa5]+', segment) else 'Roboto'
                            c.setFont(font_name, fontsize)
                            
                            # 绘制分段文本
                            c.drawString(current_x, pdf_y_baseline, segment)
                            # 更新下一个分段的起始 X 坐标
                            current_x += c.stringWidth(segment, font_name, fontsize)
                        
                except Exception as e:
                    print(f"插入文本 '{text}' 失败: {e}")
                    
        # 保存并关闭 canvas
        c.save()
        
        # 获取生成的 PDF 字节流
        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()
        
        # 返回 PDF 文件流响应，设置 Content-Disposition 触发浏览器下载
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=generated.pdf"}
        )
        
    except Exception as e:
        # 捕获生成过程中的异常并返回 500 错误
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"生成PDF失败: {e}")
    
@router.post("/visualize", summary="工具: 可视化标注", tags=["辅助工具"])
async def visualize_results(
    file: UploadFile = File(...), # 接收上传的原始图片
    data: str = Form(..., description="JSON字符串，包含要绘制的 items (OCRResult 或 ExtractedItem 列表)") # 接收包含坐标数据的 JSON 字符串
):
    """
    辅助接口：接收图片和包含坐标的数据，在图片上绘制红框并返回。
    用于前端展示 OCR 识别结果或信息提取结果的位置。
    """
    import json
    from app.models.models import ExtractedItem, BoundingBox
    
    try:
        # 读取上传的图片文件
        image = Image.open(io.BytesIO(await file.read()))
        # 解析传入的 JSON 数据列表
        data_list = json.loads(data)
        
        items = []
        # 遍历数据列表，提取坐标信息
        for item in data_list:
            # 尝试解析为 ExtractedItem 或 OCRResult
            # 这里采用简化处理，只要字典中包含 "box" 字段即可
            if "box" in item:
                box_data = item["box"]
                if box_data: # 确保 box 数据不为空
                    # 将字典转换为 BoundingBox 模型对象
                    box = BoundingBox(**box_data)
                    # 创建一个包含 box 属性的临时对象，以适配 draw_boxes_on_image 函数的参数要求
                    class TempItem:
                        def __init__(self, box): self.box = box
                    items.append(TempItem(box))
                
        # 调用可视化工具函数，在图片上绘制边界框
        annotated_image = draw_boxes_on_image(image, items)
        
        # 将标注后的图片转换为 JPEG 格式的字节流
        img_byte_arr = io.BytesIO()
        annotated_image.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0) # 重置指针
        
        # 返回图片流响应
        return StreamingResponse(img_byte_arr, media_type="image/jpeg")
        
    except Exception as e:
        # 捕获处理过程中的异常并返回 400 错误
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"可视化失败: {e}")