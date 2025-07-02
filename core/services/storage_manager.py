# Путь: /youtube_automation_bot/core/services/storage_manager.py
# Описание: Менеджер для работы с Яндекс.Диском

import yadisk
import os
import json
from typing import Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class YandexDiskManager:
    """Управление файлами на Яндекс.Диске"""
    
    def __init__(self, token: str):
        self.y = yadisk.YaDisk(token=token)
        
        # Проверка токена
        if not self.y.check_token():
            raise ValueError("Invalid Yandex.Disk token")
        
        self.base_path = "/VideoAutomation"
        
    async def upload_project(self, 
                           project_id: str,
                           files: Dict[str, List[str]],
                           metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Загружает файлы проекта на Яндекс.Диск
        
        Args:
            project_id: ID проекта
            files: Словарь {категория: [пути к файлам]}
            metadata: Метаданные проекта
            
        Returns:
            Информация о загрузке
        """
        # Создаем структуру папок
        date_str = datetime.now().strftime("%Y-%m-%d")
        project_path = f"{self.base_path}/{date_str}/{project_id}"
        
        # Создаем базовые папки
        self._ensure_folder(self.base_path)
        self._ensure_folder(f"{self.base_path}/{date_str}")
        self._ensure_folder(project_path)
        
        uploaded_files = []
        
        # Загружаем файлы по категориям
        for category, file_list in files.items():
            category_path = f"{project_path}/{category}"
            self._ensure_folder(category_path)
            
            for file_path in file_list:
                if os.path.exists(file_path):
                    remote_path = f"{category_path}/{os.path.basename(file_path)}"
                    
                    logger.info(f"Загружаем {file_path} -> {remote_path}")
                    
                    try:
                        self.y.upload(file_path, remote_path, overwrite=True)
                        uploaded_files.append(remote_path)
                    except Exception as e:
                        logger.error(f"Ошибка загрузки {file_path}: {e}")
        
        # Сохраняем метаданные
        metadata_path = f"{project_path}/metadata.json"
        metadata_local = f"/tmp/{project_id}_metadata.json"
        
        with open(metadata_local, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        self.y.upload(metadata_local, metadata_path, overwrite=True)
        os.remove(metadata_local)
        
        # Получаем публичную ссылку на папку
        self.y.publish(project_path)
        meta = self.y.get_meta(project_path)
        
        return {
            "folder_path": project_path,
            "folder_url": meta.public_url,
            "files_count": len(uploaded_files),
            "uploaded_files": uploaded_files
        }
    
    def _ensure_folder(self, path: str):
        """Создает папку если она не существует"""
        try:
            self.y.mkdir(path)
        except yadisk.exceptions.PathExistsError:
            pass  # Папка уже существует
        except Exception as e:
            logger.error(f"Ошибка создания папки {path}: {e}")
            raise