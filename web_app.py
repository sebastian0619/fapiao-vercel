from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
from typing import List, Dict, Any
import shutil
from datetime import datetime
import zipfile
import re
import hashlib
import secrets
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from config_manager import config
from pdf_processor import process_special_pdf
from ofd_processor import process_ofd, extract_ofd_info_direct
from data_extractor import extract_information_from_pdf
import uvicorn
import threading
import io
import time

# 配置日志
# 创建一个内存日志处理器，用于存储最近的日志
class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=1000):
        super().__init__()
        self.capacity = capacity
        self.log_records = []
        self.lock = threading.Lock()
        # 添加一个初始日志记录
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        self.log_records.append({
            'timestamp': timestamp,
            'level': 'INFO',
            'message': '日志系统已初始化',
            'logger': 'system'
        })
        
    def emit(self, record):
        try:
            with self.lock:
                # 格式化日志记录
                message = self.format(record)
                timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                log_entry = {
                    'timestamp': timestamp,
                    'level': record.levelname,
                    'message': message,
                    'logger': record.name
                }
                
                # 添加日志记录，保持日志数量在容量范围内
                self.log_records.append(log_entry)
                if len(self.log_records) > self.capacity:
                    self.log_records = self.log_records[-self.capacity:]
        except Exception as e:
            print(f"日志记录错误: {str(e)}")
                
    def get_logs(self, limit=100, level=None):
        """获取最近的日志记录"""
        try:
            with self.lock:
                if level:
                    # 转为大写再进行比较
                    level_upper = level.upper()
                    filtered_logs = [log for log in self.log_records if log['level'] == level_upper]
                    return filtered_logs[-limit:] if filtered_logs else []
                return self.log_records[-limit:] if self.log_records else []
        except Exception as e:
            print(f"获取日志错误: {str(e)}")
            return []

# 创建内存日志处理器
memory_handler = MemoryLogHandler(capacity=1000)
memory_handler.setLevel(logging.DEBUG)
memory_handler.setFormatter(logging.Formatter('%(message)s'))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 将内存处理器添加到根日志记录器
root_logger = logging.getLogger()
root_logger.addHandler(memory_handler)

# 添加一些系统启动日志
logging.info("发票处理系统启动")
logging.info(f"运行环境: {'Vercel' if os.environ.get('VERCEL') == '1' else '本地'}")
logging.info(f"工作目录: {os.getcwd()}")
logging.info(f"临时目录: {tmp_dir}")
logging.info(f"上传目录: {uploads_dir}")
logging.info(f"下载目录: {downloads_dir}")

app = FastAPI(title="发票处理系统")

# 确保目录存在（Vercel中的临时目录）
tmp_dir = "/tmp"
uploads_dir = "/tmp/uploads"
downloads_dir = "/tmp/downloads"

os.makedirs(uploads_dir, exist_ok=True)
os.makedirs(downloads_dir, exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# 静态文件和模板配置
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """验证管理员密码"""
    # 从配置文件获取管理员密码的哈希值，如果不存在则使用默认密码 "admin"
    stored_password_hash = config.get("admin_password_hash", 
                                    hashlib.sha256("admin".encode()).hexdigest())
    
    # 计算提供的密码的哈希值
    provided_password_hash = hashlib.sha256(credentials.password.encode()).hexdigest()
    
    # 验证用户名和密码
    is_correct_username = secrets.compare_digest(credentials.username, "admin")
    is_correct_password = secrets.compare_digest(provided_password_hash, stored_password_hash)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """主页"""
    # 确保使用Web UI的配置
    config_data = config.get_all()
    config_data["rename_with_amount"] = config_data.get("webui_rename_with_amount", False)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": config_data
        }
    )

def create_zip_file(files_info):
    """创建包含处理后文件的ZIP包"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"processed_invoices_{timestamp}.zip"
    zip_path = os.path.join(downloads_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for info in files_info:
            if info["success"] and info.get("new_path"):
                # 将文件添加到ZIP中，使用新文件名作为ZIP中的名称
                zipf.write(
                    info["new_path"],
                    os.path.basename(info["new_path"])
                )
    
    return zip_path, zip_filename

@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """处理上传的文件并返回ZIP包下载链接"""
    results = []
    processed_files = []
    
    try:
        # 获取当前的配置状态
        rename_with_amount = config.get("webui_rename_with_amount", False)
        logging.info(f"当前配置: rename_with_amount={rename_with_amount}")
        
        # 暂时设置为False，确保提取金额但不包含在文件名中
        if not rename_with_amount:
            config.set("rename_with_amount", False)
        
        logging.info(f"接收到{len(files)}个文件上传请求")
        
        for file in files:
            try:
                # 保存上传的文件
                file_path = os.path.join(uploads_dir, file.filename)
                with open(file_path, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)
                
                logging.info(f"已保存文件: {file_path}, 大小: {len(content)} 字节")
                
                # 处理文件
                ext = os.path.splitext(file.filename)[1].lower()
                result = None
                amount = None
                
                try:
                    if ext == '.pdf':
                        logging.info(f"开始处理PDF文件: {file_path}")
                        # 直接从PDF提取发票号和金额
                        invoice_number, extracted_amount = extract_information_from_pdf(file_path)
                        logging.info(f"从PDF中提取到信息 - 发票号: {invoice_number}, 金额: {extracted_amount}")
                        
                        # 记录金额信息，无论是否用于重命名
                        amount = extracted_amount
                        
                        # 处理PDF文件
                        result = process_special_pdf(file_path)
                        logging.info(f"PDF处理结果: {result}")
                        
                        # 如果处理成功但没有金额信息，尝试从文件名获取
                        if result and not amount:
                            try:
                                amount_match = re.search(r'\[¥(\d+\.\d{2})\]', os.path.basename(result))
                                if amount_match:
                                    amount = amount_match.group(1)
                                    logging.info(f"从文件名提取到金额: {amount}")
                            except Exception as e:
                                logging.warning(f"从文件名提取金额失败: {e}")
                    elif ext == '.ofd':
                        logging.info(f"开始处理OFD文件: {file_path}")
                        
                        # 先尝试直接从OFD文件提取信息
                        ofd_info = extract_ofd_info_direct(file_path)
                        if ofd_info.get('amount'):
                            amount = ofd_info.get('amount')
                            logging.info(f"从OFD文件直接提取到金额: {amount}")
                        
                        # 处理OFD文件
                        result = process_ofd(file_path, "", False)
                        logging.info(f"OFD处理结果: {result}")
                        
                        # 如果处理成功但没有金额信息，尝试从文件名获取
                        if result and not amount:
                            try:
                                amount_match = re.search(r'\[¥(\d+\.\d{2})\]', os.path.basename(result))
                                if amount_match:
                                    amount = amount_match.group(1)
                                    logging.info(f"从文件名提取到金额: {amount}")
                            except Exception as e:
                                logging.warning(f"从文件名提取金额失败: {e}")
                    else:
                        logging.warning(f"不支持的文件类型: {ext}")
                except Exception as file_process_error:
                    logging.error(f"处理文件时出错: {file_process_error}", exc_info=True)
                    result = None
                
                # 准备结果
                success = result is not None
                new_name = os.path.basename(result) if success else None
                
                result_item = {
                    "filename": file.filename,
                    "success": success,
                    "amount": amount,
                    "new_name": new_name,
                    "new_path": result if success else None
                }
                
                logging.info(f"处理结果: {result_item}")
                results.append(result_item)
                
                if success:
                    processed_files.append(result)
                
            except Exception as e:
                logging.error(f"处理文件失败: {e}", exc_info=True)
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": str(e)
                })
                continue
        
        # 创建ZIP文件（如果有成功处理的文件）
        if processed_files:
            zip_path, zip_filename = create_zip_file([r for r in results if r["success"]])
            logging.info(f"创建ZIP文件: {zip_path}")
            return {"success": True, "results": results, "download": zip_filename}
        
        return {"success": True, "results": results}
    
    except Exception as e:
        logging.error(f"处理上传文件时出错: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        # 恢复原始配置
        config.set("rename_with_amount", rename_with_amount)

@app.get("/download/{filename}")
async def download_file(filename: str):
    """下载处理后的ZIP文件"""
    file_path = os.path.join(downloads_dir, filename)
    if not os.path.exists(file_path):
        return JSONResponse(
            status_code=404,
            content={"error": "文件不存在"}
        )
    
    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=filename
    )

@app.get("/config")
async def get_config():
    """获取当前配置"""
    return config.get_all()

@app.post("/config")
async def update_config(
    rename_with_amount: bool = Form(...),
    ui_port: int = Form(...)
):
    """更新配置"""
    try:
        config.set("rename_with_amount", rename_with_amount)
        config.set("ui_port", ui_port)
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request, credentials: HTTPBasicCredentials = Depends(verify_admin)):
    """管理页面（需要密码验证）"""
    # 在Vercel环境下，使用admin_vercel.html模板
    template_name = "admin.html"
    if os.environ.get("VERCEL") == "1":
        template_name = "admin_vercel.html"
    
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "config": config.get_all()
        }
    )

@app.post("/admin/config")
async def update_system_config(
    credentials: HTTPBasicCredentials = Depends(verify_admin),
    ui_port: int = Form(...),
    admin_password: str = Form(None)  # 可选参数，用于更新管理员密码
):
    """更新系统配置（需要密码验证）"""
    try:
        config.set("ui_port", ui_port)
        
        # 如果提供了新密码，则更新密码哈希
        if admin_password:
            new_password_hash = hashlib.sha256(admin_password.encode()).hexdigest()
            config.set("admin_password_hash", new_password_hash)
            
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

@app.post("/user/config")
async def update_user_config(
    rename_with_amount: bool = Form(...)
):
    """更新Web UI用户配置"""
    try:
        # 将Web UI的重命名配置保存为单独的键
        config.set("webui_rename_with_amount", rename_with_amount)
        return {"success": True}
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

@app.get("/api/logs", response_class=JSONResponse)
async def get_logs(limit: int = 100, level: str = None, test: bool = False):
    """获取最近的日志记录"""
    try:
        # 如果是测试请求，生成几条不同级别的测试日志
        if test:
            logging.debug("这是一条测试DEBUG日志")
            logging.info("这是一条测试INFO日志")
            logging.warning("这是一条测试WARNING日志")
            logging.error("这是一条测试ERROR日志")
            
        if level and level.upper() not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            level = None
        
        # 生成一条测试日志，确保有日志可以显示
        logging.info(f"日志API被调用: limit={limit}, level={level}")
        
        logs = memory_handler.get_logs(limit=limit, level=level)
        logging.debug(f"返回日志记录: {len(logs)} 条")
        
        # 确保日志不为空，至少添加一条测试日志
        if not logs:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            logs = [{
                'timestamp': current_time,
                'level': 'INFO',
                'message': '系统正在运行中，暂无其他日志记录',
                'logger': 'system'
            }]
        
        return {"logs": logs, "count": len(logs), "status": "success"}
    except Exception as e:
        logging.error(f"获取日志时出错: {str(e)}", exc_info=True)
        return {"logs": [], "error": str(e), "status": "error"}

# 应用启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logging.info("FastAPI应用已启动")
    # 确保目录存在
    for directory in [uploads_dir, downloads_dir]:
        os.makedirs(directory, exist_ok=True)
        logging.info(f"确保目录存在: {directory}")

if __name__ == "__main__":
    port = config.get("ui_port", 8000)
    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=True) 