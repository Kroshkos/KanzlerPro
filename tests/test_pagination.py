"""Тесты пагинации списка курсантов (пункт C-1 бэклога).

Проверяют обратную совместимость get_students() (без параметров — все
записи) и корректность LIMIT/OFFSET-страниц, а также чистовную математику
количества страниц.
"""


def _seed_students(db, n):
    for i in range(1, n + 1):
        db.execute_query(
            "INSERT INTO students (o_surname, o_name, o_lastname, o_course,"
            " o_group_name) VALUES (?, 'И', 'И', 1, 'Г-1')",
            params=(f"Фамилия{i:03d}",))


def test_get_students_no_limit_returns_all(db):
    """get_students() без limit сохраняет прежнее поведение — полный список."""
    _seed_students(db, 7)
    assert len(db.get_students()) == 7


def test_get_students_pages_are_disjoint_and_complete(db):
    _seed_students(db, db.STUDENTS_PAGE_SIZE * 2 + 5)
    total = db.count_students()
    assert total == db.STUDENTS_PAGE_SIZE * 2 + 5

    page1 = db.get_students(limit=db.STUDENTS_PAGE_SIZE, offset=0)
    page2 = db.get_students(limit=db.STUDENTS_PAGE_SIZE,
                            offset=db.STUDENTS_PAGE_SIZE)
    page3 = db.get_students(limit=db.STUDENTS_PAGE_SIZE,
                            offset=db.STUDENTS_PAGE_SIZE * 2)
    assert len(page1) == db.STUDENTS_PAGE_SIZE
    assert len(page2) == db.STUDENTS_PAGE_SIZE
    assert len(page3) == 5

    ids = [r["id"] for r in page1 + page2 + page3]
    assert len(ids) == len(set(ids)), "страницы не должны пересекаться"
    assert len(ids) == total, "все записи покрыты страницами"


def test_get_students_offset_beyond_end_is_empty(db):
    _seed_students(db, 3)
    assert db.get_students(limit=10, offset=100) == []


def test_count_students_empty_table(db):
    assert db.count_students() == 0


def test_total_pages_ceil_math():
    """Математика числа страниц из ShowStudentsPage: ceil(total/page_size)."""
    page_size = 50
    for total, expected in [(0, 1), (1, 1), (50, 1), (51, 2), (100, 2), (101, 3)]:
        pages = max(1, -(-total // page_size))
        assert pages == expected, f"total={total}"


# ---------- UI: листание и сохранение выбора между страницами ----------

def _seed_ui(db, n):
    for i in range(1, n + 1):
        db.execute_query(
            "INSERT INTO students (o_surname, o_name, o_lastname, o_course,"
            " o_group_name) VALUES (?, 'И', 'И', 1, 'Г-1')",
            params=(f"Фамилия{i:03d}",))


class _PageStub:
    def __init__(self):
        self.session = {"role": "admin"}

    def update(self):
        pass

    def add(self, *c):
        pass


def test_show_students_paging_and_selection_kept(db):
    from pages.kadri_page import ShowStudentsPage

    _seed_ui(db, db.STUDENTS_PAGE_SIZE + 3)
    page = ShowStudentsPage(_PageStub())
    assert page.total_pages == 2
    assert len(page.data_grid.rows) == db.STUDENTS_PAGE_SIZE
    assert page.prev_button.disabled and not page.next_button.disabled

    # отмечаем курсанта на 1-й странице
    first_id = int(min(page.checkboxes))  # минимальный id на 1-й странице
    page.checkboxes[int(first_id)].value = True

    page.next_page_click(None)
    assert page.current_page == 1
    assert len(page.data_grid.rows) == 3
    assert not page.prev_button.disabled and page.next_button.disabled
    # выбор сохранился при листании
    assert page._selected_ids() == [int(first_id)]

    page.prev_page_click(None)
    assert page.current_page == 0
    assert len(page.data_grid.rows) == db.STUDENTS_PAGE_SIZE
