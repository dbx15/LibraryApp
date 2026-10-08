import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager


class LibraryDB:
    """Класс для работы с базой данных библиотеки"""
    
    def __init__(self, db_path='library.db'):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def connect(self):
        """Контекстный менеджер для соединения с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # доступ к полям по имени
        conn.execute("PRAGMA foreign_keys = ON")  # включаем внешние ключи
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_db(self):
        """Создание таблиц при первом запуске"""
        with self.connect() as conn:
            cur = conn.cursor()
            
            # Таблица книг
            cur.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    book_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    author      TEXT NOT NULL,
                    year        INTEGER,
                    genre       TEXT,
                    copies      INTEGER NOT NULL DEFAULT 1 CHECK (copies >= 0),
                    available   INTEGER NOT NULL DEFAULT 1 CHECK (available >= 0)
                )
            """)
            
            # Таблица читателей
            cur.execute("""
                CREATE TABLE IF NOT EXISTS readers (
                    reader_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    phone       TEXT,
                    email       TEXT,
                    reg_date    TEXT NOT NULL
                )
            """)
            
            # Таблица выдач (связь многие-ко-многим между книгами и читателями)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS loans (
                    loan_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id         INTEGER NOT NULL,
                    reader_id       INTEGER NOT NULL,
                    issue_date      TEXT NOT NULL,
                    due_date        TEXT NOT NULL,
                    return_date     TEXT,
                    status          TEXT NOT NULL DEFAULT 'issued'
                                    CHECK (status IN ('issued', 'returned')),
                    FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE,
                    FOREIGN KEY (reader_id) REFERENCES readers(reader_id) ON DELETE CASCADE
                )
            """)
            
            # Индексы для скорости поиска
            cur.execute("CREATE INDEX IF NOT EXISTS idx_books_title ON books(title)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_books_author ON books(author)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_loans_reader ON loans(reader_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_loans_book ON loans(book_id)")


class Library:
    """Бизнес-логика библиотеки"""
    
    LOAN_DAYS = 14  # срок выдачи
    
    def __init__(self, db_path='library.db'):
        self.db = LibraryDB(db_path)
    
    # ============ КНИГИ ============
    
    def add_book(self):
        print("\n--- Добавление книги ---")
        title = input("Название: ").strip()
        if not title:
            print("Название обязательно!")
            return
        author = input("Автор: ").strip()
        year_str = input("Год издания: ").strip()
        genre = input("Жанр: ").strip()
        copies_str = input("Количество экземпляров [1]: ").strip() or "1"
        
        try:
            year = int(year_str) if year_str else None
            copies = int(copies_str)
            if copies < 1:
                raise ValueError
        except ValueError:
            print("Ошибка: год и количество должны быть положительными числами!")
            return
        
        with self.db.connect() as conn:
            cur = conn.execute("""
                INSERT INTO books (title, author, year, genre, copies, available)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, author, year, genre, copies, copies))
            book_id = cur.lastrowid
        
        print(f"✓ Книга добавлена (ID: {book_id})")
    
    def show_all_books(self, only_available=False):
        print("\n--- Список книг ---")
        query = "SELECT * FROM books"
        if only_available:
            query += " WHERE available > 0"
        query += " ORDER BY title"
        
        with self.db.connect() as conn:
            rows = conn.execute(query).fetchall()
        
        if not rows:
            print("Книг нет.")
            return
        
        for row in rows:
            status = "✓ доступна" if row['available'] > 0 else "✗ все выданы"
            print(f"[{row['book_id']:>3}] «{row['title']}» — {row['author']} "
                  f"({row['year'] or '—'}) | Жанр: {row['genre'] or '—'} "
                  f"| Доступно: {row['available']}/{row['copies']} | {status}")
    
    def search_books(self):
        print("\n--- Поиск книг ---")
        query = input("Название / автор / жанр: ").strip()
        if not query:
            return
        pattern = f"%{query.lower()}%"
        
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT * FROM books
                WHERE LOWER(title) LIKE ?
                   OR LOWER(author) LIKE ?
                   OR LOWER(genre) LIKE ?
                ORDER BY title
            """, (pattern, pattern, pattern)).fetchall()
        
        if not rows:
            print("Ничего не найдено.")
            return
        
        print(f"Найдено: {len(rows)}")
        for row in rows:
            status = "✓" if row['available'] > 0 else "✗"
            print(f"  {status} [{row['book_id']}] «{row['title']}» — {row['author']} "
                  f"({row['available']}/{row['copies']})")
    
    def edit_book(self):
        print("\n--- Редактирование книги ---")
        book_id = self._input_int("ID книги: ")
        if book_id is None:
            return
        
        with self.db.connect() as conn:
            book = conn.execute("SELECT * FROM books WHERE book_id = ?",
                                (book_id,)).fetchone()
            if not book:
                print("Книга не найдена.")
                return
            
            print(f"Текущее: «{book['title']}» — {book['author']}, "
                  f"{book['year']}, {book['genre']}, копий: {book['copies']}")
            
            title = input(f"Название [{book['title']}]: ").strip() or book['title']
            author = input(f"Автор [{book['author']}]: ").strip() or book['author']
            year_s = input(f"Год [{book['year'] or ''}]: ").strip()
            year = int(year_s) if year_s else book['year']
            genre = input(f"Жанр [{book['genre'] or ''}]: ").strip() or book['genre']
            copies_s = input(f"Всего копий [{book['copies']}]: ").strip()
            new_copies = int(copies_s) if copies_s else book['copies']
            
            # пересчёт доступных копий с учётом уже выданных
            issued = book['copies'] - book['available']
            if new_copies < issued:
                print(f"Ошибка: на руках {issued} экз., нельзя уменьшить до {new_copies}")
                return
            
            conn.execute("""
                UPDATE books
                SET title=?, author=?, year=?, genre=?, copies=?, available=?
                WHERE book_id=?
            """, (title, author, year, genre, new_copies,
                  new_copies - issued, book_id))
        print("✓ Книга обновлена.")
    
    def delete_book(self):
        print("\n--- Удаление книги ---")
        book_id = self._input_int("ID книги: ")
        if book_id is None:
            return
        
        with self.db.connect() as conn:
            active = conn.execute("""
                SELECT COUNT(*) AS c FROM loans
                WHERE book_id = ? AND status = 'issued'
            """, (book_id,)).fetchone()['c']
            if active > 0:
                print(f"Нельзя удалить: книга на руках ({active} экз.)")
                return
            
            cur = conn.execute("DELETE FROM books WHERE book_id = ?", (book_id,))
            if cur.rowcount:
                print("✓ Книга удалена (вместе с историей выдач).")
            else:
                print("Книга не найдена.")
    
    # ============ ЧИТАТЕЛИ ============
    
    def add_reader(self):
        print("\n--- Регистрация читателя ---")
        name = input("ФИО: ").strip()
        if not name:
            print("ФИО обязательно!")
            return
        phone = input("Телефон: ").strip()
        email = input("Email: ").strip()
        reg_date = datetime.now().strftime('%Y-%m-%d')
        
        with self.db.connect() as conn:
            cur = conn.execute("""
                INSERT INTO readers (name, phone, email, reg_date)
                VALUES (?, ?, ?, ?)
            """, (name, phone, email, reg_date))
            reader_id = cur.lastrowid
        
        print(f"✓ Читатель зарегистрирован (ID: {reader_id})")
    
    def show_all_readers(self):
        print("\n--- Список читателей ---")
        with self.db.connect() as conn:
            readers = conn.execute("""
                SELECT r.*,
                       (SELECT COUNT(*) FROM loans l
                        WHERE l.reader_id = r.reader_id AND l.status = 'issued')
                       AS active_loans
                FROM readers r
                ORDER BY r.name
            """).fetchall()
        
        if not readers:
            print("Читателей нет.")
            return
        
        for r in readers:
            print(f"[{r['reader_id']:>3}] {r['name']} | тел.: {r['phone'] or '—'} "
                  f"| email: {r['email'] or '—'} | на руках: {r['active_loans']}")
    
    def show_reader_loans(self):
        print("\n--- Книги на руках у читателя ---")
        reader_id = self._input_int("ID читателя: ")
        if reader_id is None:
            return
        
        with self.db.connect() as conn:
            reader = conn.execute("SELECT * FROM readers WHERE reader_id = ?",
                                  (reader_id,)).fetchone()
            if not reader:
                print("Читатель не найден.")
                return
            
            loans = conn.execute("""
                SELECT l.*, b.title, b.author
                FROM loans l
                JOIN books b ON b.book_id = l.book_id
                WHERE l.reader_id = ? AND l.status = 'issued'
                ORDER BY l.due_date
            """, (reader_id,)).fetchall()
        
        print(f"\nЧитатель: {reader['name']}")
        if not loans:
            print("  Нет книг на руках.")
            return
        
        today = datetime.now().date()
        for l in loans:
            due = datetime.strptime(l['due_date'], '%Y-%m-%d').date()
            overdue = (today - due).days
            mark = f"⚠ просрочка {overdue} дн." if overdue > 0 else "ok"
            print(f"  [{l['loan_id']}] «{l['title']}» — {l['author']} "
                  f"| выдана {l['issue_date']} | вернуть до {l['due_date']} ({mark})")
    
    # ============ ВЫДАЧА / ВОЗВРАТ ============
    
    def issue_book(self):
        print("\n--- Выдача книги ---")
        reader_id = self._input_int("ID читателя: ")
        book_id = self._input_int("ID книги: ")
        if reader_id is None or book_id is None:
            return
        
        with self.db.connect() as conn:
            reader = conn.execute("SELECT * FROM readers WHERE reader_id = ?",
                                  (reader_id,)).fetchone()
            if not reader:
                print("Читатель не найден.")
                return
            
            book = conn.execute("SELECT * FROM books WHERE book_id = ?",
                                (book_id,)).fetchone()
            if not book:
                print("Книга не найдена.")
                return
            
            if book['available'] <= 0:
                print("Нет доступных экземпляров.")
                return
            
            # проверка, что читатель уже не держит эту книгу
            dup = conn.execute("""
                SELECT 1 FROM loans
                WHERE reader_id = ? AND book_id = ? AND status = 'issued'
            """, (reader_id, book_id)).fetchone()
            if dup:
                print("Этот читатель уже держит данную книгу.")
                return
            
            issue_date = datetime.now().strftime('%Y-%m-%d')
            due_date = (datetime.now() + timedelta(days=self.LOAN_DAYS)).strftime('%Y-%m-%d')
            
            conn.execute("""
                INSERT INTO loans (book_id, reader_id, issue_date, due_date, status)
                VALUES (?, ?, ?, ?, 'issued')
            """, (book_id, reader_id, issue_date, due_date))
            
            conn.execute("""
                UPDATE books SET available = available - 1 WHERE book_id = ?
            """, (book_id,))
        
        print(f"✓ Книга «{book['title']}» выдана читателю {reader['name']}")
        print(f"  Срок возврата: {due_date}")
    
    def return_book(self):
        print("\n--- Возврат книги ---")
        reader_id = self._input_int("ID читателя: ")
        if reader_id is None:
            return
        
        with self.db.connect() as conn:
            loans = conn.execute("""
                SELECT l.*, b.title FROM loans l
                JOIN books b ON b.book_id = l.book_id
                WHERE l.reader_id = ? AND l.status = 'issued'
                ORDER BY l.issue_date
            """, (reader_id,)).fetchall()
            
            if not loans:
                print("У читателя нет книг на руках.")
                return
            
            print("\nКниги на руках:")
            for l in loans:
                print(f"  [{l['loan_id']}] «{l['title']}» (до {l['due_date']})")
            
            loan_id = self._input_int("ID записи для возврата: ")
            if loan_id is None:
                return
            
            loan = next((l for l in loans if l['loan_id'] == loan_id), None)
            if not loan:
                print("Неверный ID записи.")
                return
            
            # проверка просрочки
            due = datetime.strptime(loan['due_date'], '%Y-%m-%d').date()
            today = datetime.now().date()
            if today > due:
                days_late = (today - due).days
                fine = days_late * 5  # 5 руб./день
                print(f"⚠ Просрочка {days_late} дн. Штраф: {fine} руб.")
            
            return_date = datetime.now().strftime('%Y-%m-%d')
            conn.execute("""
                UPDATE loans SET status = 'returned', return_date = ?
                WHERE loan_id = ?
            """, (return_date, loan_id))
            
            conn.execute("""
                UPDATE books SET available = available + 1 WHERE book_id = ?
            """, (loan['book_id'],))
        
        print(f"✓ Книга «{loan['title']}» возвращена.")
    
    # ============ ОТЧЁТЫ ============
    
    def show_overdue(self):
        print("\n--- Просроченные книги ---")
        today = datetime.now().strftime('%Y-%m-%d')
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT l.*, b.title, b.author, r.name AS reader_name, r.phone
                FROM loans l
                JOIN books b ON b.book_id = l.book_id
                JOIN readers r ON r.reader_id = l.reader_id
                WHERE l.status = 'issued' AND l.due_date < ?
                ORDER BY l.due_date
            """, (today,)).fetchall()
        
        if not rows:
            print("Просрочек нет. ✓")
            return
        
        for r in rows:
            due = datetime.strptime(r['due_date'], '%Y-%m-%d').date()
            days_late = (datetime.now().date() - due).days
            print(f"  [{r['loan_id']}] «{r['title']}» — {r['reader_name']} "
                  f"(тел. {r['phone'] or '—'}) | просрочка {days_late} дн.")
    
    def show_popular_books(self, limit=10):
        print(f"\n--- Топ-{limit} популярных книг ---")
        with self.db.connect() as conn:
            rows = conn.execute("""
                SELECT b.book_id, b.title, b.author,
                       COUNT(l.loan_id) AS times_issued
                FROM books b
                LEFT JOIN loans l ON l.book_id = b.book_id
                GROUP BY b.book_id
                ORDER BY times_issued DESC, b.title
                LIMIT ?
            """, (limit,)).fetchall()
        
        if not rows or all(r['times_issued'] == 0 for r in rows):
            print("Статистики пока нет.")
            return
        
        for i, r in enumerate(rows, 1):
            print(f"  {i}. «{r['title']}» — {r['author']} (выдавалась {r['times_issued']} раз)")
    
    def show_stats(self):
        print("\n--- Статистика библиотеки ---")
        with self.db.connect() as conn:
            books_total = conn.execute("SELECT COUNT(*) c FROM books").fetchone()['c']
            copies_total = conn.execute("SELECT COALESCE(SUM(copies),0) c FROM books").fetchone()['c']
            readers_total = conn.execute("SELECT COUNT(*) c FROM readers").fetchone()['c']
            on_hands = conn.execute(
                "SELECT COUNT(*) c FROM loans WHERE status='issued'").fetchone()['c']
            loans_total = conn.execute("SELECT COUNT(*) c FROM loans").fetchone()['c']
        
        print(f"  Книг (наименований): {books_total}")
        print(f"  Всего экземпляров:   {copies_total}")
        print(f"  Читателей:           {readers_total}")
        print(f"  Сейчас на руках:     {on_hands}")
        print(f"  Всего выдач:         {loans_total}")
    
    # ============ ВСПОМОГАТЕЛЬНОЕ ============
    
    @staticmethod
    def _input_int(prompt):
        try:
            return int(input(prompt).strip())
        except ValueError:
            print("Ошибка: нужно целое число.")
            return None
    
    # ============ МЕНЮ ============
    
    def menu(self):
        actions = {
            '1': ("Показать все книги", self.show_all_books),
            '2': ("Показать доступные книги", lambda: self.show_all_books(only_available=True)),
            '3': ("Добавить книгу", self.add_book),
            '4': ("Редактировать книгу", self.edit_book),
            '5': ("Удалить книгу", self.delete_book),
            '6': ("Поиск книги", self.search_books),
            '7': ("Показать читателей", self.show_all_readers),
            '8': ("Зарегистрировать читателя", self.add_reader),
            '9': ("Книги на руках у читателя", self.show_reader_loans),
            '10': ("Выдать книгу", self.issue_book),
            '11': ("Принять возврат", self.return_book),
            '12': ("Просроченные книги", self.show_overdue),
            '13': ("Топ популярных книг", self.show_popular_books),
            '14': ("Статистика", self.show_stats),
        }
        
        while True:
            print("\n" + "=" * 55)
            print("        ИС «БИБЛИОТЕКА» (SQLite)")
            print("=" * 55)
            for key, (title, _) in actions.items():
                print(f"  {key:>2}. {title}")
            print("   0. Выход")
            print("=" * 55)
            
            choice = input("Выберите пункт: ").strip()
            
            if choice == '0':
                print("До свидания!")
                break
            elif choice in actions:
                try:
                    actions[choice][1]()
                except Exception as e:
                    print(f"Ошибка выполнения: {e}")
            else:
                print("Неверный пункт меню.")


if __name__ == '__main__':
    library = Library('library.db')
    library.menu()