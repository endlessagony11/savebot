import os
import sqlite3
from datetime import datetime, timedelta

def clean_old_images():
    """Удаляет изображения из папки storage, которые старше 2 дней."""
    days = 2
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

        # Формируем "Белый список" файлов (Keep List) - файлы, которые новее 2 дней
        c.execute("SELECT file_path FROM messages WHERE timestamp >= ?", (cutoff_date,))
        keep_files = set()
        for row in c.fetchall():
            if row[0]:
                keep_files.add(os.path.normpath(row[0]))

        # Сканируем папку storage и удаляем старые файлы
        deleted_files_count = 0
        storage_dir = 'storage'
        if os.path.exists(storage_dir):
            for filename in os.listdir(storage_dir):
                full_path = os.path.join(storage_dir, filename)
                if os.path.isfile(full_path):
                    if os.path.normpath(full_path) not in keep_files:
                        try:
                            os.remove(full_path)
                            deleted_files_count += 1
                            print(f"Удален файл: {filename}")
                        except Exception as e:
                            print(f"Ошибка при удалении {filename}: {e}")

        print(f"Очистка завершена. Удалено файлов: {deleted_files_count}")

    except Exception as e:
        print(f"Ошибка при очистке: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    clean_old_images()