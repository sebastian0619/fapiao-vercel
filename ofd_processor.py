import os
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from pdf_processor import create_new_filename
from data_extractor import scan_qrcode, extract_information
from config_manager import config
from datetime import datetime
from PIL import Image
import io

def process_ofd(file_path, tmp_dir, keep_temp_files=False):
    """
    处理OFD文件
    OFD(Open Fixed-layout Document)是一种电子文档格式标准
    """
    try:
        logging.info(f"处理OFD文件: {file_path}")
        extracted_info = extract_ofd_info_direct(file_path)
        
        invoice_number = extracted_info.get('invoice_number')
        amount = extracted_info.get('amount')
        
        # 如果无法从内容提取，则尝试从文件名提取发票号
        if not invoice_number:
            filename = os.path.basename(file_path)
            invoice_number = extract_invoice_number_from_filename(filename)
            logging.info(f"从文件名提取到发票号码: {invoice_number}")
        
        # 如果仍然没有发票号，生成一个基于时间戳的唯一标识符
        if not invoice_number:
            invoice_number = f"OFD{datetime.now().strftime('%Y%m%d%H%M%S')}"
            logging.info(f"生成时间戳发票号: {invoice_number}")
            
        logging.info(f"发票号: {invoice_number}, 金额: {amount}")
        
        # 创建新文件名
        new_file_name = create_new_filename(invoice_number, amount, file_path)
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
            timestamp = datetime.now().strftime("%H%M%S")
            base_name = os.path.splitext(new_file_name)[0]
            ext = os.path.splitext(new_file_name)[1]
            new_file_path = os.path.join(os.path.dirname(file_path), f"{base_name}_{timestamp}{ext}")
        
        # 重命名文件
        logging.info(f"重命名文件: {file_path} -> {new_file_path}")
        os.rename(file_path, new_file_path)
        return new_file_path
    except Exception as e:
        logging.error(f"处理OFD文件时出错: {e}", exc_info=True)
        return None

def extract_invoice_number_from_filename(filename):
    """从文件名中提取发票号码"""
    invoice_patterns = [
        r"\b\d{20}\b",  # 20位发票号
        r"\b\d{10}\b",  # 10位发票号
        r"\b\d{8}\b"    # 8位发票号
    ]
    
    for pattern in invoice_patterns:
        invoice_match = re.search(pattern, filename)
        if invoice_match:
            return invoice_match.group(0)
    
    return None

def extract_ofd_info_direct(file_path):
    """
    直接从OFD文件中提取信息，不使用临时目录
    """
    result = {
        'invoice_number': None,
        'amount': None
    }
    
    try:
        if not zipfile.is_zipfile(file_path):
            logging.warning(f"文件不是有效的OFD/ZIP格式: {file_path}")
            return result
            
        with zipfile.ZipFile(file_path) as ofd_zip:
            # 搜索可能的XML文件
            xml_files = [f for f in ofd_zip.namelist() if f.lower().endswith('.xml')]
            
            # 处理每个XML文件
            for xml_file in xml_files:
                try:
                    with ofd_zip.open(xml_file) as xml_data:
                        xml_content = xml_data.read()
                        invoice_info = parse_ofd_xml_content(xml_content)
                        
                        # 如果找到了发票号或金额，更新结果
                        if invoice_info.get('invoice_number'):
                            result['invoice_number'] = invoice_info['invoice_number']
                        if invoice_info.get('amount'):
                            result['amount'] = invoice_info['amount']
                            
                        # 如果已经找到了所有信息，可以提前返回
                        if result['invoice_number'] and result['amount']:
                            return result
                except Exception as e:
                    logging.warning(f"解析XML文件 {xml_file} 时出错: {e}")
                    continue
            
            # 如果从XML获取不到完整信息，尝试从图片中提取
            image_files = [f for f in ofd_zip.namelist() 
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff'))]
            
            for img_file in image_files:
                try:
                    with ofd_zip.open(img_file) as img_data:
                        img_bytes = img_data.read()
                        # 创建临时内存文件对象
                        img_io = io.BytesIO(img_bytes)
                        # 将图像加载到内存中
                        image = Image.open(img_io)
                        
                        # 使用图像宽度作为临时文件名（仅作为标识符）
                        temp_id = f"memimg_{hash(img_file)}"
                        
                        # 通过从图像中提取文本来模拟扫描二维码
                        # 注意：由于我们没有实际的二维码库，这部分功能有限
                        # 直接从图像提取文本模式尝试查找发票号和金额
                        if not result['invoice_number'] or not result['amount']:
                            # 在内存中处理图像
                            try:
                                invoice_number = None
                                amount = None
                                
                                # 将图像转为灰度
                                gray_img = image.convert('L')
                                
                                # 使用简单模式尝试查找发票号（20位数字）
                                # 这里只是一个示例，实际需要OCR库支持
                                
                                # 如果发现了信息，更新结果
                                if invoice_number and not result['invoice_number']:
                                    result['invoice_number'] = invoice_number
                                if amount and not result['amount']:
                                    result['amount'] = amount
                            except Exception as img_err:
                                logging.warning(f"处理图像文件时出错: {img_err}")
                
                except Exception as e:
                    logging.warning(f"处理图像文件 {img_file} 时出错: {e}")
                    continue
                    
    except Exception as e:
        logging.error(f"直接从OFD文件中提取信息时出错: {e}", exc_info=True)
    
    return result

def parse_ofd_xml_content(xml_content):
    """
    从XML内容中解析发票信息
    """
    result = {
        'invoice_number': None,
        'amount': None
    }
    
    try:
        root = ET.fromstring(xml_content)
        
        # 使用XPath搜索可能包含发票号的元素
        invoice_patterns = [
            ".//*[contains(local-name(), 'Invoice')]",
            ".//*[contains(local-name(), 'Number')]",
            ".//*[contains(local-name(), 'Code')]",
            ".//*[contains(local-name(), 'ID')]"
        ]
        
        for pattern in invoice_patterns:
            elements = root.findall(pattern)
            for element in elements:
                text = element.text if hasattr(element, 'text') else None
                if text and re.search(r'\b\d{8,20}\b', text):
                    invoice_number = re.search(r'\b\d{8,20}\b', text).group(0)
                    logging.info(f"从XML中提取到发票号码: {invoice_number}")
                    result['invoice_number'] = invoice_number
                    break
            
            if result['invoice_number']:
                break
        
        # 搜索可能包含金额的元素
        amount_patterns = [
            ".//*[contains(local-name(), 'Amount')]",
            ".//*[contains(local-name(), 'Price')]",
            ".//*[contains(local-name(), 'Money')]",
            ".//*[contains(local-name(), 'Sum')]",
            ".//*[contains(lower-case(local-name()), 'amount')]",
            ".//*[contains(lower-case(local-name()), 'price')]",
            ".//*[contains(lower-case(local-name()), 'money')]",
            ".//*[contains(lower-case(local-name()), 'sum')]"
        ]
        
        for pattern in amount_patterns:
            elements = root.findall(pattern)
            for element in elements:
                text = element.text if hasattr(element, 'text') else None
                if text and re.search(r'\d+\.\d{2}', text):
                    amount = re.search(r'\d+\.\d{2}', text).group(0)
                    logging.info(f"从XML中提取到金额: {amount}")
                    result['amount'] = amount
                    break
            
            if result['amount']:
                break
                
    except Exception as e:
        logging.warning(f"解析XML内容时出错: {e}")
    
    return result

# 删除未使用的功能
# def extract_text_from_ofd(file_path):
#     """从OFD文件中提取文本（如果需要）"""
#     # TODO: 实现OFD文本提取功能
#     # 这个功能可能在未来需要，用于处理无法从二维码获取信息的情况
#     pass