#!/usr/bin/env python3
"""
Автоматический загрузчик апостилей по прямым ссылкам
Использует сгенерированные URL для загрузки PDF файлов
"""

import os
import time
import json
import requests
import sqlite3
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

class DirectApostilleDownloader:
    def __init__(self, archive_path="/mnt/c/apostille_archive/CASE-MACHERET-1997-2026"):
        self.archive_path = Path(archive_path)
        self.session = requests.Session()
        
        # Настройка сессии с SSL bypass
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Headers для имитации браузера
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/pdf,application/octet-stream',
            'Accept-Language': 'ro-RU,ro;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://apostila.gov.md/'
        })
        
        # Настройка логирования
        self.setup_logging()
        
        # База данных
        self.db_path = self.archive_path / "archive_database.sqlite3"
        
        print(f"📥 Прямой загрузчик апостилей инициализирован")

    def setup_logging(self):
        """Настройка логирования"""
        log_file = self.archive_path / "download_direct.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def load_links_from_json(self):
        """Загрузка ссылок из JSON файла"""
        links_file = self.archive_path / "download_links" / "apostille_download_links.json"
        
        if not links_file.exists():
            self.logger.error(f"❌ Файл со ссылками не найден: {links_file}")
            return {}
        
        with open(links_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def download_single_apostille(self, code, data):
        """Загрузка одного апостиля по прямой ссылке"""
        try:
            url = data['download_url']
            self.logger.info(f"📥 Загрузка {code}...")
            
            # Загрузка PDF
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                
                # Проверка, что это PDF
                if 'pdf' in content_type or len(response.content) > 1000:
                    # Создание имени файла
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{timestamp}_{code}.pdf"
                    
                    # Путь для сохранения
                    target_dir = self.archive_path / "downloads" / "completed"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    file_path = target_dir / filename
                    
                    # Сохранение файла
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                    
                    # Обновление базы данных
                    self.update_download_status(code, 'success', file_path, len(response.content))
                    
                    self.logger.info(f"✅ {code} успешно загружен: {filename}")
                    return {
                        'success': True,
                        'code': code,
                        'filename': filename,
                        'file_path': str(file_path),
                        'file_size': len(response.content),
                        'url': url
                    }
                else:
                    error_msg = f"Неверный content-type: {content_type}"
                    self.logger.error(f"❌ {code}: {error_msg}")
                    self.update_download_status(code, 'failed', None, 0, error_msg)
                    return {'success': False, 'code': code, 'error': error_msg}
            else:
                error_msg = f"HTTP {response.status_code}"
                self.logger.error(f"❌ {code}: {error_msg}")
                self.update_download_status(code, 'failed', None, 0, error_msg)
                return {'success': False, 'code': code, 'error': error_msg}
                
        except Exception as e:
            error_msg = f"Ошибка загрузки: {str(e)}"
            self.logger.error(f"💥 {code}: {error_msg}")
            self.update_download_status(code, 'error', None, 0, error_msg)
            return {'success': False, 'code': code, 'error': error_msg}

    def update_download_status(self, code, status, file_path=None, file_size=0, error_msg=None):
        """Обновление статуса загрузки в базе данных"""
        with sqlite3.connect(self.db_path) as conn:
            # Обновление таблицы download_links
            conn.execute("""
                INSERT OR REPLACE INTO download_links 
                (apostille_code, status, last_attempt, download_success, download_failures)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
            """, (
                code,
                status,
                1 if status == 'success' else 0,
                1 if status in ['failed', 'error'] else 0
            ))
            
            # Если успешно, добавляем в основной реестр
            if status == 'success' and file_path:
                conn.execute("""
                    INSERT OR REPLACE INTO apostille_registry 
                    (code, filename, file_path, category, status, download_date, file_size)
                    VALUES (?, ?, ?, ?, 'downloaded', ?, ?)
                """, (
                    code,
                    Path(file_path).name,
                    str(file_path),
                    "downloads/completed",
                    datetime.now().isoformat(),
                    file_size
                ))

    def test_single_link(self, code, data):
        """Тестирование одной ссылки"""
        url = data['download_url']
        
        try:
            # HEAD запрос для проверки доступности
            response = self.session.head(url, timeout=10)
            
            if response.status_code == 200:
                content_length = response.headers.get('content-length', 'N/A')
                content_type = response.headers.get('content-type', 'N/A')
                
                print(f"✅ {code}")
                print(f"   Статус: {response.status_code}")
                print(f"   Размер: {content_length} bytes")
                print(f"   Тип: {content_type}")
                print(f"   URL: {url}")
                return True
            else:
                print(f"❌ {code} - HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print(f"💥 {code} - Ошибка: {e}")
            return False

    def test_all_links(self):
        """Тестирование всех ссылок"""
        print("🧪 ТЕСТИРОВАНИЕ ВСЕХ ССЫЛОК")
        print("=" * 60)
        
        links = self.load_links_from_json()
        
        working_links = 0
        total_links = len(links)
        
        for code, data in links.items():
            if self.test_single_link(code, data):
                working_links += 1
            time.sleep(0.5)  # Небольшая задержка
        
        print(f"\n📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
        print(f"✅ Рабочие ссылки: {working_links}/{total_links}")
        print(f"❌ Нерабочие ссылки: {total_links - working_links}/{total_links}")
        print(f"📈 Успешность: {(working_links/total_links)*100:.1f}%")
        
        return working_links, total_links

    def download_batch(self, max_workers=3):
        """Пакетная загрузка всех апостилей"""
        print("📥 НАЧАЛО ПАКЕТНОЙ ЗАГРУЗКИ АПОСТИЛЕЙ")
        print("=" * 60)
        
        links = self.load_links_from_json()
        
        results = {
            'total': len(links),
            'success': 0,
            'failed': 0,
            'errors': 0,
            'start_time': datetime.now()
        }
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(self.download_single_apostille, code, data): code 
                for code, data in links.items()
            }
            
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    result = future.result()
                    
                    if result['success']:
                        results['success'] += 1
                    else:
                        if 'HTTP' in result.get('error', ''):
                            results['failed'] += 1
                        else:
                            results['errors'] += 1
                    
                    # Прогресс
                    progress = (results['success'] + results['failed'] + results['errors']) / results['total'] * 100
                    self.logger.info(f"📊 Прогресс: {progress:.1f}% ({results['success']} успехов, {results['failed']} неудач)")
                    
                except Exception as e:
                    self.logger.error(f"💥 Ошибка потока для {code}: {e}")
                    results['errors'] += 1
        
        results['end_time'] = datetime.now()
        results['duration'] = str(results['end_time'] - results['start_time'])
        
        # Сохранение отчета
        self.save_download_report(results)
        
        return results

    def save_download_report(self, results):
        """Сохранение отчета о загрузке"""
        report_path = self.archive_path / "download_report.json"
        
        report = {
            'download_date': datetime.now().isoformat(),
            'results': results,
            'success_rate': (results['success'] / results['total']) * 100,
            'archive_path': str(self.archive_path)
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📊 ОТЧЕТ О ЗАГРУЗКЕ:")
        print(f"✅ Успешно: {results['success']}/{results['total']}")
        print(f"❌ Неудачно: {results['failed']}")
        print(f"💥 Ошибок: {results['errors']}")
        print(f"📈 Успешность: {report['success_rate']:.1f}%")
        print(f"⏱️ Длительность: {results['duration']}")
        print(f"📁 Файлы в: {self.archive_path}/downloads/completed/")

def main():
    """Основная функция"""
    print("📥 ПРЯМОЙ ЗАГРУЗЧИК АПОСТИЛЕЙ")
    print("=" * 60)
    
    downloader = DirectApostilleDownloader()
    
    # Сначала тестирование
    working, total = downloader.test_all_links()
    
    if working > 0:
        print(f"\n🚀 НАЧАЛО ЗАГРУЗКИ {working} РАБОЧИХ ФАЙЛОВ...")
        results = downloader.download_batch(max_workers=2)
    else:
        print("❌ Нет рабочих ссылок для загрузки")
    
    print("\n🎯 ЗАГРУЗКА ЗАВЕРШЕНА")
    print("=" * 60)

if __name__ == "__main__":
    main()