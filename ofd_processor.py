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

def process_ofd(file_path, tmp_dir, keep_temp_files=False):
    """
    处理OFD文件
    OFD(Open Fixed-layout Document)是一种电子文档格式标准
    """
    try:
        logging.info(f"处理OFD文件: {file_path}")
        extracted_info = extract_ofd_info(file_path, tmp_dir)
        
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

def extract_ofd_info(file_path, tmp_dir):
    """
    从OFD文件中提取信息
    OFD文件基本上是一个ZIP文件，包含XML文件和其他资源
    """
    result = {
        'invoice_number': None,
        'amount': None
    }
    
    temp_dir = os.path.join(tmp_dir, f"ofd_extract_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        # 尝试作为ZIP文件打开OFD
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path) as ofd_zip:
                # 提取OFD文件内容
                ofd_zip.extractall(temp_dir)
                logging.info(f"已解压OFD文件到: {temp_dir}")
                
                # 尝试查找并解析主文档文件
                doc_xml_path = find_ofd_doc_xml(temp_dir)
                if doc_xml_path:
                    result = parse_ofd_doc_xml(doc_xml_path)
                
                # 尝试从任何可能的图像文件中提取二维码信息
                image_files = find_image_files(temp_dir)
                for img_file in image_files:
                    try:
                        qr_data = scan_qrcode(img_file)
                        if qr_data:
                            invoice_number, amount = extract_information(qr_data)
                            if invoice_number:
                                result['invoice_number'] = invoice_number
                            if amount and not result.get('amount'):
                                result['amount'] = amount
                            break
                    except Exception as e:
                        logging.warning(f"处理图片时出错: {e}")
        else:
            logging.warning(f"文件不是有效的OFD/ZIP格式: {file_path}")
    except Exception as e:
        logging.error(f"解析OFD文件时出错: {e}", exc_info=True)
    finally:
        # 清理临时目录
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except Exception as e:
            logging.warning(f"清理临时目录时出错: {e}")
    
    return result

def find_ofd_doc_xml(base_dir):
    """查找OFD文档中的主XML文件"""
    possible_paths = [
        os.path.join(base_dir, "OFD.xml"),
        os.path.join(base_dir, "Doc_0", "Document.xml"),
        os.path.join(base_dir, "Doc_0", "DocumentRes.xml")
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # 如果找不到预定义路径，尝试查找任何XML文件
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.lower().endswith('.xml'):
                return os.path.join(root, file)
    
    return None

def parse_ofd_doc_xml(xml_path):
    """解析OFD文档的XML文件以提取发票信息"""
    result = {
        'invoice_number': None,
        'amount': None
    }
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        # 查找金额字段 - 常见的命名模式
        amount_patterns = [
            ".//*[contains(local-name(), 'Amount')]",
            ".//*[contains(local-name(), 'Price')]",
            ".//*[contains(local-name(), 'money')]",
            ".//*[contains(local-name(), 'Money')]",
            ".//*[contains(local-name(), 'sum')]",
            ".//*[contains(local-name(), 'Sum')]"
        ]
        
        for pattern in amount_patterns:
            elements = root.findall(pattern)
            for element in elements:
                text = element.text if hasattr(element, 'text') else None
                if text and re.search(r'\d+\.\d{2}', text):
                    # 找到了可能的金额
                    amount = re.search(r'\d+\.\d{2}', text).group(0)
                    logging.info(f"从XML中提取到金额: {amount}")
                    result['amount'] = amount
                    break
        
        # 查找发票号码字段 - 常见的命名模式
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
                    # 找到了可能的发票号码
                    invoice_number = re.search(r'\b\d{8,20}\b', text).group(0)
                    logging.info(f"从XML中提取到发票号码: {invoice_number}")
                    result['invoice_number'] = invoice_number
                    break
    
    except Exception as e:
        logging.warning(f"解析XML时出错: {e}")
    
    return result

def find_image_files(base_dir):
    """在解压的OFD文件中查找图像文件"""
    image_files = []
    
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.tiff')):
                image_files.append(os.path.join(root, file))
    
    return image_files

# 删除未使用的功能
# def extract_text_from_ofd(file_path):
#     """从OFD文件中提取文本（如果需要）"""
#     # TODO: 实现OFD文本提取功能
#     # 这个功能可能在未来需要，用于处理无法从二维码获取信息的情况
#     pass