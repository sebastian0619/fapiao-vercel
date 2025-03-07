from PIL import Image
import re
# import fitz  # PyMuPDF, 用于读取PDF文件
# from pyzbar.pyzbar import decode
import logging
import PyPDF2
import os
import base64
import io

def scan_qrcode(image_path):
    """
    尝试提取图像中的文本信息，模拟二维码扫描
    注意：由于移除了pyzbar库，此函数能力有限
    """
    try:
        logging.info(f"正在处理图片: {image_path}")
        
        # 打开图片
        image = Image.open(image_path)
        
        # 尝试解析二维码区域 (黑白区域)
        # 这是一个简化版本，实际上并不会解码二维码，但会尝试检测是否有二维码区域
        # 如果要完整解码二维码，需要专门的库如pyzbar
        
        # 尝试检测二维码区域
        qr_text = detect_text_from_image(image)
        if qr_text:
            logging.info(f"从图像中提取到文本信息: {qr_text[:50]}...")
            return qr_text
        
        # 尝试OCR文本识别（在真实场景中可能需要更专业的OCR库）
        # 在这里我们只能做简单的模拟
        
        # 将图像转为灰度图
        gray_image = image.convert('L')
        
        # 检查图像中是否有发票特征
        invoice_info = extract_text_from_regions(gray_image)
        if invoice_info:
            return invoice_info
        
        logging.debug(f"未能从图像中提取有用信息")
        return None
    except Exception as e:
        logging.debug(f"处理图片失败: {e}", exc_info=True)
        return None

def detect_text_from_image(image):
    """
    尝试从图像中检测文本信息
    这是一个简化版本，主要用于检测是否包含发票相关信息
    """
    try:
        # 保存为临时文件
        temp_buffer = io.BytesIO()
        image.save(temp_buffer, format="PNG")
        temp_buffer.seek(0)
        
        # 在真实应用中，可以集成OCR服务
        # 这里我们返回None表示没有检测到
        return None
    except Exception as e:
        logging.warning(f"检测图像文本时出错: {e}")
        return None

def extract_text_from_regions(image):
    """
    从图像的特定区域提取文本
    这是一个简化版本，实际应用中可能需要专业OCR库
    """
    # 在真实应用中，这里会有区域识别和OCR逻辑
    # 目前返回None
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
        logging.info(f"从PDF文件提取信息: {file_path}")
        text = ""
        # 使用PyPDF2代替PyMuPDF
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            # 处理所有页面以确保不错过发票信息
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        
        logging.debug(f"提取的文本长度: {len(text)}")
        
        # 提取发票号码 - 使用更灵活的模式匹配
        invoice_number = None
        # 尝试多种模式，发票号可能是8位、10位或20位
        invoice_patterns = [
            r"\b\d{20}\b",   # 20位发票号
            r"\b\d{10}\b",   # 10位发票号
            r"\b\d{8}\b"     # 8位发票号
        ]
        
        for pattern in invoice_patterns:
            invoice_matches = re.findall(pattern, text)
            if invoice_matches:
                # 通常第一个匹配的是发票号
                invoice_number = invoice_matches[0]
                logging.info(f"提取到发票号码: {invoice_number}")
                break
        
        # 如果没找到，使用文件名作为备用方案
        if not invoice_number:
            base_filename = os.path.basename(file_path)
            invoice_match = re.search(r"\b\d{8,20}\b", base_filename)
            if invoice_match:
                invoice_number = invoice_match.group(0)
                logging.info(f"从文件名提取到发票号码: {invoice_number}")
            else:
                # 使用一个通用标识符和时间戳
                from datetime import datetime
                invoice_number = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"
                logging.info(f"使用生成的发票号码: {invoice_number}")
        
        # 提取金额
        amount = None
        amount_patterns = [
            r"¥\s*(\d+\.\d{2})",
            r"金额[^\d]*(\d+\.\d{2})",
            r"价税合计[^\d]*(\d+\.\d{2})",
            r"小写[^\d]*(\d+\.\d{2})",
            r"(\d+\.\d{2})元"
        ]
        
        for pattern in amount_patterns:
            amount_matches = re.findall(pattern, text)
            if amount_matches:
                # 如果有多个匹配，尝试找出最大金额
                amounts = [float(x) for x in amount_matches]
                max_amount = max(amounts)
                amount = "{:.2f}".format(max_amount)
                logging.info(f"提取到金额: {amount}")
                break
        
        return invoice_number, amount
    except Exception as e:
        logging.error(f"从PDF提取信息时出错: {e}", exc_info=True)
        return None, None