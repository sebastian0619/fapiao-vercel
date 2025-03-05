import os
import logging
import re
from pdf_processor import create_new_filename
from data_extractor import scan_qrcode, extract_information
from config_manager import config
from datetime import datetime

def process_ofd(file_path, tmp_dir, keep_temp_files=False):
    """
    处理OFD文件的简化版本
    注意：由于无法处理OFD图片提取，此函数仅基于文件名进行处理
    """
    try:
        logging.info(f"处理OFD文件: {file_path}")
        # 仅从文件名提取信息
        filename = os.path.basename(file_path)
        
        # 尝试从文件名提取发票号
        invoice_number = None
        invoice_patterns = [
            r"\b\d{20}\b",  # 20位发票号
            r"\b\d{10}\b",  # 10位发票号
            r"\b\d{8}\b"    # 8位发票号
        ]
        
        for pattern in invoice_patterns:
            invoice_match = re.search(pattern, filename)
            if invoice_match:
                invoice_number = invoice_match.group(0)
                logging.info(f"从文件名提取到发票号码: {invoice_number}")
                break
        
        # 如果无法从文件名提取，生成一个基于时间戳的发票号
        if not invoice_number:
            invoice_number = f"OFD{datetime.now().strftime('%Y%m%d%H%M%S')}"
            logging.info(f"生成时间戳发票号: {invoice_number}")
        
        # 尝试从文件名提取金额
        amount = None
        amount_match = re.search(r"(\d+\.\d{2})", filename)
        if amount_match:
            amount = amount_match.group(1)
            logging.info(f"从文件名提取到金额: {amount}")
        
        # 尝试提取其他相关信息（如果需要）
        # ...
        
        # 创建新文件名
        new_file_name = create_new_filename(invoice_number, amount, file_path)
        new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)
        
        # 处理文件名冲突
        counter = 1
        while os.path.exists(new_file_path):
            base_name = os.path.splitext(new_file_name)[0]
            ext = os.path.splitext(new_file_name)[1]
            new_file_path = os.path.join(os.path.dirname(file_path), f"{base_name}_{counter}{ext}")
            counter += 1
        
        # 重命名文件
        os.rename(file_path, new_file_path)
        logging.info(f"文件重命名为: {new_file_path}")
        return new_file_path
    except Exception as e:
        logging.error(f"处理OFD文件时出错: {e}", exc_info=True)
        return None

# 删除未使用的功能
# def extract_text_from_ofd(file_path):
#     """从OFD文件中提取文本（如果需要）"""
#     # TODO: 实现OFD文本提取功能
#     # 这个功能可能在未来需要，用于处理无法从二维码获取信息的情况
#     pass