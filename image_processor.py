import os
import logging

def crop_image(image_path, output_dir):
    """
    裁剪图像的简化版本 - 实际不进行裁剪
    此版本仅用于保持API兼容性，不实际处理图像
    """
    logging.info(f"图像处理已简化，不进行实际裁剪: {image_path}")
    return image_path
