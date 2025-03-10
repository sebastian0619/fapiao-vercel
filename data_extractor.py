from PIL import Image
import re
# import fitz  # PyMuPDF, 用于读取PDF文件
import logging
import PyPDF2
import os
import base64
import io

# 检查环境变量，明确禁用二维码支持
NO_ZBAR_REQUIRED = os.environ.get("NO_ZBAR_REQUIRED", "0") == "1"
if NO_ZBAR_REQUIRED:
    logging.warning("环境变量NO_ZBAR_REQUIRED=1，将禁用二维码支持")
    QRCODE_SUPPORT = False
    # 定义一个空函数作为替代
    def decode(image):
        return []
else:
    # 尝试导入pyzbar，但在缺少系统依赖时不会崩溃
    try:
        from pyzbar.pyzbar import decode
        QRCODE_SUPPORT = True
        logging.info("二维码支持已启用（pyzbar库成功加载）")
    except ImportError as e:
        QRCODE_SUPPORT = False
        logging.warning(f"二维码支持已禁用: {e}")
        # 定义一个空函数作为替代
        def decode(image):
            return []

def scan_qrcode(image_path):
    """
    使用pyzbar扫描二维码（如果可用）
    """
    # 如果没有二维码支持，直接返回None
    if not QRCODE_SUPPORT:
        logging.info("二维码支持不可用，跳过扫描")
        return None
        
    try:
        logging.info(f"扫描二维码: {image_path}")
        image = Image.open(image_path)
        
        # 如果图片太大，调整大小以提高处理速度
        if image.width > 1500 or image.height > 1500:
            image.thumbnail((1500, 1500), Image.LANCZOS)
        
        # 尝试直接读取二维码
        decoded_objects = decode(image)
        if decoded_objects:
            for obj in decoded_objects:
                try:
                    qr_data = obj.data.decode('utf-8')
                    logging.info(f"成功识别二维码: {qr_data[:50]}...")
                    return qr_data
                except Exception as e:
                    logging.warning(f"解码二维码数据失败: {e}")
                    continue
        
        # 如果直接读取失败，尝试优化图像再次读取
        # 转为灰度图以提高对比度
        gray_img = image.convert('L')
        decoded_objects = decode(gray_img)
        if decoded_objects:
            for obj in decoded_objects:
                try:
                    qr_data = obj.data.decode('utf-8')
                    logging.info(f"优化后识别二维码: {qr_data[:50]}...")
                    return qr_data
                except Exception as e:
                    logging.warning(f"解码优化后的二维码数据失败: {e}")
                    continue
                    
        logging.warning(f"未能在图像中识别到二维码: {image_path}")
        return None
    except Exception as e:
        logging.error(f"扫描二维码失败: {e}", exc_info=True)
        return None

def extract_information(data_str):
    """
    从二维码数据中提取发票号码和金额
    
    常见二维码格式:
    1. "发票代码:xxxxxxxx,发票号码:xxxxxxxx,日期:xxxx年xx月xx日,校验码:xxxxx,金额:xxxx.xx"
    2. "01,10,xxxxxxxx,xxxxxxxx,xxxx.xx,xxxx.xx,xxxxxx"
    """
    if not data_str:
        return None, None
        
    invoice_number = None
    amount = None
    
    try:
        logging.info(f"从二维码提取信息: {data_str[:100]}...")
        
        # 尝试多种模式解析二维码内容
        
        # 模式1: 键值对格式
        if "发票号码" in data_str or "发票代码" in data_str:
            # 提取发票号码
            invoice_match = re.search(r"发票号码[：:]\s*(\d{8,20})", data_str)
            if invoice_match:
                invoice_number = invoice_match.group(1)
                logging.info(f"从键值对二维码提取到发票号码: {invoice_number}")
            else:
                # 尝试提取发票代码+发票号码
                code_match = re.search(r"发票代码[：:]\s*(\d{10,12})", data_str)
                number_match = re.search(r"发票号码[：:]\s*(\d{8})", data_str)
                if code_match and number_match:
                    invoice_number = code_match.group(1) + number_match.group(1)
                    logging.info(f"从键值对二维码提取到发票代码+号码: {invoice_number}")
                    
            # 提取金额
            amount_match = re.search(r"金额[：:]\s*(\d+\.\d{2})", data_str)
            if amount_match:
                amount = amount_match.group(1)
                logging.info(f"从键值对二维码提取到金额: {amount}")
            else:
                # 尝试其他金额格式
                amount_match = re.search(r"(?:金额|价税合计)[^\d]*(\d+\.\d{2})", data_str)
                if amount_match:
                    amount = amount_match.group(1)
                    logging.info(f"从键值对二维码提取到金额(备选格式): {amount}")
                
        # 模式2: 逗号分隔的数值格式
        elif "," in data_str and len(data_str.split(",")) >= 5:
            parts = data_str.split(",")
            # 通常第3、4个部分是发票代码和发票号码
            if len(parts) >= 4 and re.match(r"\d{8,12}", parts[2]) and re.match(r"\d{8}", parts[3]):
                invoice_number = parts[2] + parts[3]
                logging.info(f"从CSV格式二维码提取到发票代码+号码: {invoice_number}")
                
                # 通常第5个部分是金额
                if len(parts) >= 5 and re.match(r"\d+\.\d{2}", parts[4]):
                    amount = parts[4]
                    logging.info(f"从CSV格式二维码提取到金额: {amount}")
        
        # 如果上述解析失败，尝试通用的数据格式
        if not invoice_number:
            # 寻找所有可能的发票号码格式
            number_matches = re.findall(r"\b\d{8,20}\b", data_str)
            if number_matches:
                invoice_number = number_matches[0]  # 使用第一个匹配
                logging.info(f"通用模式提取到发票号码: {invoice_number}")
        
        if not amount:
            # 寻找所有可能的金额格式
            amount_matches = re.findall(r"\b\d+\.\d{2}\b", data_str)
            if amount_matches:
                # 过滤掉不合理的金额
                valid_amounts = [float(a) for a in amount_matches if 0.01 <= float(a) <= 100000]
                if valid_amounts:
                    amount = "{:.2f}".format(max(valid_amounts))
                    logging.info(f"通用模式提取到金额: {amount}")
    except Exception as e:
        logging.error(f"从二维码数据提取信息时出错: {e}", exc_info=True)
    
    return invoice_number, amount

def extract_information_from_pdf(file_path):
    """
    从PDF文件中提取发票信息
    优先使用二维码方式（如果可用），如果失败再尝试文本提取
    """
    try:
        logging.info(f"从PDF文件提取信息: {file_path}")
        
        # 步骤1: 如果二维码支持可用，则尝试从PDF提取图像并识别二维码
        if QRCODE_SUPPORT:
            try:
                from pdf_processor import convert_to_image_memory
                images = convert_to_image_memory(file_path)
                
                # 确保有临时目录
                temp_dir = "/tmp"
                if os.environ.get("VERCEL") == "1":
                    # 在Vercel环境中使用/tmp目录
                    temp_dir = "/tmp"
                else:
                    # 本地环境使用当前目录的temp子目录
                    temp_dir = os.path.join(os.path.dirname(__file__), "temp")
                    os.makedirs(temp_dir, exist_ok=True)
                
                # 从图像中提取二维码信息
                for idx, img_data in enumerate(images):
                    img = Image.open(io.BytesIO(img_data))
                    # 保存临时图像文件用于二维码扫描
                    temp_img_path = os.path.join(temp_dir, f"temp_qr_img_{idx}.png")
                    img.save(temp_img_path)
                    
                    # 扫描二维码
                    qr_data = scan_qrcode(temp_img_path)
                    
                    # 清理临时文件
                    try:
                        os.remove(temp_img_path)
                    except Exception as e:
                        logging.warning(f"无法删除临时文件 {temp_img_path}: {e}")
                        
                    # 如果找到二维码信息，从中提取发票信息
                    if qr_data:
                        invoice_number, amount = extract_information(qr_data)
                        if invoice_number:
                            logging.info(f"成功从二维码提取到信息 - 发票号: {invoice_number}, 金额: {amount}")
                            return invoice_number, amount
            except Exception as e:
                logging.warning(f"从PDF提取图像并识别二维码失败: {e}")
        else:
            logging.info("二维码支持不可用，直接使用文本提取")
            
        # 步骤2: 如果二维码提取失败，回退到文本提取方法
        logging.info("尝试从文本提取信息")
        text = ""
        # 使用PyPDF2提取文本
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            # 处理所有页面以确保不错过发票信息
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
        
        logging.debug(f"提取的文本长度: {len(text)}")
        logging.debug(f"提取的文本(前300字符): {text[:300]}")
        
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
                logging.info(f"从文本提取到发票号码: {invoice_number}")
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
        
        # 提取金额 - 优化版本
        amount = None
        
        # 更全面的金额匹配模式
        amount_patterns = [
            # 小写合计行的格式模式  
            r"小写[金额]?[^\d\n]{0,20}(?:¥|￥|RMB|人民币)?(\d+\.\d{2})",
            r"(?:小写|小写金额|小写总计)[：:]((?:¥|￥)?[0-9,]+\.[0-9]{2})",
            
            # 价税合计相关格式
            r"[价税]+[合计]+[：:]?(?:¥|￥|RMB|人民币)?\s*([0-9,]+\.[0-9]{2})",
            r"(?:[（(]?小写[）)]?|价税合计)[^\d\n]{0,20}(?:¥|￥|RMB)?\s*([0-9,]+\.[0-9]{2})",
            
            # 标准货币格式  
            r"(?:¥|￥)\s*([0-9,]+\.[0-9]{2})",
            r"RMB\s*([0-9,]+\.[0-9]{2})",
            
            # 发票专用格式
            r"金额[：:]\s*([0-9,]+\.[0-9]{2})",
            r"(?:金额|合[计]?)[^\d\n]{0,20}(?:¥|￥)?\s*([0-9,]+\.[0-9]{2})",
            
            # 更通用的模式，一般用作备选
            r"(\d+\.\d{2})元",
            r"\b(\d+\.\d{2})\b"
        ]
        
        # 保存所有匹配到的金额，稍后分析
        all_amounts = []
        all_amount_contexts = {}  # 存储金额及其上下文
        
        # 先尝试从文件名中提取金额，这通常是最准确的来源
        base_filename = os.path.basename(file_path)
        file_amount_match = re.search(r"\[¥?(\d+\.\d{2})\]", base_filename)
        if file_amount_match:
            try:
                file_amount = float(file_amount_match.group(1))
                all_amounts.append(file_amount)
                all_amount_contexts[file_amount] = f"文件名: {base_filename}"
                logging.info(f"从文件名提取到金额: {file_amount}")
            except:
                pass
        
        # 然后尝试高优先级的金额匹配模式
        # 小写合计和价税合计是发票上最准确的金额来源
        high_priority_patterns = [
            (r"小写[金额]?[^\d\n]{0,20}(?:¥|￥|RMB|人民币)?(\d+\.\d{2})", "小写金额"),
            (r"(?:小写|小写金额|小写总计)[：:]((?:¥|￥)?[0-9,]+\.[0-9]{2})", "小写金额冒号格式"),
            (r"[价税]+[合计]+[：:]?(?:¥|￥|RMB|人民币)?\s*([0-9,]+\.[0-9]{2})", "价税合计"),
            (r"(?:合[计]?金额|价税合计)[^\d\n]{0,20}(?:¥|￥)?\s*([0-9,]+\.[0-9]{2})", "合计金额") 
        ]
        
        for pattern, desc in high_priority_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):  # 处理多组捕获
                    match = match[0]
                # 清理金额字符串
                clean_amount = match.replace(",", "").replace("¥", "").replace("￥", "")
                try:
                    float_amount = float(clean_amount)
                    if 0.01 <= float_amount <= 100000:
                        all_amounts.append(float_amount)
                        # 找出匹配上下文（前后20个字符)
                        match_context = find_context(text, match)
                        all_amount_contexts[float_amount] = f"{desc}: {match_context}"
                        logging.info(f"找到高优先级金额: {float_amount} ({desc})")
                except ValueError:
                    continue
        
        # 如果高优先级匹配没有结果，则尝试其他模式
        if not all_amounts:
            for pattern in amount_patterns:
                amount_matches = re.findall(pattern, text)
                for match in amount_matches:
                    if isinstance(match, tuple):  # 处理多组捕获
                        match = match[0]
                    # 清理金额字符串
                    clean_amount = match.replace(",", "").replace("¥", "").replace("￥", "")
                    try:
                        float_amount = float(clean_amount)
                        if 0.01 <= float_amount <= 100000:
                            all_amounts.append(float_amount)
                            # 找出匹配上下文（前后20个字符)
                            match_context = find_context(text, match)
                            all_amount_contexts[float_amount] = f"普通匹配: {match_context}"
                            logging.info(f"找到普通金额: {float_amount}")
                    except ValueError:
                        continue
        
        # 如果找到多个金额，根据上下文选择最合适的
        if all_amounts:
            logging.info(f"找到的所有可能金额: {all_amounts}")
            for amt, context in all_amount_contexts.items():
                logging.info(f"金额 {amt} 上下文: {context}")
                
            # 优先考虑通过文件名得到的金额
            file_amount = None
            file_amount_match = re.search(r"\[¥?(\d+\.\d{2})\]", base_filename)
            if file_amount_match:
                try:
                    file_amount = float(file_amount_match.group(1)) 
                    # 判断文件名金额是否在提取的金额中（允许0.01的误差）
                    for amt in all_amounts:
                        if abs(amt - file_amount) < 0.01:
                            amount = "{:.2f}".format(amt)
                            logging.info(f"选择与文件名匹配的金额: {amount}")
                            return invoice_number, amount
                except:
                    pass
                    
            # 优先选择含有"小写"或"价税合计"关键词上下文的金额
            for amt, context in all_amount_contexts.items():
                lower_context = context.lower()
                if any(key in lower_context for key in ["小写金额", "小写", "价税合计", "合计金额"]):
                    amount = "{:.2f}".format(amt)
                    logging.info(f"基于关键词上下文选择金额: {amount} (上下文: {context})")
                    return invoice_number, amount
            
            # 如果找不到明确的上下文，则查找最大的那个值
            if all_amounts:
                amount = "{:.2f}".format(max(all_amounts))
                logging.info(f"选择所有金额中的最大值: {amount}")
        
        return invoice_number, amount
    except Exception as e:
        logging.error(f"从PDF提取信息时出错: {e}", exc_info=True)
        return None, None
        
def find_context(text, match_text, context_chars=20):
    """
    查找匹配文本在原文中的上下文
    """
    try:
        index = text.find(match_text)
        if index >= 0:
            start = max(0, index - context_chars)
            end = min(len(text), index + len(match_text) + context_chars)
            context = text[start:end]
            return f"...{context}..."
        return "上下文未找到"
    except:
        return "上下文提取错误"