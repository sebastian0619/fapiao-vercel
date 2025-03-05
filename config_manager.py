import json
import os
import logging
from typing import Dict, Any

class ConfigManager:
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """加载配置，优先级：config.json > 环境变量 > 默认值"""
        # 默认配置
        self._config = {
            "rename_with_amount": True,
            "ui_port": 8080,
            "log_level": "INFO",
            "temp_dir": "./tmp",
            "supported_formats": [".pdf", ".ofd"]
        }

        # 从配置文件加载
        try:
            if os.path.exists('config.json'):
                with open('config.json', 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                    self._config.update(file_config)
                logging.info("配置已从config.json加载")
        except Exception as e:
            logging.warning(f"加载配置文件失败: {e}")

        # 从环境变量加载
        env_mapping = {
            "RENAME_WITH_AMOUNT": "rename_with_amount",
            "UI_PORT": "ui_port",
            "LOG_LEVEL": "log_level",
            "TEMP_DIR": "temp_dir"
        }

        for env_key, config_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value is not None:
                # 类型转换
                if isinstance(self._config[config_key], bool):
                    self._config[config_key] = env_value.lower() in ('true', '1', 'yes')
                elif isinstance(self._config[config_key], int):
                    self._config[config_key] = int(env_value)
                else:
                    self._config[config_key] = env_value
                logging.info(f"配置从环境变量加载: {config_key}={self._config[config_key]}")
        
        # Vercel环境特定设置
        if os.environ.get('VERCEL') == '1':
            # 在Vercel环境中使用/tmp目录
            logging.info("检测到Vercel环境，使用/tmp作为临时目录")
            self._config["temp_dir"] = "/tmp"

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置配置项并保存到文件"""
        self._config[key] = value
        self.save()

    def save(self) -> None:
        """保存配置到文件，在Vercel环境中仅保存到内存"""
        # 在Vercel环境中不写入文件
        if os.environ.get('VERCEL') == '1':
            logging.info(f"Vercel环境：配置仅保存到内存")
            return
            
        try:
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=4, ensure_ascii=False)
            logging.info("配置已保存到config.json")
        except Exception as e:
            logging.error(f"保存配置文件失败: {e}")

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()

# 全局配置实例
config = ConfigManager() 