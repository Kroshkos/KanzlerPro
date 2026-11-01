"""Юнит-тесты модуля security: хеширование и проверка паролей.

Это критичный код безопасности — раньше он не был покрыт совсем.
"""

import security


class TestHashPassword:
    def test_format(self):
        h = security.hash_password("secret")
        algo, iterations, salt_hex, hash_hex = h.split("$")
        assert algo == "pbkdf2_sha256"
        assert int(iterations) == 200_000
        assert len(bytes.fromhex(salt_hex)) == 16
        assert len(bytes.fromhex(hash_hex)) == 32  # sha256

    def test_unique_salts(self):
        """Одинаковые пароли дают разные хеши (соль случайна)."""
        assert security.hash_password("pwd") != security.hash_password("pwd")

    def test_is_hashed(self):
        assert security.is_hashed(security.hash_password("x"))
        assert not security.is_hashed("plain_old_password")
        assert not security.is_hashed("")


class TestVerifyPassword:
    def test_correct(self):
        h = security.hash_password("Вход123!")
        assert security.verify_password("Вход123!", h) is True

    def test_incorrect(self):
        h = security.hash_password("Вход123!")
        assert security.verify_password("wrong", h) is False

    def test_empty_stored(self):
        assert security.verify_password("any", "") is False

    def test_legacy_plaintext_matches(self):
        """Легаси-запись с открытым паролем всё ещё пускает владельца."""
        assert security.verify_password("oldpass", "oldpass") is True
        assert security.verify_password("newpass", "oldpass") is False

    def test_foreign_algorithm_rejected(self):
        fake = "bcrypt$10$aabb$ccdd"
        assert security.verify_password("x", fake) is False

    def test_malformed_hash_no_crash(self):
        """Молчаливый except в verify_password не должен маскировать ошибку формата."""
        assert security.verify_password("x", "pbkdf2_sha256$notanumber$zz$yy") is False


class TestNeedsMigration:
    def test_plain_needs(self):
        assert security.needs_migration("plaintext") is True

    def test_hash_does_not_need(self):
        assert security.needs_migration(security.hash_password("p")) is False

    def test_empty(self):
        assert security.needs_migration("") is False
