import json
import re
from typing import List, Optional
from openai import OpenAI
from app.models.models import PageResult, ExtractedItem, BoundingBox, FieldRule, LlmConfig

def find_text_box(text_to_find: str, pages: List[PageResult]) -> Optional[BoundingBox]:
    """
    在 OCR 结果中查找特定文本片段的位置。
    
    Args:
        text_to_find: 需要查找的文本字符串。
        pages: 包含所有页面 OCR 结果的列表。
        
    Returns:
        如果找到匹配项，返回第一个匹配项的边界框 (BoundingBox)；否则返回 None。
    """
    if not text_to_find:
        return None
    # 遍历所有页面
    for page in pages:
        # 遍历页面中的所有 OCR 识别块
        for ocr_result in page.ocr_results:
            # 简单的子串匹配：如果目标文本包含在识别块的文本中
            if text_to_find in ocr_result.text:
                return ocr_result.box
    return None

def validate_value(value: str, rule: FieldRule) -> (bool, Optional[str]):
    """
    根据用户定义的规则校验提取出的值。
    
    Args:
        value: LLM 提取出的字段值。
        rule: 该字段对应的提取规则 (包含类型、长度、正则等限制)。
        
    Returns:
        一个元组 (is_valid, error_message)。
        如果校验通过，返回 (True, None)。
        如果校验失败，返回 (False, 错误原因字符串)。
    """
    # 如果提取值为 None，通常认为校验通过 (或者可以根据业务需求改为必填校验)
    if value is None:
        return True, None

    # 1. 长度校验
    if rule.max_length and len(str(value)) > rule.max_length:
        return False, f"长度超过限制 (最大 {rule.max_length})"
    
    # 2. 正则表达式校验
    if rule.regex:
        # 使用 re.match 进行正则匹配 (从字符串开头匹配)
        if not re.match(rule.regex, str(value)):
            return False, f"不符合正则表达式 '{rule.regex}'"
            
    # 3. 类型校验 (这里提供了一个简化的数字类型校验实现)
    if rule.field_type == "number":
        try:
            # 尝试将字符串转换为浮点数，先移除可能存在的千位分隔符
            float(str(value).replace(",", ""))
        except (ValueError, AttributeError):
            return False, "不是一个有效的数字"

    # 所有校验通过
    return True, None

def parse_fields_from_prompt(prompt: str, llm_config: Optional[LlmConfig] = None) -> List[FieldRule]:
    """
    使用大语言模型 (LLM) 从用户的自然语言描述中解析出结构化的字段提取规则列表。
    
    Args:
        prompt: 用户输入的自然语言描述 (例如："帮我提取合同里的甲方名称和总金额")。
        llm_config: LLM 服务的配置信息。
        
    Returns:
        解析出的 FieldRule 对象列表。
    """
    # 如果提示词为空，直接返回空列表
    if not prompt or not prompt.strip():
        return []
        
    system_prompt = """你是一个专业的文档字段分析专家。
用户会输入一段自然语言描述，说明他们想从文档中提取哪些信息。
请你分析用户的描述，提取出具体的字段列表，并以JSON数组的格式返回。

返回格式示例：
[
  {
    "key": "甲方名称",
    "description": "合同的签署方",
    "field_type": "string"
  },
  {
    "key": "合同金额",
    "description": "合同的总金额",
    "field_type": "string"
  }
]

注意：
1. key 必须是简短的字段名。
2. field_type 尽量使用 string, number, date 等基础类型。
3. 必须返回合法的 JSON 数组，不要包含任何其他文字或 markdown 标记。
"""
    
    if llm_config:
        try:
            # 初始化 OpenAI 客户端 (兼容支持 OpenAI API 格式的其他模型，如 DeepSeek)
            client = OpenAI(
                api_key=llm_config.api_key,
                base_url=llm_config.base_url if llm_config.base_url else None
            )
            
            # 调用 LLM 的 Chat Completion 接口
            response = client.chat.completions.create(
                model=llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3, # 较低的温度以保证输出的结构稳定性
                response_format={"type": "json_object"} # 提示模型返回 JSON 格式 (注意：某些模型可能不支持直接返回 JSON 数组，所以系统提示词中要求返回对象或数组)
            )
            llm_output = response.choices[0].message.content
            
            # 清理 LLM 输出中可能包含的 Markdown 代码块标记 (```json ... ```)
            cleaned_output = llm_output.strip()
            if cleaned_output.startswith("```json"):
                cleaned_output = cleaned_output[7:]
            if cleaned_output.startswith("```"):
                cleaned_output = cleaned_output[3:]
            if cleaned_output.endswith("```"):
                cleaned_output = cleaned_output[:-3]
                
            # 尝试将清理后的字符串解析为 JSON 对象
            parsed_data = json.loads(cleaned_output)
            
            # 兼容性处理：如果模型返回的是一个包含数组的字典（例如 {"fields": [...]}），则提取出其中的数组
            if isinstance(parsed_data, dict):
                for k, v in parsed_data.items():
                    if isinstance(v, list):
                        parsed_data = v
                        break
            
            # 如果最终得到的是一个列表，则将其转换为 FieldRule 对象列表
            if isinstance(parsed_data, list):
                rules = []
                for item in parsed_data:
                    if isinstance(item, dict) and "key" in item:
                        rules.append(FieldRule(
                            key=item["key"],
                            description=item.get("description"),
                            field_type=item.get("field_type", "string")
                        ))
                return rules
            else:
                print(f"ERROR: LLM返回的不是数组格式: {llm_output}")
                return []
                
        except Exception as e:
            print(f"ERROR: 解析字段失败: {e}")
            raise ValueError(f"大模型API调用失败，无法解析字段。详细错误: {str(e)}")
    else:
        # 简单的本地回退逻辑（如果未配置 LLM，则返回一个提示性的错误字段）
        return [FieldRule(key="解析失败", description="未配置LLM，无法智能解析")]

def extract_with_llm(pages: List[PageResult], rules: List[FieldRule], llm_config: Optional[LlmConfig] = None) -> List[ExtractedItem]:
    """
    核心提取逻辑：使用大语言模型 (LLM) 从 OCR 识别结果中提取结构化信息，并进行后处理校验。
    
    Args:
        pages: OCR 识别出的页面结果列表。
        rules: 用户定义的字段提取规则列表。
        llm_config: LLM 服务的配置信息。
        
    Returns:
        提取出的结构化数据项列表 (ExtractedItem)。
    """
    
    # 1. 文本预处理：将所有页面的 OCR 文本块拼接成一个完整的长字符串，作为 LLM 的上下文输入
    full_text = "\n".join([ocr.text for page in pages for ocr in page.ocr_results])
    
    # 2. 构建 Prompt：将用户定义的提取规则转换为 LLM 易于理解的文本描述
    rules_description = []
    for rule in rules:
        desc = f'- "{rule.key}"'
        if rule.description:
            desc += f" (描述: {rule.description})"
        if rule.field_type:
            desc += f" (类型: {rule.field_type})"
        rules_description.append(desc)
    
    system_prompt = "你是一个专业的文档信息提取助手。请从用户提供的OCR文本中，精准提取出指定的字段信息。"
    user_prompt = f"""
    OCR文本内容如下:
    ---
    {full_text}
    ---
    请根据以下规则提取字段:
    {chr(10).join(rules_description)}
    
    请严格按照以下JSON格式返回结果，不要添加任何额外的解释或说明（如markdown代码块标记）。
    如果某个字段在文本中不存在，请将值设为 null。
    返回格式 (key必须与请求的key完全一致):
    {{
      "key1": "value1",
      "key2": "value2"
    }}
    """
    
    llm_output = ""

    # 3. 调用 LLM 进行信息提取
    if llm_config:
        try:
            print(f"DEBUG: 使用真实LLM调用 ({llm_config.provider})...")
            # 初始化 OpenAI 客户端
            client = OpenAI(
                api_key=llm_config.api_key,
                base_url=llm_config.base_url if llm_config.base_url else None
            )
            
            # 发送请求给 LLM
            response = client.chat.completions.create(
                model=llm_config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1, # 使用极低的温度 (0.1) 以保证提取结果的确定性和准确性，减少幻觉
                response_format={"type": "json_object"} # 强制要求模型返回 JSON 对象格式
            )
            llm_output = response.choices[0].message.content
            print(f"DEBUG: LLM返回: {llm_output}")
            
        except Exception as e:
            print(f"ERROR: LLM调用失败: {e}")
            raise ValueError(f"大模型API调用失败，请检查 config.py 中的 API Key 和网络配置。详细错误: {str(e)}")
    else:
        # --- 模拟 LLM 返回 (仅用于开发测试，当未提供 LLM 配置时触发) ---
        print("DEBUG: 未提供LLM配置，使用模拟数据...")
        mock_responses = {
            "甲方名称": "示例甲方有限公司",
            "合同金额": "1,000,000.00元",
            "身份证号": "11010119900307123X",
            "姓名": "张三"
        }
        # 根据请求的规则生成模拟的 JSON 响应
        llm_output_dict = {rule.key: mock_responses.get(rule.key) for rule in rules}
        llm_output = json.dumps(llm_output_dict, ensure_ascii=False)
        # --- 模拟结束 ---

    # 4. 解析 LLM 的返回结果
    try:
        # 清理 LLM 输出中可能包含的 Markdown 代码块标记
        cleaned_output = llm_output.strip()
        if cleaned_output.startswith("```json"):
            cleaned_output = cleaned_output[7:]
        if cleaned_output.startswith("```"):
            cleaned_output = cleaned_output[3:]
        if cleaned_output.endswith("```"):
            cleaned_output = cleaned_output[:-3]
            
        # 将清理后的字符串解析为 Python 字典
        extracted_data_dict = json.loads(cleaned_output)
    except json.JSONDecodeError:
        print(f"ERROR: LLM未能返回有效的JSON格式: {llm_output}")
        return []

    # 5. 后处理：校验结果并查找坐标
    extracted_items: List[ExtractedItem] = []
    for rule in rules:
        # 获取 LLM 提取出的对应字段的值
        value = extracted_data_dict.get(rule.key)
        
        # 5.1 根据规则校验提取出的值 (类型、长度、正则等)
        is_valid, validation_error = validate_value(value, rule)
        
        # 5.2 尝试在原始 OCR 结果中查找该提取值的坐标位置 (用于前端高亮显示)
        original_text = str(value) if value is not None else None
        box = find_text_box(original_text, pages) if original_text else None
        
        # 组装最终的提取项对象
        item = ExtractedItem(
            key=rule.key,
            value=value,
            original_text=original_text,
            box=box,
            is_valid=is_valid,
            validation_error=validation_error
        )
        extracted_items.append(item)
            
    return extracted_items