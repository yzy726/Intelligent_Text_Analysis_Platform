import fitz  # PyMuPDF
import io
from PIL import Image
from typing import List

def convert_pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> List[Image.Image]:
    """
    将 PDF 文件的字节流转换为 PIL Image 对象列表。
    这是处理 PDF 文档进行 OCR 识别的第一步，因为大多数 OCR 引擎直接处理图像。

    Args:
        pdf_bytes: PDF 文件的二进制字节内容。
        dpi: 渲染图像的分辨率 (dots per inch)。
             默认值为 300，这是一个在图像清晰度和处理速度之间较好的平衡点。
             较高的 DPI 可以提高 OCR 的准确性，但会增加内存消耗和处理时间。

    Returns:
        List[Image.Image]: 一个包含每个页面渲染后 PIL.Image 对象的列表。
        
    Raises:
        Exception: 如果 PDF 解析或渲染过程中发生错误。
    """
    images = []
    try:
        # 使用 PyMuPDF (fitz) 从内存字节流中打开 PDF 文档
        # filetype="pdf" 明确指定文件类型
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # 遍历 PDF 的每一页
        for page_num in range(len(pdf_document)):
            # 加载指定页码的页面对象
            page = pdf_document.load_page(page_num)
            
            # 计算缩放比例以获得所需的 DPI
            # PDF 的标准默认 DPI 是 72
            zoom = dpi / 72
            # 创建一个缩放矩阵
            mat = fitz.Matrix(zoom, zoom)
            
            # 使用指定的缩放矩阵将 PDF 页面渲染为像素图 (pixmap)
            # 这一步将矢量图形和文本光栅化为位图
            pix = page.get_pixmap(matrix=mat)
            
            # 将 PyMuPDF 的 pixmap 对象转换为 Python Imaging Library (PIL) 的 Image 对象
            # "RGB" 模式表示彩色图像，pix.samples 包含了原始的像素数据
            # 修复乱码问题：如果 PDF 包含透明通道，需要使用 RGBA 模式，或者先转换为 RGB
            if pix.alpha:
                img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
                # 转换为 RGB，背景填充白色，避免 OCR 引擎处理透明通道时出现乱码或黑块
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3]) # 3 is the alpha channel
                img = background
            else:
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
            images.append(img)
            
        # 处理完毕后关闭文档，释放资源
        pdf_document.close()
    except Exception as e:
        # 捕获并打印异常信息，然后向上抛出以便调用者处理 (例如返回 500 错误)
        print(f"处理PDF时发生错误: {e}")
        raise
        
    return images
