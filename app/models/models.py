from pydantic import BaseModel, Field
from typing import List, Any, Optional

# --- 基础模型 (OCR结果) ---

class BoundingBox(BaseModel):
    """
    定义一个边界框，表示文字在图片中的位置。
    坐标原点 (0,0) 通常在图片左上角。
    """
    x_min: float # 左上角 X 坐标
    y_min: float # 左上角 Y 坐标
    x_max: float # 右下角 X 坐标
    y_max: float # 右下角 Y 坐标

class OCRResult(BaseModel):
    """单个OCR识别结果的结构。"""
    text: str # 识别出的文本内容
    box: BoundingBox # 文本所在的边界框
    confidence: float = 0.0 # 识别置信度 (0.0 - 1.0)

class PageResult(BaseModel):
    """单个页面的所有OCR结果。"""
    page_number: int # 页码 (从 1 开始)
    ocr_results: List[OCRResult] # 该页包含的所有 OCR 识别结果列表
    image_width: int # 原始图像宽度 (像素)
    image_height: int # 原始图像高度 (像素)

# --- API: /ocr (纯OCR识别) ---

class OcrResponse(BaseModel):
    """纯OCR接口的响应体。"""
    filename: str # 处理的文件名
    ocr_service: str # 使用的 OCR 服务名称
    pages: List[PageResult] # 每一页的识别结果列表

# --- API: /extract_fields (按规则提取) ---

class FieldRule(BaseModel):
    """用户自定义的单个字段提取规则。"""
    key: str = Field(..., description="要提取的字段名, e.g., '甲方名称'")
    description: Optional[str] = Field(None, description="对该字段的详细描述，帮助 LLM 更好地理解提取意图, e.g., '合同的签署方'")
    field_type: str = Field("string", description="期望的字段数据类型, e.g., 'string', 'number', 'date'")
    max_length: Optional[int] = Field(None, description="提取结果的最大长度限制")
    regex: Optional[str] = Field(None, description="用于校验提取结果格式的正则表达式")

class LlmConfig(BaseModel):
    """LLM (大语言模型) 配置信息。"""
    provider: str = Field("openai", description="提供商标识，如 'openai', 'deepseek', 'aliyun'")
    api_key: str = Field(..., description="调用 LLM 服务的 API Key")
    base_url: Optional[str] = Field(None, description="API Base URL (如果不是默认的官方地址，例如使用代理或兼容接口)")
    model: str = Field(..., description="使用的具体模型名称，如 'gpt-4', 'deepseek-chat', 'qwen-turbo'")

class ExtractionRequest(BaseModel):
    """字段提取接口的请求体。"""
    pages: List[PageResult] = Field(..., description="从 /ocr 接口获取的原始 OCR 识别结果")
    rules: List[FieldRule] = Field(..., description="用户定义的字段提取规则列表")
    llm_config: Optional[LlmConfig] = Field(None, description="LLM配置信息。如果不传，将使用后端默认配置。")
    return_image: bool = Field(False, description="是否返回标注了提取结果的图片（仅用于测试）。注意：如果设为True，响应将是二进制图片流，而不是JSON。")

class ParsePromptRequest(BaseModel):
    """自然语言解析字段请求体"""
    prompt: str = Field(..., description="用户输入的自然语言描述，说明需要提取哪些信息")
    llm_config: Optional[LlmConfig] = Field(None, description="LLM配置信息")

class ParsePromptResponse(BaseModel):
    """自然语言解析字段响应体"""
    fields: List[FieldRule] # 解析后生成的结构化字段规则列表

class ExtractedItem(BaseModel):
    """大模型提取出的单个结构化字段结果。"""
    key: str # 提取的字段名 (对应 FieldRule 中的 key)
    value: Any # 提取出的具体值
    original_text: Optional[str] = None # 提取值在原文中对应的原始文本片段
    box: Optional[BoundingBox] = None # 提取值在原图中的位置坐标
    is_valid: bool = True # 校验结果 (是否符合规则中定义的类型、正则等)
    validation_error: Optional[str] = None # 如果校验失败，记录失败原因

class ExtractionResponse(BaseModel):
    """字段提取接口的响应体。"""
    extracted_data: List[ExtractedItem] # 提取出的所有字段结果列表

# --- API: /process_document (一站式处理) ---

class ProcessConfig(BaseModel):
    """一站式处理接口的配置部分，作为JSON字符串在表单中传递。"""
    rules: List[FieldRule] = Field(..., description="用户定义的字段提取规则列表")
    llm_config: Optional[LlmConfig] = Field(None, description="LLM配置信息。")
    return_image: bool = Field(True, description="是否返回标注了提取结果的图片。")

class ProcessResponse(BaseModel):
    """一站式处理接口的响应体。"""
    filename: str # 处理的文件名
    extracted_data: List[ExtractedItem] # 提取出的结构化数据
    annotated_image_base64: Optional[str] = Field(None, description="标注了提取结果的图片的 Base64 编码字符串。")
    ocr_pages: List[PageResult] = Field(..., description="原始的 OCR 识别结果，可用于前端调试或高级渲染。")