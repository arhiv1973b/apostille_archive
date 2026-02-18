#!/usr/bin/env python3
"""
Интеграция apostille processor с архивом CASE-MACHERET-1997-2026
Автоматическая загрузка и организация апостилей в существующую систему архива
"""

import os
import sys
import time
import json
import shutil
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

class SimpleApostilleDownloader:
    """Упрощенный загрузчик апостилей для интеграции с архивом"""
    
    def __init__(self):
        self.session = None
        self.base_url = "https://apostila.gov.md"
        self.setup_session()
        
    def setup_session(self):
        """Настройка сессии с SSL bypass"""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        self.session = requests.Session()
        
        # SSL verification bypass
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ro-RU,ro;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })

    def process_single_apostille(self, code):
        """Загрузка одного апостиля по коду"""
        try:
            # Шаг 1: Получение страницы поиска
            search_url = f"{self.base_url}/apostila/site/search"
            response = self.session.get(search_url, timeout=10)
            
            if response.status_code != 200:
                return {'success': False, 'error': f'Search page failed: {response.status_code}'}
            
            # Шаг 2: Отправка POST запроса с кодом
            post_data = {
                'Registration[search_string]': code,
                'yt0': 'Căutare'
            }
            
            post_response = self.session.post(search_url, data=post_data, timeout=10)
            
            if post_response.status_code != 200:
                return {'success': False, 'error': f'POST request failed: {post_response.status_code}'}
            
            # Шаг 3: Поиск PDF ссылки
            content = post_response.text
            if '.pdf' in content.lower():
                # Простая эвристика для поиска PDF
                import re
                pdf_pattern = r'href=["\']([^"\']*\.pdf)["\']'
                pdf_matches = re.findall(pdf_pattern, content, re.IGNORECASE)
                
                if pdf_matches:
                    pdf_url = pdf_matches[0]
                    if not pdf_url.startswith('http'):
                        pdf_url = self.base_url + pdf_url if pdf_url.startswith('/') else f"{self.base_url}/{pdf_url}"
                    
                    # Шаг 4: Загрузка PDF
                    pdf_response = self.session.get(pdf_url, timeout=15)
                    
                    if pdf_response.status_code == 200 and len(pdf_response.content) > 1000:
                        # Сохранение файла
                        filename = f"apostille_{code}_{int(time.time())}.pdf"
                        filepath = f"/tmp/{filename}"
                        
                        with open(filepath, 'wb') as f:
                            f.write(pdf_response.content)
                        
                        return {
                            'success': True,
                            'file_path': filepath,
                            'filename': filename,
                            'file_size': len(pdf_response.content),
                            'code': code,
                            'pdf_url': pdf_url
                        }
            
            return {'success': False, 'error': 'PDF link not found'}
            
        except Exception as e:
            return {'success': False, 'error': f'Processing error: {str(e)}'}

class CaseMacheretIntegrator:
    def __init__(self, archive_path="/mnt/c/apostille_archive/CASE-MACHERET-1997-2026"):
        self.archive_path = Path(archive_path)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        
        # Инициализация загрузчика
        self.downloader = SimpleApostilleDownloader()
        
        # Настройка логирования
        self.setup_logging()
        
        # Инициализация базы данных
        self.init_database()
        
        # Создание структуры архива
        self.create_archive_structure()
        
        print(f"📁 Архив CASE-MACHERET-1997-2026 создан: {self.archive_path}")

    def setup_logging(self):
        """Настройка расширенного логирования"""
        log_file = self.archive_path / "archive_integration.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def init_database(self):
        """Инициализация базы данных архива"""
        self.db_path = self.archive_path / "archive_database.sqlite3"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS apostille_registry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    filename TEXT,
                    file_path TEXT,
                    category TEXT,
                    status TEXT DEFAULT 'pending',
                    download_date TEXT,
                    file_size INTEGER,
                    metadata TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    action TEXT,
                    status TEXT,
                    message TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
        print("🗄️ База данных архива инициализирована")

    def create_archive_structure(self):
        """Создание структуры каталогов архива"""
        categories = {
            "2021": {
                "description": "Апостили 2021 года",
                "subdirs": ["ianuarie", "februarie", "martie", "aprilie", "mai", "iunie", 
                           "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie"]
            },
            "documente_juridice": {
                "description": "Документы юридические",
                "subdirs": ["certificate", "extrase", "declaratii", "contracte"]
            },
            "negru_din_macheret": {
                "description": "Дело Negru din Macheret",
                "subdirs": ["dovezi", "probe", "documente_oficiale", "corespondenta"]
            },
            "processed": {
                "description": "Обработанные документы",
                "subdirs": ["verified", "pending_review", "archived"]
            },
            "downloads": {
                "description": "Свежие загрузки",
                "subdirs": ["pending", "processing", "completed"]
            }
        }
        
        for category, info in categories.items():
            cat_path = self.archive_path / category
            cat_path.mkdir(parents=True, exist_ok=True)
            
            # Создаем README для категории
            readme_path = cat_path / "README.md"
            if not readme_path.exists():
                with open(readme_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {category.upper()}\n\n{info['description']}\n\n")
                    f.write("## Подкаталоги:\n")
                    for subdir in info['subdirs']:
                        f.write(f"- `{subdir}/`\n")
            
            # Создаем подкаталоги
            for subdir in info['subdirs']:
                (cat_path / subdir).mkdir(exist_ok=True)
        
        print("📂 Структура архива создана")

    def determine_category(self, code, metadata=None):
        """Определение категории для апостиля"""
        if "BOU" in code or "CFY" in code:
            return "2021/ianuarie"
        elif "CQ0V" in code or "IG4Q" in code:
            return "2021/februarie"
        elif "NEG" in code or "MAC" in code:
            return "negru_din_macheret/dovezi"
        else:
            return "downloads/pending"

    def add_to_archive_registry(self, code, filename, file_path, category, file_size=None, metadata=None):
        """Добавление записи в реестр архива"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO apostille_registry 
                (code, filename, file_path, category, status, download_date, file_size, metadata)
                VALUES (?, ?, ?, ?, 'downloaded', ?, ?, ?)
            """, (
                code, 
                filename, 
                str(file_path),
                category,
                datetime.now().isoformat(),
                file_size,
                json.dumps(metadata) if metadata else None
            ))
        
        self.logger.info(f"📋 Код {code} добавлен в реестр архива")

    def process_apostille(self, code):
        """Обработка одного апостиля с интеграцией в архив"""
        try:
            self.logger.info(f"🔄 Обработка кода: {code}")
            
            # Загрузка
            download_result = self.downloader.process_single_apostille(code)
            
            if download_result and download_result['success']:
                # Определение категории
                category = self.determine_category(code, download_result)
                
                # Создание имени файла
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}_{code}.pdf"
                
                # Копирование в архив
                source_path = Path(download_result['file_path'])
                target_path = self.archive_path / category / filename
                
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
                
                # Добавление в реестр
                self.add_to_archive_registry(
                    code, 
                    filename, 
                    target_path, 
                    category,
                    source_path.stat().st_size,
                    download_result
                )
                
                self.logger.info(f"✅ {code} интегрирован в архив: {category}")
                return True
                
            else:
                self.logger.error(f"❌ Не удалось скачать {code}: {download_result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            self.logger.error(f"💥 Ошибка интеграции {code}: {str(e)}")
            return False

    def process_batch(self, codes, max_workers=2):
        """Пакетная обработка с интеграцией в архив"""
        self.logger.info(f"🚀 Начало пакетной обработки {len(codes)} кодов")
        
        results = {
            'total': len(codes),
            'processed': 0,
            'failed': 0,
            'start_time': datetime.now()
        }
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(self.process_apostille, code): code 
                for code in codes
            }
            
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    success = future.result()
                    if success:
                        results['processed'] += 1
                    else:
                        results['failed'] += 1
                        
                    # Прогресс
                    progress = (results['processed'] + results['failed']) / results['total'] * 100
                    self.logger.info(f"📊 Прогресс: {progress:.1f}% ({results['processed']} успехов, {results['failed']} неудач)")
                    
                except Exception as e:
                    self.logger.error(f"💥 Ошибка потока для {code}: {e}")
                    results['failed'] += 1
        
        results['end_time'] = datetime.now()
        results['duration'] = str(results['end_time'] - results['start_time'])
        
        # Сохранение отчета
        report_path = self.archive_path / "integration_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        
        self.logger.info(f"🎯 Интеграция завершена: {results['processed']}/{results['total']} успешно")
        return results

def main():
    """Основная функция интеграции"""
    print("🗄️ ИНИЦИАЛИЗАЦИЯ ИНТЕГРАЦИИ С CASE-MACHERET-1997-2026")
    print("=" * 60)
    
    # Создание интегратора
    integrator = CaseMacheretIntegrator()
    
    # Тестовые коды из 2021
    test_codes = [
        "BOUS9XAQDTFH2",
        "IMWM44AZGX6N6", 
        "CQ0VC27VGTCK6"
    ]
    
    print(f"📋 Тестовых кодов для интеграции: {len(test_codes)}")
    
    # Обработка с интеграцией в архив
    results = integrator.process_batch(test_codes, max_workers=1)
    
    print("\n" + "=" * 60)
    print("🎯 ИНТЕГРАЦИЯ ЗАВЕРШЕНА")
    print(f"✅ Обработано: {results['processed']}")
    print(f"❌ Неудачно: {results['failed']}")
    print(f"⏱️ Длительность: {results['duration']}")
    print(f"📁 Архив: {integrator.archive_path}")
    print("=" * 60)
    
    return integrator, results

if __name__ == "__main__":
    integrator, results = main()