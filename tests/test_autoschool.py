import pytest
from datetime import datetime, timezone, timedelta, date, time
from app import create_app
from config import Config
from extensions import db
from models import User, StudentProfile, InstructorProfile, DrivingSlot, DrivingBooking, InternalExam, UserSession
from encryption import encrypt_data, decrypt_data, compute_hmac_signature, verify_hmac_signature
from integrity import check_exam_ledger_integrity, GENESIS_PREV_HASH
import bleach

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False # Отключаем для некоторых прямых unit-тестов контроллеров

@pytest.fixture
def app():
    test_app = create_app(TestConfig)
    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

# =========================================================================
# 1. ТЕСТИРОВАНИЕ КРИПТОГРАФИЧЕСКИХ МЕХАНИЗМОВ И ЗАЩИТЫ ПДн (152-ФЗ)
# =========================================================================

def test_password_hashing():
    """Проверка соленого хеширования паролей PBKDF2-HMAC-SHA256."""
    u1 = User(email='user1@test.ru', full_name='Иванов И.И.')
    u2 = User(email='user2@test.ru', full_name='Петров П.П.')
    
    # Одинаковые открытые пароли
    u1.set_password('SecretPass123')
    u2.set_password('SecretPass123')
    
    # Проверка: разные криптографические соли гарантируют разные хеши в БД
    assert u1.password_hash != u2.password_hash
    assert u1.check_password('SecretPass123') is True
    assert u1.check_password('WrongPass') is False

def test_fernet_encryption_at_rest(app):
    """Проверка симметричного шифрования Fernet персональных данных в БД."""
    with app.app_context():
        u = User(email='crypto@test.ru', full_name='Сидоров С.С.', role='student')
        u.set_password('pass123')
        plain_phone = '+7 (999) 777-88-99'
        u.phone = plain_phone
        db.session.add(u)
        db.session.flush()

        sp = StudentProfile(user_id=u.id)
        plain_passport = 'Серия 3814 № 123456'
        sp.passport_data = plain_passport
        db.session.add(sp)
        db.session.commit()

        # 1. При чтении через @property возвращается расшифрованный текст
        loaded_user = User.query.get(u.id)
        assert loaded_user.phone == plain_phone
        assert loaded_user.student_profile.passport_data == plain_passport

        # 2. Физически в базе данных хранятся Base64-криптограммы (at rest)
        raw_phone = loaded_user._phone
        raw_passport = loaded_user.student_profile._passport_data
        assert raw_phone != plain_phone
        assert plain_phone not in raw_phone
        assert raw_passport != plain_passport
        assert plain_passport not in raw_passport

# =========================================================================
# 2. ТЕСТИРОВАНИЕ ЗАЩИТЫ ЭКЗАМЕНОВ ОТ ФАЛЬСИФИКАЦИИ (HMAC И HASH CHAINING)
# =========================================================================

def test_exam_hmac_and_chain_validity(app):
    """Проверка генерации валидной HMAC-подписи и непрерывности цепочки."""
    with app.app_context():
        u = User(email='stud_exam@test.ru', full_name='Курсант Экзаменов', role='student')
        u.set_password('p123')
        db.session.add(u)
        db.session.commit()

        # Создаем 3 последовательных экзамена
        e1 = InternalExam(student_id=u.id, exam_type='theory', score=19, is_passed=True, passed_at=datetime.now(timezone.utc))
        e1.sign_and_seal(GENESIS_PREV_HASH)
        db.session.add(e1)
        db.session.commit()

        e2 = InternalExam(student_id=u.id, exam_type='practice', score=3, is_passed=True, passed_at=datetime.now(timezone.utc))
        e2.sign_and_seal(e1.record_hash)
        db.session.add(e2)
        db.session.commit()

        exams = InternalExam.query.order_by(InternalExam.id).all()
        report = check_exam_ledger_integrity(exams)

        assert report['is_healthy'] is True
        assert report['total'] == 2
        assert report['valid_count'] == 2
        assert report['tampered_count'] == 0
        assert report['chain_breaks_count'] == 0

def test_tamper_detection_in_exam_score(app):
    """Пентест: обнаружение подделки оценки экзамена в базе данных."""
    with app.app_context():
        u = User(email='tamper_target@test.ru', full_name='Студент Фальсификат', role='student')
        u.set_password('p123')
        db.session.add(u)
        db.session.commit()

        # Студент не сдал экзамен (12 верных ответов)
        exam = InternalExam(student_id=u.id, exam_type='theory', score=12, is_passed=False, passed_at=datetime.now(timezone.utc))
        exam.sign_and_seal(GENESIS_PREV_HASH)
        db.session.add(exam)
        db.session.commit()

        # Злоумышленник выполняет несанкционированный UPDATE в СУБД: ставит «СДАН» и 20 баллов
        exam.score = 20
        exam.is_passed = True
        # Подпись exam.signature НЕ обновляется!
        db.session.commit()

        # Запуск сканера контроля целостности
        exams = InternalExam.query.order_by(InternalExam.id).all()
        report = check_exam_ledger_integrity(exams)

        # Сканер ОБЯЗАН зафиксировать компрометацию!
        assert report['is_healthy'] is False
        assert report['tampered_count'] == 1
        assert report['tampered_records'][0]['id'] == exam.id
        assert 'Подделка данных протокола' in report['tampered_records'][0]['reason']

def test_broken_hash_chain_detection(app):
    """Пентест: обнаружение разрыва блокчейн-цепочки хешей при вставке или удалении."""
    with app.app_context():
        u = User(email='chain_target@test.ru', full_name='Студент Цепочка', role='student')
        u.set_password('p123')
        db.session.add(u)
        db.session.commit()

        e1 = InternalExam(student_id=u.id, exam_type='theory', score=18, is_passed=True, passed_at=datetime.now(timezone.utc))
        e1.sign_and_seal(GENESIS_PREV_HASH)
        db.session.add(e1)
        db.session.commit()

        # Создаем вторую запись с фиктивным prev_hash (симуляция разрыва)
        e2 = InternalExam(student_id=u.id, exam_type='practice', score=2, is_passed=True, passed_at=datetime.now(timezone.utc))
        e2.sign_and_seal("fake_broken_hash_value_1234567890abcdef1234567890abcdef12345678")
        db.session.add(e2)
        db.session.commit()

        exams = InternalExam.query.order_by(InternalExam.id).all()
        report = check_exam_ledger_integrity(exams)

        assert report['is_healthy'] is False
        assert report['chain_breaks_count'] == 1
        assert 'разрыв блокчейн-цепочки' in report['broken_chains'][0]['reason']

# =========================================================================
# 3. ТЕСТИРОВАНИЕ ЗАЩИТЫ ОТ XSS И ИНЪЕКЦИЙ
# =========================================================================

def test_stored_xss_sanitization_with_bleach():
    """Тест нейтрализации вредоносных HTML/JS инъекций (Stored XSS)."""
    malicious_inputs = [
        "<script>alert('HACKED')</script>Отличный инструктор!",
        "<img src=x onerror=alert(document.cookie)>Внимательный преподаватель",
        "<a href='javascript:void(0)' onclick='stealData()'>Кликни сюда</a>",
        "<iframe src='http://attacker.com'></iframe>Хороший автодром"
    ]

    for payload in malicious_inputs:
        cleaned = bleach.clean(payload, tags=[], strip=True)
        assert "<script>" not in cleaned
        assert "<img" not in cleaned
        assert "onerror" not in cleaned
        assert "<iframe>" not in cleaned
        assert "javascript:" not in cleaned

# =========================================================================
# 4. ТЕСТИРОВАНИЕ РОЛЕВОЙ МОДЕЛИ RBAC И IDOR
# =========================================================================

def test_rbac_management_hierarchy():
    """Проверка матрицы управления пользователями (can_manage_user)."""
    owner = User(role='owner')
    admin1 = User(role='admin', id=10)
    admin2 = User(role='admin', id=11)
    student = User(role='student', id=20)
    instructor = User(role='instructor', id=30)

    # Владелец может управлять всеми
    assert owner.can_manage_user(admin1) is True
    assert owner.can_manage_user(student) is True

    # Администратор может управлять студентами и инструкторами
    assert admin1.can_manage_user(student) is True
    assert admin1.can_manage_user(instructor) is True
    # Администратор может редактировать свой профиль
    assert admin1.can_manage_user(admin1) is True
    # Администратор НЕ может изменять других администраторов или владельца!
    assert admin1.can_manage_user(admin2) is False
    assert admin1.can_manage_user(owner) is False

    # Студент не может администрировать никого
    assert student.can_manage_user(instructor) is False

# =========================================================================
# 5. ТЕСТИРОВАНИЕ СЕССИОННОЙ БЕЗОПАСНОСТИ
# =========================================================================

def test_session_expiration_and_revocation():
    """Проверка контроля срока жизни сессионного токена и его отзыва."""
    now = datetime.now(timezone.utc)
    # 1. Свежая сессия
    active_sess = UserSession(token='valid_token', expires_at=now + timedelta(minutes=15), is_active=True)
    assert active_sess.is_expired() is False

    # 2. Просроченная сессия (более 15 минут)
    expired_sess = UserSession(token='old_token', expires_at=now - timedelta(seconds=1), is_active=True)
    assert expired_sess.is_expired() is True

    # 3. Отозванная администратором сессия
    revoked_sess = UserSession(token='revoked_token', expires_at=now + timedelta(minutes=10), is_active=False)
    assert revoked_sess.is_active is False
