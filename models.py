from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from encryption import encrypt_data, decrypt_data, compute_hmac_signature
from integrity import format_exam_payload, calculate_chain_hash, GENESIS_PREV_HASH

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student') # guest, student, instructor, admin, owner
    full_name = db.Column(db.String(120), nullable=False)
    _phone = db.Column('phone', db.String(256), nullable=True) # Зашифровано Fernet
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Связи
    student_profile = db.relationship('StudentProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    instructor_profile = db.relationship('InstructorProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    sessions = db.relationship('UserSession', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reviews_left = db.relationship('Review', foreign_keys='Review.student_id', backref='student', lazy='dynamic')
    reviews_received = db.relationship('Review', foreign_keys='Review.instructor_id', backref='instructor', lazy='dynamic')

    # Прозрачное шифрование телефона (152-ФЗ)
    @property
    def phone(self):
        return decrypt_data(self._phone)

    @phone.setter
    def phone(self, value):
        self._phone = encrypt_data(value)

    def set_password(self, password):
        """Хеширование пароля с криптографической солью PBKDF2-HMAC-SHA256."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def can_manage_user(self, target_user):
        """Проверка прав администрирования по ролевой модели RBAC."""
        if self.role == 'owner':
            return True
        if self.role == 'admin':
            if target_user.id == self.id:
                return True
            return target_user.role not in ('admin', 'owner')
        return False

    def is_student(self):
        return self.role == 'student'

    def is_instructor(self):
        return self.role == 'instructor'

    def is_admin(self):
        return self.role in ('admin', 'owner')

    def is_owner(self):
        return self.role == 'owner'


class StudentProfile(db.Model):
    __tablename__ = 'student_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    category = db.Column(db.String(10), default='B')
    _passport_data = db.Column('passport_data', db.String(256), nullable=True) # Зашифровано Fernet
    _medical_cert = db.Column('medical_cert', db.String(256), nullable=True)   # Зашифровано Fernet
    theory_hours = db.Column(db.Integer, default=0)
    practice_hours = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default='studying') # studying, admitted_to_exam, graduated, expelled

    # Прозрачное шифрование персональных данных
    @property
    def passport_data(self):
        return decrypt_data(self._passport_data)

    @passport_data.setter
    def passport_data(self, value):
        self._passport_data = encrypt_data(value)

    @property
    def medical_cert(self):
        return decrypt_data(self._medical_cert)

    @medical_cert.setter
    def medical_cert(self, value):
        self._medical_cert = encrypt_data(value)


class InstructorProfile(db.Model):
    __tablename__ = 'instructor_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)
    car_model = db.Column(db.String(80), nullable=False, default='Hyundai Solaris')
    car_number = db.Column(db.String(20), nullable=False, default='А123ВС46')
    transmission = db.Column(db.String(20), nullable=False, default='МКПП') # МКПП или АКПП
    experience_years = db.Column(db.Integer, default=5)
    hourly_rate = db.Column(db.Float, default=1200.0)
    bio = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, default=5.0)


class DrivingSlot(db.Model):
    __tablename__ = 'driving_slots'

    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_booked = db.Column(db.Boolean, default=False, nullable=False)
    price = db.Column(db.Float, nullable=False, default=1200.0)

    instructor = db.relationship('User', foreign_keys=[instructor_id], backref='teaching_slots')
    booking = db.relationship('DrivingBooking', backref='slot', uselist=False, cascade='all, delete-orphan')


class DrivingBooking(db.Model):
    __tablename__ = 'driving_bookings'

    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('driving_slots.id', ondelete='CASCADE'), nullable=False, unique=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = db.Column(db.String(20), default='booked') # booked, completed, cancelled
    instructor_notes = db.Column(db.Text, nullable=True) # Санитизируется через bleach
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    student = db.relationship('User', foreign_keys=[student_id], backref='my_bookings')
    instructor = db.relationship('User', foreign_keys=[instructor_id], backref='instructor_bookings')


class PddQuestion(db.Model):
    __tablename__ = 'pdd_questions'

    id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.Integer, nullable=False, index=True)
    question_number = db.Column(db.Integer, nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_1 = db.Column(db.Text, nullable=False)
    option_2 = db.Column(db.Text, nullable=False)
    option_3 = db.Column(db.Text, nullable=True)
    option_4 = db.Column(db.Text, nullable=True)
    correct_option = db.Column(db.Integer, nullable=False) # 1, 2, 3, 4
    explanation = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(100), default='Общие положения')


class InternalExam(db.Model):
    """
    Ключевая защищенная таблица: журнал внутренних экзаменов автошколы.
    Каждая запись защищена HMAC-подписью и связана в блокчейн-цепочку хешей.
    """
    __tablename__ = 'internal_exams'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    exam_type = db.Column(db.String(20), nullable=False) # theory или practice
    score = db.Column(db.Integer, nullable=False)         # theory: 0-20 верных ответов; practice: 0-15 штрафных баллов
    is_passed = db.Column(db.Boolean, nullable=False)
    notes = db.Column(db.Text, nullable=True)            # Санитизируется bleach
    passed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Поля подсистемы защиты от фальсификации (HMAC + Hash-Chaining)
    prev_hash = db.Column(db.String(64), nullable=False)
    record_hash = db.Column(db.String(64), nullable=False)
    signature = db.Column(db.String(64), nullable=False)

    student = db.relationship('User', foreign_keys=[student_id], backref='exam_results')
    examiner = db.relationship('User', foreign_keys=[examiner_id], backref='conducted_exams')

    def sign_and_seal(self, prev_hash: str = None):
        """Генерирует криптографическую подпись и блокчейн-хеш записи."""
        if not prev_hash:
            prev_hash = GENESIS_PREV_HASH
        self.prev_hash = prev_hash

        payload = format_exam_payload(
            student_id=self.student_id,
            exam_type=self.exam_type,
            score=self.score,
            is_passed=self.is_passed,
            passed_at=self.passed_at or datetime.now(timezone.utc),
            examiner_id=self.examiner_id or 0
        )
        self.record_hash = calculate_chain_hash(payload, self.prev_hash)
        self.signature = compute_hmac_signature(payload)


class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    instructor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False, default=5)
    comment = db.Column(db.Text, nullable=False) # Санитизируется через bleach
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class UserSession(db.Model):
    __tablename__ = 'user_sessions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(256), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)

    def is_expired(self):
        # Безопасное сравнение временных меток с учетом таймзоны
        now = datetime.now(timezone.utc)
        target = self.expires_at
        if target.tzinfo is None:
            now = datetime.utcnow()
        return now > target


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    event_type = db.Column(db.String(50), nullable=False) # LOGIN, LOGOUT, EXAM_RECORD, INTEGRITY_SCAN, TAMPER_ALERT, etc.
    description = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='audit_actions')
