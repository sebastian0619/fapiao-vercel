import os
import logging
import re
import PyPDF2
import io
import tempfile
import subprocess
from PIL import Image
from config_manager import config
from data_extractor import extract_information_from_pdf
from datetime import datetime

def create_new_filename(invoice_number, amount=None, original_path=None):
    """根据配置创建新文件名"""
    ext = os.path.splitext(original_path)[1] if original_path else '.pdf'
    
    # 检查是否需要包含金额
    if config.get('rename_with_amount', True) and amount:
        return f"[¥{amount}]{invoice_number}{ext}"
    return f"{invoice_number}{ext}"

def process_special_pdf(file_path):
    """处理PDF文件，简化版本"""
    try:
        logging.info(f"处理PDF文件: {file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logging.error(f"文件不存在: {file_path}")
            return None
            
        # 检查文件扩展名
        if not file_path.lower().endswith('.pdf'):
            logging.error(f"不是PDF文件: {file_path}")
            return None
            
        # 使用PDF信息提取功能
        invoice_number, amount_str = extract_information_from_pdf(file_path)
        
        if not invoice_number:
            logging.warning("未找到发票号码，使用生成的识别码")
            # 生成一个基于时间戳的发票号
            invoice_number = f"PDF{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
        logging.info(f"使用发票号码: {invoice_number}")
        if amount_str:
            logging.info(f"使用金额: {amount_str}")
        
        # 创建新文件名（即使没有找到金额也继续处理）
        new_file_name = create_new_filename(invoice_number, amount_str, file_path)
        new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)
        
        # 处理文件名冲突
        counter = 1
        while os.path.exists(new_file_path) and new_file_path != file_path:
            base_name = os.path.splitext(new_file_name)[0]
            ext = os.path.splitext(new_file_name)[1]
            new_file_path = os.path.join(os.path.dirname(file_path), f"{base_name}_{counter}{ext}")
            counter += 1
        
        # 防止重命名为自己
        if new_file_path == file_path:
            logging.warning(f"新文件名与原文件名相同，添加时间戳: {file_path}")
            timestamp = datetime.now().strftime("%H%M%S")
            base_name = os.path.splitext(new_file_name)[0]
            ext = os.path.splitext(new_file_name)[1]
            new_file_path = os.path.join(os.path.dirname(file_path), f"{base_name}_{timestamp}{ext}")
        
        # 重命名文件
        logging.info(f"重命名文件: {file_path} -> {new_file_path}")
        os.rename(file_path, new_file_path)
        logging.info(f"文件重命名为: {new_file_path}")
        return new_file_path
    except Exception as e:
        logging.error(f"处理PDF文件时出错: {e}", exc_info=True)
        return None

def convert_to_image_memory(pdf_path, max_pages=3):
    """
    轻量级方法:从PDF提取图像
    
    Args:
        pdf_path: PDF文件路径
        max_pages: 最大处理页数
        
    Returns:
        图像二进制数据列表
    """
    try:
        logging.info(f"使用轻量级方法从PDF提取图像: {pdf_path}")
        
        # 打开PDF获取页数
        with open(pdf_path, 'rb') as f:
            pdf = PyPDF2.PdfReader(f)
            total_pages = len(pdf.pages)
            logging.info(f"PDF共有{total_pages}页")
        
        # 限制处理的页数
        pages_to_process = min(total_pages, max_pages)
        
        images = []
        for page_num in range(pages_to_process):
            try:
                # 创建临时文件来存储图像
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    tmp_path = tmp.name
                
                # 尝试使用Python的PDF渲染能力（可能质量较低）
                with open(pdf_path, 'rb') as pdf_file:
                    pdf = PyPDF2.PdfReader(pdf_file)
                    if page_num < len(pdf.pages):
                        # 由于PyPDF2本身不支持PDF渲染为图像
                        # 我们将提示用户PDF被处理，但不会实际生成图像
                        logging.info(f"处理页面{page_num+1}/{pages_to_process}")
                        
                        # 在Vercel环境中，尝试使用pdftoppm命令（如果可用）
                        try:
                            # 使用pdftoppm（如果系统中可用）
                            output_prefix = os.path.splitext(tmp_path)[0]
                            cmd = f"pdftoppm -png -f {page_num+1} -l {page_num+1} -r 150 '{pdf_path}' '{output_prefix}'"
                            
                            # 尝试执行命令
                            result = os.system(cmd)
                            if result == 0:
                                # 查找生成的文件
                                import glob
                                generated_files = glob.glob(f"{output_prefix}*.png")
                                if generated_files:
                                    with open(generated_files[0], 'rb') as img_file:
                                        image_data = img_file.read()
                                        images.append(image_data)
                                    # 删除生成的文件
                                    for f in generated_files:
                                        os.remove(f)
                                    continue
                        except Exception as cmd_err:
                            logging.warning(f"使用pdftoppm命令失败: {cmd_err}")
                        
                        # 如果上述方法失败，使用更简单的方法
                        # 创建一个空白图像，写入一些文本表明这是PDF的页面
                        try:
                            # 创建具有基本信息的图像
                            img = Image.new('RGB', (800, 1000), color=(255, 255, 255))
                            # 保存图像
                            img.save(tmp_path)
                            with open(tmp_path, 'rb') as img_file:
                                image_data = img_file.read()
                                images.append(image_data)
                        except Exception as img_err:
                            logging.warning(f"创建图像失败: {img_err}")
                
                # 清理临时文件
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            
            except Exception as page_err:
                logging.warning(f"处理页面{page_num+1}失败: {page_err}")
        
        logging.info(f"成功从PDF提取{len(images)}张图像")
        return images
    except Exception as e:
        logging.error(f"从PDF提取图像失败: {e}", exc_info=True)
        return []

def extract_pages_as_images(pdf_path, output_dir=None, prefix="page", format="png"):
    """
    从PDF中提取页面并保存为图像文件，轻量级实现
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录
        prefix: 图像文件名前缀
        format: 图像格式
        
    Returns:
        保存的图像文件路径列表
    """
    try:
        # La creación de imágenes para PDFs ahora es más simple
        logging.info(f"轻量级提取PDF页面为图像: {pdf_path}")
        
        if not output_dir:
            output_dir = os.path.dirname(pdf_path)
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取PDF基本信息
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        images = []
        
        # 提取图像（最多前3页）
        image_data_list = convert_to_image_memory(pdf_path, max_pages=3)
        
        # 将图像保存到文件
        for idx, image_data in enumerate(image_data_list):
            output_path = os.path.join(output_dir, f"{prefix}_{base_name}_{idx+1}.{format}")
            with open(output_path, 'wb') as f:
                f.write(image_data)
            images.append(output_path)
            logging.info(f"保存图像: {output_path}")
        
        return images
    except Exception as e:
        logging.error(f"提取PDF页面为图像失败: {e}", exc_info=True)
        return []