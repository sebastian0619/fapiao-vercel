import os
import logging
import re
import PyPDF2
import io
import fitz  # PyMuPDF
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

def convert_to_image_memory(pdf_path, zoom_x=2.0, zoom_y=2.0):
    """
    将PDF转换为内存中的图像列表
    
    Args:
        pdf_path: PDF文件路径
        zoom_x: 水平缩放比例
        zoom_y: 垂直缩放比例
        
    Returns:
        图像二进制数据列表
    """
    try:
        logging.info(f"从PDF提取图像: {pdf_path}")
        
        # 打开PDF文件
        pdf_document = fitz.open(pdf_path)
        images = []
        
        # 处理每一页
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            
            # 设置矩阵用于缩放
            mat = fitz.Matrix(zoom_x, zoom_y)
            
            # 获取页面图像
            pix = page.get_pixmap(matrix=mat)
            
            # 转换为PIL图像
            img_data = io.BytesIO(pix.tobytes())
            images.append(img_data.getvalue())
            
            logging.info(f"提取了页面 {page_num+1}/{len(pdf_document)} 的图像")
            
            # 仅处理前5页以提高性能
            if page_num >= 4:
                logging.info(f"仅处理前5页图像，跳过剩余页面")
                break
                
        if not images:
            logging.warning(f"未能从PDF中提取图像: {pdf_path}")
            
        logging.info(f"成功从PDF提取了 {len(images)} 张图像")
        return images
    except Exception as e:
        logging.error(f"提取PDF图像时出错: {e}", exc_info=True)
        return []
        
def extract_pages_as_images(pdf_path, output_dir=None, prefix="page", format="png"):
    """
    从PDF中提取页面并保存为图像文件
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录，默认为PDF所在目录
        prefix: 图像文件名前缀
        format: 图像格式 (png, jpg等)
        
    Returns:
        保存的图像文件路径列表
    """
    try:
        # 如果未指定输出目录，使用PDF所在目录
        if not output_dir:
            output_dir = os.path.dirname(pdf_path)
            
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取PDF文件名（不含扩展名）
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # 打开PDF文件
        pdf_document = fitz.open(pdf_path)
        saved_images = []
        
        # 处理每一页
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            
            # 设置矩阵用于高质量渲染 (300 DPI)
            mat = fitz.Matrix(2.0, 2.0)
            
            # 获取页面图像
            pix = page.get_pixmap(matrix=mat)
            
            # 构建输出文件路径
            output_filename = f"{prefix}_{base_name}_{page_num+1}.{format}"
            output_path = os.path.join(output_dir, output_filename)
            
            # 保存图像
            pix.save(output_path)
            saved_images.append(output_path)
            
            logging.info(f"保存页面 {page_num+1}/{len(pdf_document)} 为图像: {output_path}")
            
        return saved_images
    except Exception as e:
        logging.error(f"提取PDF页面为图像时出错: {e}", exc_info=True)
        return []