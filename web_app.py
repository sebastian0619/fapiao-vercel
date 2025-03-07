from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import logging
from typing import List
import shutil
from datetime import datetime
import zipfile
import re
import hashlib
import secrets
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from config_manager import config
from pdf_processor import process_special_pdf
from ofd_processor import process_ofd
import uvicorn

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
        # 使用Web UI的配置
        config.set("rename_with_amount", config.get("webui_rename_with_amount", False))
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
                        result = process_special_pdf(file_path)
                        logging.info(f"PDF处理结果: {result}")
                        
                        if result:
                            try:
                                amount_match = re.search(r'\[¥(\d+\.\d{2})\]', os.path.basename(result))
                                if amount_match:
                                    amount = amount_match.group(1)
                                    logging.info(f"提取到金额: {amount}")
                            except Exception as e:
                                logging.warning(f"提取金额失败: {e}")
                    elif ext == '.ofd':
                        logging.info(f"开始处理OFD文件: {file_path}")
                        # 确保tmp_dir存在
                        os.makedirs(tmp_dir, exist_ok=True)
                        result = process_ofd(file_path, tmp_dir, False)
                        logging.info(f"OFD处理结果: {result}")
                        
                        if result:
                            try:
                                amount_match = re.search(r'\[¥(\d+\.\d{2})\]', os.path.basename(result))
                                if amount_match:
                                    amount = amount_match.group(1)
                                    logging.info(f"提取到金额: {amount}")
                            except Exception as e:
                                logging.warning(f"提取金额失败: {e}")
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
        config.set("rename_with_amount", config.get("webui_rename_with_amount", False))

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

if __name__ == "__main__":
    port = config.get("ui_port", 8000)
    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=True) 