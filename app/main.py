import os
# 解决 OpenMP 库冲突问题 (OMP: Error #15)，通常在同时使用多个依赖 OpenMP 的库时发生
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 强制禁用 MKLDNN 加速，解决部分 CPU 环境下的底层兼容性错误 (主要针对 PaddlePaddle)
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0" # 尝试禁用 PIR 模式，回退到旧版执行器，以提高兼容性

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

# 定义 OpenAPI 文档的标签元数据，用于对 API 接口进行分类和描述
tags_metadata = [
    {
        "name": "OCR识别",
        "description": "第一步：上传文档（PDF或图片），获取包含坐标的原始文字识别结果。",
    },
    {
        "name": "信息提取",
        "description": "第二步：基于OCR结果和自定义规则，智能提取结构化字段并进行校验。",
    },
]

# 初始化 FastAPI 应用实例
app = FastAPI(
    title="智能文档信息提取平台 API", # API 文档标题
    description="""
    欢迎使用智能文档信息提取平台。本平台提供两步式的信息提取服务：
    
    1. **OCR识别**: 将非结构化文档转换为计算机可读的文字和坐标。
    2. **信息提取**: 根据您定义的规则（字段名、类型、正则等），从OCR结果中精准提取信息。
    """, # API 文档描述
    version="2.0.0", # API 版本号
    openapi_tags=tags_metadata # 关联标签元数据
)

# 配置 CORS (跨域资源共享) 中间件，允许前端应用跨域访问 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源的跨域请求。注意：生产环境中应配置为前端应用的实际地址以提高安全性
    allow_credentials=False, # 是否允许携带凭证 (如 cookies)。当 allow_origins 为 ["*"] 时，必须为 False
    allow_methods=["*"], # 允许所有 HTTP 方法 (GET, POST, PUT, DELETE 等)
    allow_headers=["*"], # 允许所有 HTTP 请求头
)

# 引入并注册 API 路由模块
from app.api import endpoints
# 将 endpoints 模块中的路由挂载到 /api/v1 前缀下
app.include_router(endpoints.router, prefix="/api/v1")

# 定义根路径 ("/") 的 GET 请求处理函数
# include_in_schema=False 表示该接口不在 OpenAPI 文档中显示
@app.get("/", include_in_schema=False)
async def root():
    """
    根路径重定向：当用户访问根路径时，自动重定向到前端主页面 (zgwxt.html)。
    """
    return RedirectResponse(url="/zgwxt.html")

# 挂载静态文件目录，用于提供前端页面和资源文件 (HTML, CSS, JS, 图片等)
# 注意：这个挂载点应该在所有 API 路由和路径操作之后定义，以确保 API 路由被优先匹配。
# 否则，如果存在与 API 路径同名的静态文件，可能会导致 API 无法访问。
app.mount("/", StaticFiles(directory="frontend"), name="frontend")
