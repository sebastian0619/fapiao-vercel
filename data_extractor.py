from PIL import Image
import re
# import fitz  # PyMuPDF, 用于读取PDF文件
# from pyzbar.pyzbar import decode
import logging
import PyPDF2

def scan_qrcode(image_path):
    """
    简化二维码扫描功能，仅返回模拟数据
    注意：由于移除了pyzbar库，此函数实际上不再扫描二维码
    在生产环境中需要通过API或其他方式实现此功能
    """
    try:
        logging.debug(f"正在处理图片: {image_path}")
        # 简化功能，返回None表示未识别到二维码
        # 在生产环境应使用单独的API服务处理二维码
        return None
    except Exception as e:
        logging.debug(f"处理图片失败: {e}")
        return None

def extract_information(data_str):
    """
    从二维码数据中提取发票号码和金额
    """
    if not data_str:
        return None, None
        
    invoice_number = None
    amount = None
    
    try:
        # 提取发票号码（支持20位和8位格式）
        invoice_match = re.search(r"\b\d{20}\b|\b\d{8}\b", data_str)
        if invoice_match:
            invoice_number = invoice_match.group(0)
            logging.debug(f"提取到发票号码: {invoice_number}")
        
        # 提取金额（支持多种格式）
        amount_patterns = [
            r"(\d+\.\d+)(?=,)",  # 标准格式：数字.数字,
            r"金额[:：]\s*(\d+\.\d+)",  # 带"金额"标识
            r"¥\s*(\d+\.\d+)",  # 带货币符号
            r"[^\d](\d+\.\d+)[^\d]"  # 通用数字格式
        ]
        
        for pattern in amount_patterns:
            amount_match = re.search(pattern, data_str)
            if amount_match:
                amount = round(float(amount_match.group(1)), 2)
                amount = "{:.2f}".format(amount)
                logging.debug(f"提取到金额: {amount}")
                break
    except Exception as e:
        logging.debug(f"提取信息时出错: {e}")
    
    return invoice_number, amount

def extract_information_from_pdf(file_path):
    """
    直接从PDF文件中提取发票信息
    简化版本，使用PyPDF2代替PyMuPDF
    """
    try:
        text = ""
        # 使用PyPDF2代替PyMuPDF
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            # 只处理第一页
            if len(reader.pages) > 0:
                page = reader.pages[0]
                text = page.extract_text()
        
        # 提取发票号码
        invoice_number = None
        invoice_match = re.search(r"\b\d{20}\b|\b\d{8}\b", text)
        if invoice_match:
            invoice_number = invoice_match.group(0)
            logging.debug(f"提取到发票号码: {invoice_number}")
        
        # 提取金额
        amount = None
        amount_match = re.search(r"¥\s*(\d+\.\d+)", text)
        if amount_match:
            amount = round(float(amount_match.group(1)), 2)
            amount = "{:.2f}".format(amount)
            logging.debug(f"提取到金额: {amount}")
        
        return invoice_number, amount
    except Exception as e:
        logging.debug(f"从PDF提取信息时出错: {e}")
        return None, None