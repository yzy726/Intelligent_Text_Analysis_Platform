import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    应用程序配置类，继承自 pydantic_settings.BaseSettings。
    用于管理环境变量和默认配置。
    """
    # LLM (大语言模型) 配置
    LLM_PROVIDER: str = "deepseek" # LLM 提供商名称
    LLM_API_KEY: str = "sk-your-api-key"     # 请在此处填入你的 API Key 
    LLM_BASE_URL: str = "https://api.deepseek.com/v1" # LLM 服务的 Base URL，如果使用代理或其他兼容接口，请修改此处
    LLM_MODEL: str = "deepseek-chat" # 使用的 LLM 模型名称

    # OCR (光学字符识别) 配置 (如果需要使用百度 OCR 等云服务)
    BAIDU_OCR_API_KEY: str = "your-baidu-api-key"  # 请在此处填入你的Baidu API Key 
    BAIDU_OCR_SECRET_KEY: str = "your-baidu-secret-key"  # 请在此处填入你的 Baidu Secret Key


    class Config:
        """Pydantic 配置类，指定环境变量文件"""
        env_file = ".env" # 从 .env 文件加载环境变量
        env_file_encoding = 'utf-8' # 环境变量文件编码

# 实例化配置对象，供其他模块导入使用
settings = Settings()