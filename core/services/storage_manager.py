# core/services/storage_manager.py
# Менеджер для работы с Яндекс.Диском

import yadisk
import os
import asyncio
from typing import Dict, List, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class YandexDiskManager:
    """Управление файлами на Яндекс.Диске"""
    
    def __init__(self, token: str):
        self.client = yadisk.YaDisk(token=token)
        self.base_folder = "/VideoAutomation"
        
    async def upload_project(self, 
                           project_id: str,
                           folder_structure: Dict[str, List[str]],
                           metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Загружает проект на Яндекс.Диск
        
        Args:
            project_id: ID проекта
            folder_structure: Структура папок и файлов
            metadata: Метаданные проекта
            
        Returns:
            Информация о загрузке
        """
        try:
            # Проверяем токен
            if not self.client.check_token():
                raise ValueError("Недействительный токен Яндекс.Диска")
            
            # Создаем папку проекта
            project_folder = f"{self.base_folder}/Projects/{project_id}"
            
            # Создаем базовую структуру
            await self._ensure_folder_exists(self.base_folder)
            await self._ensure_folder_exists(f"{self.base_folder}/Projects")
            await self._ensure_folder_exists(project_folder)
            
            # Загружаем файлы по категориям
            uploaded_files = []
            
            for category, files in folder_structure.items():
                category_folder = f"{project_folder}/{category}"
                await self._ensure_folder_exists(category_folder)
                
                for file_path in files:
                    if os.path.exists(file_path):
                        file_name = os.path.basename(file_path)
                        remote_path = f"{category_folder}/{file_name}"
                        
                        logger.info(f"Загружаем {file_name} в {category_folder}")
                        
                        await self._upload_file(file_path, remote_path)
                        uploaded_files.append(remote_path)
            
            # Создаем файл с метаданными
            import json
            metadata_path = f"outputs/{project_id}/project_metadata.json"
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump({
                    **metadata,
                    "upload_date": datetime.now().isoformat(),
                    "files_count": len(uploaded_files)
                }, f, ensure_ascii=False, indent=2)
            
            await self._upload_file(metadata_path, f"{project_folder}/metadata.json")
            
            # Получаем публичную ссылку
            folder_url = await self._get_public_url(project_folder)
            
            logger.info(f"Проект {project_id} успешно загружен")
            
            return {
                "folder_url": folder_url,
                "folder_path": project_folder,
                "files_count": len(uploaded_files),
                "uploaded_files": uploaded_files
            }
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке на Яндекс.Диск: {e}")
            raise
    
    async def _ensure_folder_exists(self, folder_path: str):
        """Создает папку если не существует"""
        loop = asyncio.get_event_loop()
        
        def check_and_create():
            try:
                if not self.client.exists(folder_path):
                    self.client.mkdir(folder_path)
                    logger.info(f"Создана папка: {folder_path}")
            except Exception as e:
                # Папка может уже существовать
                logger.debug(f"Папка {folder_path} уже существует или ошибка: {e}")
        
        await loop.run_in_executor(None, check_and_create)
    
    async def _upload_file(self, local_path: str, remote_path: str):
        """Загружает файл"""
        loop = asyncio.get_event_loop()
        
        def upload():
            try:
                self.client.upload(local_path, remote_path, overwrite=True)
            except Exception as e:
                logger.error(f"Ошибка загрузки файла {local_path}: {e}")
                raise
        
        await loop.run_in_executor(None, upload)
    
    async def _get_public_url(self, folder_path: str) -> str:
        """Получает публичную ссылку на папку"""
        loop = asyncio.get_event_loop()
        
        def get_url():
            try:
                # Публикуем папку
                self.client.publish(folder_path)
                
                # Получаем мета-информацию
                meta = self.client.get_meta(folder_path)
                
                # Возвращаем публичную ссылку
                return meta.public_url or folder_path
                
            except Exception as e:
                logger.error(f"Ошибка получения публичной ссылки: {e}")
                # Возвращаем путь если не удалось получить ссылку
                return folder_path
        
        return await loop.run_in_executor(None, get_url)