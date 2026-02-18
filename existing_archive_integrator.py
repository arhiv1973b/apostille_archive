#!/usr/bin/env python3
"""
Интеграция с существующим архивом CASE-MACHERET-1997-2026
Сканирование и организация существующих апостилей из "I:\Мой диск"
"""

import os
import json
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
import re

class ExistingArchiveIntegrator:
    def __init__(self, source_path="/mnt/i", target_path="/mnt/c/apostille_archive/CASE-MACHERET-1997-2026"):
        self.source_path = Path(source_path)
        self.target_path = Path(target_path)
        
        # Инициализация базы данных
        self.init_database()
        
        print(f"📂 Интегратор существующих архивов инициализирован")
        print(f"📁 Источник: {self.source_path}")
        print(f"📁 Цель: {self.target_path}")

    def init_database(self):
        """Инициализация базы данных для существующих файлов"""
        self.db_path = self.target_path / "archive_database.sqlite3"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS existing_apostilles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_path TEXT UNIQUE NOT NULL,
                    filename TEXT,
                    category TEXT,
                    year TEXT,
                    case_number TEXT,
                    document_type TEXT,
                    status TEXT DEFAULT 'indexed',
                    file_size INTEGER,
                    indexed_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
        
        print("🗄️ База данных для существующих файлов готова")

    def extract_metadata_from_filename(self, filename):
        """Извлечение метаданных из имени файла"""
        metadata = {
            'year': None,
            'case_number': None,
            'document_type': None,
            'persons': [],
            'dates': []
        }
        
        # Поиск годов
        year_matches = re.findall(r'(19|20)\d{2}', filename)
        if year_matches:
            metadata['year'] = year_matches[-1]
        
        # Поиск номеров дел
        case_patterns = [
            r'(\d+-\d+_\d{2})',  # 1-984_07
            r'(\d+[rRa]-\d+)',   # 10r-1009
            r'(1ra-\d+_\d{2})',  # 1ra-834_09
            r'(1a-\d+_\d{2})',   # 1a-42_09
        ]
        
        for pattern in case_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                metadata['case_number'] = match.group(1)
                break
        
        # Определение типа документа
        doc_types = {
            'sentinta': 'решение/приговор',
            'decizie': 'решение',
            'certificat': 'сертификат',
            'cazier': 'справка о судимости',
            'extras': 'выписка',
            'medical': 'медицинский',
            'expertiza': 'экспертиза',
            'procuratura': 'прокуратура',
            'judecatoria': 'суд',
            'discriminare': 'дискриминация'
        }
        
        for key, value in doc_types.items():
            if key.lower() in filename.lower():
                metadata['document_type'] = value
                break
        
        # Поиск имен
        name_patterns = [
            r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # Имя Фамилия
            r'([A-Z][a-z]+)',                # Простое имя
            r'(Олейник)', r'(Мачерет)', r'(Вирлан)', r'(Потинга)',
            r'(Бабалэу)', r'(Морозан)', r'(Дулче)', r'(Николеску)'
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, filename)
            metadata['persons'].extend(matches)
        
        return metadata

    def determine_category(self, filename, metadata):
        """Определение категории на основе имени файла и метаданных"""
        filename_lower = filename.lower()
        
        # Приоритетные категории
        if 'macheret' in filename_lower or 'мачерет' in filename_lower:
            return "negru_din_macheret/documente_oficiale"
        elif 'negru' in filename_lower:
            return "negru_din_macheret/dovezi"
        elif 'dis crimi' in filename_lower or 'дискримин' in filename_lower:
            return "documente_juridice/contracte"
        elif 'medical' in filename_lower or 'экспертиз' in filename_lower:
            return "documente_juridice/certificate"
        elif metadata.get('year') == '2021':
            return f"2021/{self._get_month_from_filename(filename)}"
        elif metadata.get('case_number'):
            return "documente_juridice/declaratii"
        else:
            return "downloads/pending"

    def _get_month_from_filename(self, filename):
        """Определение месяца из имени файла"""
        months = {
            'ianuarie': 'ianuarie', 'februarie': 'februarie', 'martie': 'martie',
            'aprilie': 'aprilie', 'mai': 'mai', 'iunie': 'iunie',
            'iulie': 'iulie', 'august': 'august', 'septembrie': 'septembrie',
            'octombrie': 'octombrie', 'noiembrie': 'noiembrie', 'decembrie': 'decembrie'
        }
        
        for month_en, month_ro in months.items():
            if month_en.lower() in filename.lower() or month_ro.lower() in filename.lower():
                return month_ro
        
        return 'ianuarie'  # по умолчанию

    def process_existing_files(self):
        """Обработка существующих файлов апостилей"""
        print("🔍 Сканирование существующих файлов апостилей...")
        
        # Ваш список файлов из "I:\Мой диск"
        apostille_files = [
            "I:\\Мой диск\\Outlook\\apostila  Суд мед. экспертиза последствие решения Г. Морозан санкционировавший рабой 2.pdf",
            "I:\\Мой диск\\apostila (13.10.1998ю.Sentinta.pdf",
            "I:\\Мой диск\\apostila (13.10.1998ю (1).Sentinta.pdf",
            "I:\\Мой диск\\apostila  Суд мед. экспертиза последствие решения Г. Морозан санкционировавший рабой.pdf",
            "I:\\Мой диск\\apostila.11.02.2021.pdf",
            "I:\\Мой диск\\Scanned Documents\\apostila Постановление.pdf",
            "I:\\Мой диск\\apostila (5).pdf",
            "I:\\Мой диск\\apostila.pdf",
            "I:\\Мой диск\\.подписан.pdf\\apostila Дата[. 1-568_98] 1-272_2003 и 1-649_2008.pdf",
            "I:\\Мой диск\\.подписан.pdf\\apostila  10r- 1009 (1).подписан.pdf",
            "I:\\Мой диск\\apostila(POTINGAй.pdf",
            "I:\\Мой диск\\iCloudPhotos\\Photos\\Новая папка\\apostila  12-4df.pdf",
            "I:\\Мой диск\\iCloudPhotos\\Photos\\Новая папка\\apostila 95 Денис Бабалэу.pdf",
            "I:\\Мой диск\\apostila 95 Денис Бабалэу.pdf",
            "I:\\Мой диск\\apostila(POTINGAй (1).pdf",
            "I:\\Мой диск\\apostila  10r- 1009.pdf",
            "I:\\Мой диск\\apostila Sentinta 1998.pdf",
            "I:\\Мой диск\\apostila 615-616 Олейник и Мачерег.pdf",
            "I:\\Мой диск\\apostila дела от 13.10.1998 года.pdf",
            "I:\\Мой диск\\apostila Сертификат ПУ-15 на рус..pdf"
        ]
        
        processed_count = 0
        
        for file_path in apostille_files:
            try:
                path_obj = Path(file_path)
                filename = path_obj.name
                
                # Извлечение метаданных
                metadata = self.extract_metadata_from_filename(filename)
                
                # Определение категории
                category = self.determine_category(filename, metadata)
                
                # Создание записи в базе данных
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO existing_apostilles 
                        (original_path, filename, category, year, case_number, 
                         document_type, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        file_path,
                        filename,
                        category,
                        metadata['year'],
                        metadata['case_number'],
                        metadata['document_type'],
                        json.dumps(metadata, ensure_ascii=False)
                    ))
                
                processed_count += 1
                print(f"✅ Индексирован: {filename[:50]}...")
                print(f"   📂 Категория: {category}")
                print(f"   📅 Год: {metadata['year'] or 'N/A'}")
                print(f"   📋 Дело: {metadata['case_number'] or 'N/A'}")
                print()
                
            except Exception as e:
                print(f"❌ Ошибка обработки {file_path}: {e}")
        
        print(f"🎯 Индексировано файлов: {processed_count}")
        return processed_count

    def generate_inventory_report(self):
        """Генерация отчета об инвентаризации"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Статистика по категориям
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM existing_apostilles 
                GROUP BY category 
                ORDER BY count DESC
            """)
            category_stats = dict(cursor.fetchall())
            
            # Статистика по годам
            cursor.execute("""
                SELECT year, COUNT(*) as count 
                FROM existing_apostilles 
                WHERE year IS NOT NULL 
                GROUP BY year 
                ORDER BY year DESC
            """)
            year_stats = dict(cursor.fetchall())
            
            # Статистика по типам документов
            cursor.execute("""
                SELECT document_type, COUNT(*) as count 
                FROM existing_apostilles 
                WHERE document_type IS NOT NULL 
                GROUP BY document_type 
                ORDER BY count DESC
            """)
            doc_type_stats = dict(cursor.fetchall())
            
            # Общее количество
            cursor.execute("SELECT COUNT(*) FROM existing_apostilles")
            total_count = cursor.fetchone()[0]
        
        report = {
            'inventory_date': datetime.now().isoformat(),
            'total_files': total_count,
            'by_category': category_stats,
            'by_year': year_stats,
            'by_document_type': doc_type_stats,
            'archive_path': str(self.target_path)
        }
        
        # Сохранение отчета
        report_path = self.target_path / "inventory_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        return report

def main():
    """Основная функция интеграции существующих архивов"""
    print("🗂️ ИНВЕНТАРИЗАЦИЯ СУЩЕСТВУЮЩИХ АПОСТИЛЕЙ")
    print("=" * 60)
    
    # Создание интегратора
    integrator = ExistingArchiveIntegrator()
    
    # Обработка существующих файлов
    processed_count = integrator.process_existing_files()
    
    # Генерация отчета
    report = integrator.generate_inventory_report()
    
    print("\n" + "=" * 60)
    print("🎯 ИНВЕНТАРИЗАЦИЯ ЗАВЕРШЕНА")
    print(f"📁 Всего файлов: {report['total_files']}")
    print(f"📊 По категориям: {len(report['by_category'])}")
    print(f"📅 По годам: {len(report['by_year'])}")
    print(f"📋 По типам: {len(report['by_document_type'])}")
    print(f"📄 Отчет: {integrator.target_path}/inventory_report.json")
    print("=" * 60)
    
    return integrator, report

if __name__ == "__main__":
    integrator, report = main()