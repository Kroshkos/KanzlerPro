import pytest

def test_a_kwargs(db):
    from pages.search_page import SearchPage
    class P:
        def __init__(self): self.controls=[]; self.session={}
        def update(self): pass
    sp = SearchPage(P())
    print("A ok")

def test_b_cards(db):
    import repositories as repo, os
    repo.add_student({"o_surname":"Иванов","o_name":"Иван","o_lastname":"Иваныч","o_group_name":"1А","o_course":1})
    conn = repo.sqlite3.connect if hasattr(repo,'sqlite3') else None
    import database
    c = database.connect_to_db()
    print("B count in db:", c.execute("SELECT COUNT(*) FROM students").fetchone()[0])
    print("B DB_PATH:", database.DB_PATH, "exists:", os.path.exists(database.DB_PATH))
    c.close()
    from pages.search_page import _search_like
    print("B like rows:", len(_search_like(surname="Иванов")))
