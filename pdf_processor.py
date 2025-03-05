import os
import logging
import re
import PyPDF2
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