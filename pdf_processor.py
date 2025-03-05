import os
import logging
import re
import PyPDF2
from config_manager import config
from data_extractor import extract_information_from_pdf

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
        logging.debug(f"处理PDF文件: {file_path}")
        
        # 使用简化的PDF信息提取功能
        invoice_number, amount_str = extract_information_from_pdf(file_path)
        
        if not invoice_number:
            logging.debug("未找到发票号码")
            return None
            
        logging.debug(f"找到发票号码: {invoice_number}")
        if amount_str:
            logging.debug(f"找到金额: {amount_str}")
        
        # 创建新文件名（即使没有找到金额也继续处理）
        new_file_name = create_new_filename(invoice_number, amount_str, file_path)
        new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)
        
        # 处理文件名冲突
        counter = 1
        while os.path.exists(new_file_path):
            base_name = os.path.splitext(new_file_name)[0]
            ext = os.path.splitext(new_file_name)[1]
            new_file_path = os.path.join(os.path.dirname(file_path), f"{base_name}_{counter}{ext}")
            counter += 1
        
        os.rename(file_path, new_file_path)
        logging.info(f"文件重命名为: {new_file_path}")
        return new_file_path
    except Exception as e:
        logging.error(f"处理PDF文件时出错: {e}")
        return None