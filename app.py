import secrets
from datetime import datetime, timezone, timedelta, date, time
from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
import bleach

from config import Config
from extensions import db, csrf, login_manager
from models import (User, StudentProfile, InstructorProfile, DrivingSlot,
                    DrivingBooking, PddQuestion, InternalExam, Review,
                    UserSession, AuditLog)
from forms import (LoginForm, RegisterForm, ProfileForm, DrivingSlotForm,
                   PracticalExamForm, ReviewForm, UserEditAdminForm)
from decorators import role_required
from integrity import check_exam_ledger_integrity, GENESIS_PREV_HASH

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Инициализация расширений
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    # Регистрация полезных глобальных функций в шаблонизаторе Jinja
    app.jinja_env.globals.update(int=int, str=str, len=len)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    def log_security_event(event_type: str, description: str, user_id: int = None):
        """Вспомогательная функция аудита безопасности."""
        try:
            uid = user_id or (current_user.id if current_user.is_authenticated else None)
            ip = request.remote_addr or '127.0.0.1'
            log = AuditLog(user_id=uid, event_type=event_type, description=description, ip_address=ip)
            db.session.add(log)
            db.session.commit()
        except Exception:
            db.session.rollback()

    # --- ПЕРЕХВАТЧИК СЕССИЙ (SESSION LIFETIME & REVOCATION) ---
    @app.before_request
    def validate_user_session():
        # Исключаем статику и страницы аутентификации
        if request.endpoint in ('static', 'logout', 'login', 'register'):
            return

        if current_user.is_authenticated:
            token = session.get('auth_token')
            if not token:
                logout_user()
                flash('Сессия не найдена. Пожалуйста, выполните вход повторно.', 'warning')
                return redirect(url_for('login'))

            user_sess = UserSession.query.filter_by(token=token).first()
            if not user_sess or not user_sess.is_active:
                logout_user()
                flash('Ваша сессия была завершена администратором.', 'danger')
                return redirect(url_for('login'))

            if user_sess.is_expired():
                user_sess.is_active = False
                db.session.commit()
                logout_user()
                flash('Срок действия сессионного токена (15 минут) истек.', 'info')
                return redirect(url_for('login'))

    # --- КОНТЕКСТНЫЕ ПРОЦЕССОРЫ ДЛЯ ШАБЛОНОВ ---
    @app.context_processor
    def inject_now():
        return {'now': datetime.now(timezone.utc)}

    # --- ПУБЛИЧНЫЕ МАРШРУТЫ ---
    @app.route('/')
    def index():
        instructors = InstructorProfile.query.join(User).limit(6).all()
        total_students = User.query.filter_by(role='student').count()
        total_instructors = User.query.filter_by(role='instructor').count()
        total_exams = InternalExam.query.count()
        passed_exams = InternalExam.query.filter_by(is_passed=True).count()
        pass_rate = round((passed_exams / total_exams * 100), 1) if total_exams > 0 else 94.5

        return render_template('index.html',
                               instructors=instructors,
                               total_students=total_students,
                               total_instructors=total_instructors,
                               total_exams=total_exams,
                               pass_rate=pass_rate)

    @app.route('/about')
    def about():
        return render_template('about.html')

    # --- АУТЕНТИФИКАЦИЯ И РЕГИСТРАЦИЯ ---
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        form = LoginForm()
        if form.validate_on_submit():
            email = form.email.data.strip().lower()
            user = User.query.filter_by(email=email).first()

            if user and user.check_password(form.password.data):
                login_user(user, remember=form.remember_me.data)

                # Создание защищенного сессионного токена в БД
                token = secrets.token_urlsafe(32)
                session['auth_token'] = token
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

                user_sess = UserSession(
                    user_id=user.id,
                    token=token,
                    ip_address=request.remote_addr or '127.0.0.1',
                    user_agent=(request.user_agent.string[:250] if request.user_agent else 'Unknown'),
                    is_active=True,
                    expires_at=expires_at
                )
                db.session.add(user_sess)
                db.session.commit()

                log_security_event('LOGIN_SUCCESS', f'Успешный вход пользователя {user.email} (роль: {user.role})', user.id)
                flash(f'Добро пожаловать, {user.full_name}!', 'success')

                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            else:
                log_security_event('LOGIN_FAILED', f'Неудачная попытка входа для {email}')
                flash('Неверный адрес электронной почты или пароль.', 'danger')

        return render_template('auth/login.html', form=form)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        form = RegisterForm()
        if form.validate_on_submit():
            user = User(
                email=form.email.data.strip().lower(),
                full_name=form.full_name.data.strip(),
                role=form.role.data
            )
            user.set_password(form.password.data)
            user.phone = form.phone.data.strip() # Шифрование Fernet на лету
            db.session.add(user)
            db.session.flush()

            if user.role == 'student':
                profile = StudentProfile(user_id=user.id, category=form.category.data)
                db.session.add(profile)
            elif user.role == 'instructor':
                profile = InstructorProfile(user_id=user.id)
                db.session.add(profile)

            db.session.commit()
            log_security_event('REGISTER', f'Зарегистрирован новый пользователь {user.email} ({user.role})', user.id)
            flash('Регистрация успешно завершена! Теперь вы можете войти в систему.', 'success')
            return redirect(url_for('login'))

        return render_template('auth/register.html', form=form)

    @app.route('/logout')
    @login_required
    def logout():
        token = session.get('auth_token')
        if token:
            user_sess = UserSession.query.filter_by(token=token).first()
            if user_sess:
                user_sess.is_active = False
                db.session.commit()

        log_security_event('LOGOUT', f'Выход пользователя {current_user.email}', current_user.id)
        logout_user()
        session.pop('auth_token', None)
        flash('Вы успешно вышли из системы.', 'info')
        return redirect(url_for('index'))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        form = ProfileForm(
            full_name=current_user.full_name,
            phone=current_user.phone or ''
        )

        if current_user.is_student() and current_user.student_profile:
            if request.method == 'GET':
                form.passport_data.data = current_user.student_profile.passport_data or ''
                form.medical_cert.data = current_user.student_profile.medical_cert or ''

        if form.validate_on_submit():
            current_user.full_name = form.full_name.data.strip()
            current_user.phone = form.phone.data.strip()

            if current_user.is_student() and current_user.student_profile:
                if form.passport_data.data:
                    current_user.student_profile.passport_data = form.passport_data.data.strip()
                if form.medical_cert.data:
                    current_user.student_profile.medical_cert = form.medical_cert.data.strip()

            # Смена пароля
            if form.new_password.data:
                if not form.old_password.data or not current_user.check_password(form.old_password.data):
                    flash('Для изменения пароля необходимо верно ввести текущий пароль.', 'danger')
                    return render_template('profile.html', form=form)
                current_user.set_password(form.new_password.data)
                log_security_event('PASSWORD_CHANGE', f'Пользователь {current_user.email} сменил пароль')

            db.session.commit()
            flash('Данные профиля успешно обновлены.', 'success')
            return redirect(url_for('profile'))

        my_exams = InternalExam.query.filter_by(student_id=current_user.id).order_by(InternalExam.passed_at.desc()).all() if current_user.is_student() else []
        my_bookings = DrivingBooking.query.filter_by(student_id=current_user.id).order_by(DrivingBooking.created_at.desc()).all() if current_user.is_student() else []

        return render_template('profile.html', form=form, my_exams=my_exams, my_bookings=my_bookings)

    # --- ЗАПИСЬ НА ВОЖДЕНИЕ (DRIVING BOOKINGS & CALENDAR) ---
    @app.route('/driving')
    def driving_catalog():
        transmission = request.args.get('transmission')
        max_price = request.args.get('max_price', type=float)

        query = InstructorProfile.query.join(User)
        if transmission in ('МКПП', 'АКПП'):
            query = query.filter(InstructorProfile.transmission == transmission)
        if max_price:
            query = query.filter(InstructorProfile.hourly_rate <= max_price)

        instructors = query.all()
        return render_template('driving/index.html', instructors=instructors, selected_trans=transmission, max_price=max_price)

    @app.route('/driving/calendar')
    def driving_calendar():
        instructor_id = request.args.get('instructor_id', type=int)
        instructors = InstructorProfile.query.join(User).all()
        return render_template('driving/calendar.html', instructors=instructors, selected_instructor_id=instructor_id)

    @app.route('/api/slots')
    def api_slots():
        instructor_id = request.args.get('instructor_id', type=int)
        query = DrivingSlot.query.filter_by(is_booked=False)
        if instructor_id:
            query = query.filter_by(instructor_id=instructor_id)

        # Выбираем актуальные слоты (от сегодня на 30 дней вперед)
        today = date.today()
        query = query.filter(DrivingSlot.date >= today)
        slots = query.limit(300).all()

        events = []
        for s in slots:
            inst_name = s.instructor.full_name if s.instructor else "Инструктор"
            car = s.instructor.instructor_profile.car_model if (s.instructor and s.instructor.instructor_profile) else ""
            trans = s.instructor.instructor_profile.transmission if (s.instructor and s.instructor.instructor_profile) else ""

            events.append({
                'id': s.id,
                'title': f"{inst_name} ({car}, {trans}) - {int(s.price)}₽",
                'start': f"{s.date.isoformat()}T{s.start_time.strftime('%H:%M:%S')}",
                'end': f"{s.date.isoformat()}T{s.end_time.strftime('%H:%M:%S')}",
                'extendedProps': {
                    'slot_id': s.id,
                    'price': s.price,
                    'instructor': inst_name,
                    'car': f"{car} ({trans})"
                }
            })
        return jsonify(events)

    @app.route('/driving/book/<int:slot_id>', methods=['POST'])
    @login_required
    @role_required('student')
    def book_driving(slot_id):
        slot = DrivingSlot.query.get_or_404(slot_id)

        if slot.is_booked:
            flash('Данный слот уже забронирован другим курсантом.', 'danger')
            return redirect(url_for('driving_calendar'))

        # Защита от Price/Parameter Tampering: серверная проверка стоимости
        submitted_price = request.form.get('price', type=float)
        if submitted_price is not None and abs(submitted_price - slot.price) > 0.01:
            log_security_event('PRICE_TAMPERING_ATTEMPT',
                               f'Попытка манипуляции ценой слота #{slot.id}: передано {submitted_price}, в БД {slot.price}')
            flash('Попытка фальсификации стоимости занятия заблокирована!', 'danger')
            return redirect(url_for('driving_calendar'))

        slot.is_booked = True
        booking = DrivingBooking(
            slot_id=slot.id,
            student_id=current_user.id,
            instructor_id=slot.instructor_id,
            status='booked'
        )
        db.session.add(booking)
        db.session.commit()

        log_security_event('DRIVING_BOOKED', f'Курсант {current_user.email} забронировал слот #{slot.id} у инструктора #{slot.instructor_id}')
        flash('Вы успешно записались на вождение!', 'success')
        return redirect(url_for('profile'))

    @app.route('/driving/cancel/<int:booking_id>', methods=['POST'])
    @login_required
    def cancel_booking(booking_id):
        booking = DrivingBooking.query.get_or_404(booking_id)

        # Проверка IDOR: отменить может только сам курсант, инструктор этого занятия или админ
        if not (current_user.is_admin() or current_user.id in (booking.student_id, booking.instructor_id)):
            abort(403)

        booking.status = 'cancelled'
        if booking.slot:
            booking.slot.is_booked = False

        db.session.commit()
        log_security_event('BOOKING_CANCELLED', f'Бронирование #{booking.id} отменено пользователем {current_user.email}')
        flash('Запись на вождение отменена.', 'info')
        return redirect(request.referrer or url_for('profile'))

    # --- КАБИНЕТ ИНСТРУКТОРА ---
    @app.route('/instructor/slots', methods=['GET', 'POST'])
    @login_required
    @role_required('instructor', 'admin', 'owner')
    def instructor_slots():
        form = DrivingSlotForm()
        if form.validate_on_submit():
            slot = DrivingSlot(
                instructor_id=current_user.id,
                date=form.date.data,
                start_time=form.start_time.data,
                end_time=form.end_time.data,
                price=form.price.data,
                is_booked=False
            )
            db.session.add(slot)
            db.session.commit()
            flash('Слот вождения успешно добавлен в расписание.', 'success')
            return redirect(url_for('instructor_slots'))

        my_slots = DrivingSlot.query.filter_by(instructor_id=current_user.id).order_by(DrivingSlot.date.desc(), DrivingSlot.start_time.asc()).limit(50).all()
        return render_template('instructor/slots.html', form=form, slots=my_slots)

    @app.route('/instructor/slots/delete/<int:slot_id>', methods=['POST'])
    @login_required
    @role_required('instructor', 'admin', 'owner')
    def delete_slot(slot_id):
        slot = DrivingSlot.query.get_or_404(slot_id)
        if slot.instructor_id != current_user.id and not current_user.is_admin():
            abort(403)

        if slot.is_booked:
            flash('Нельзя удалить уже забронированный слот. Сначала отмените запись.', 'warning')
            return redirect(url_for('instructor_slots'))

        db.session.delete(slot)
        db.session.commit()
        flash('Слот успешно удален.', 'info')
        return redirect(url_for('instructor_slots'))

    @app.route('/instructor/bookings')
    @login_required
    @role_required('instructor', 'admin', 'owner')
    def instructor_bookings():
        bookings = DrivingBooking.query.filter_by(instructor_id=current_user.id).order_by(DrivingBooking.created_at.desc()).all()
        return render_template('instructor/bookings.html', bookings=bookings)

    @app.route('/instructor/bookings/<int:booking_id>/complete', methods=['POST'])
    @login_required
    @role_required('instructor', 'admin', 'owner')
    def complete_booking(booking_id):
        booking = DrivingBooking.query.get_or_404(booking_id)
        if booking.instructor_id != current_user.id and not current_user.is_admin():
            abort(403)

        # Санитизация bleach для защиты от Stored XSS в заметках
        raw_notes = request.form.get('notes', '')
        clean_notes = bleach.clean(raw_notes, tags=[], strip=True)

        booking.status = 'completed'
        booking.instructor_notes = clean_notes

        # Начисление практических часов курсанту
        if booking.student and booking.student.student_profile:
            booking.student.student_profile.practice_hours += 2

        db.session.commit()
        flash('Занятие отмечено как проведенное! Часы начислены курсанту.', 'success')
        return redirect(url_for('instructor_bookings'))

    # --- ТРЕНАЖЕР ПДД И ВНУТРЕННИЙ ТЕОРЕТИЧЕСКИЙ ЭКЗАМЕН ---
    @app.route('/pdd')
    def pdd_index():
        tickets_count = db.session.query(PddQuestion.ticket_number).distinct().count()
        total_questions = PddQuestion.query.count()
        return render_template('pdd/index.html', tickets_count=tickets_count or 40, total_questions=total_questions)

    @app.route('/pdd/practice/<int:ticket_number>')
    def pdd_practice(ticket_number):
        questions = PddQuestion.query.filter_by(ticket_number=ticket_number).order_by(PddQuestion.question_number).all()
        if not questions:
            flash(f'Билет №{ticket_number} пока не заполнен.', 'warning')
            return redirect(url_for('pdd_index'))
        return render_template('pdd/practice.html', ticket_number=ticket_number, questions=questions)

    @app.route('/pdd/api/check-answer', methods=['POST'])
    def pdd_check_answer():
        data = request.get_json() or {}
        question_id = data.get('question_id')
        selected_option = data.get('selected_option')

        q = PddQuestion.query.get(question_id)
        if not q:
            return jsonify({'error': 'Вопрос не найден'}), 404

        is_correct = (q.correct_option == selected_option)
        return jsonify({
            'is_correct': is_correct,
            'correct_option': q.correct_option,
            'explanation': q.explanation
        })

    @app.route('/pdd/exam')
    @login_required
    @role_required('student')
    def pdd_exam():
        # Режим сдачи экзамена: 20 случайных вопросов
        questions = PddQuestion.query.order_by(db.func.random()).limit(20).all()
        if not questions or len(questions) < 20:
            # Fallback если в базе мало вопросов
            questions = PddQuestion.query.limit(20).all()
        return render_template('pdd/exam.html', questions=questions)

    @app.route('/pdd/exam/submit', methods=['POST'])
    @login_required
    @role_required('student')
    def submit_pdd_exam():
        correct_count = 0
        total_questions = 0

        # Обработка ответов
        for key, value in request.form.items():
            if key.startswith('q_'):
                total_questions += 1
                q_id = int(key.replace('q_', ''))
                q = PddQuestion.query.get(q_id)
                if q and q.correct_option == int(value):
                    correct_count += 1

        is_passed = (correct_count >= 18) # Допускается не более 2 ошибок из 20

        # Получаем последний блок в цепочке экзаменов для формирования prev_hash
        last_exam = InternalExam.query.order_by(InternalExam.id.desc()).first()
        prev_hash = last_exam.record_hash if last_exam else GENESIS_PREV_HASH

        exam = InternalExam(
            student_id=current_user.id,
            examiner_id=None, # Системный авто-экзаменатор
            exam_type='theory',
            score=correct_count,
            is_passed=is_passed,
            notes=f'Теоретический экзамен ПДД. Верных ответов: {correct_count} из {total_questions}. Ошибок: {total_questions - correct_count}.',
            passed_at=datetime.now(timezone.utc)
        )
        exam.sign_and_seal(prev_hash)
        db.session.add(exam)

        if is_passed and current_user.student_profile:
            current_user.student_profile.theory_hours += 40

        db.session.commit()

        log_security_event('EXAM_PASSED' if is_passed else 'EXAM_FAILED',
                           f'Курсант {current_user.email} сдал экзамен ПДД: {correct_count}/20 (Статус: {"СДАН" if is_passed else "НЕ СДАН"}) [HMAC: {exam.signature[:16]}...]')

        return render_template('pdd/exam_result.html', exam=exam, correct_count=correct_count, total_questions=total_questions)

    # --- ПРАКТИЧЕСКИЙ ВНУТРЕННИЙ ЭКЗАМЕН ---
    @app.route('/instructor/practical-exam', methods=['GET', 'POST'])
    @login_required
    @role_required('instructor', 'admin', 'owner')
    def practical_exam():
        form = PracticalExamForm()
        students = User.query.filter_by(role='student').order_by(User.full_name).all()
        form.student_id.choices = [(s.id, f"{s.full_name} ({s.email})") for s in students]

        if form.validate_on_submit():
            student = User.query.get_or_404(form.student_id.data)
            penalty_points = form.score.data
            is_passed = (penalty_points <= 4) and form.is_passed.data

            raw_notes = form.notes.data or ''
            clean_notes = bleach.clean(raw_notes, tags=[], strip=True)

            last_exam = InternalExam.query.order_by(InternalExam.id.desc()).first()
            prev_hash = last_exam.record_hash if last_exam else GENESIS_PREV_HASH

            exam = InternalExam(
                student_id=student.id,
                examiner_id=current_user.id,
                exam_type='practice',
                score=penalty_points,
                is_passed=is_passed,
                notes=clean_notes,
                passed_at=datetime.now(timezone.utc)
            )
            exam.sign_and_seal(prev_hash)
            db.session.add(exam)

            if is_passed and student.student_profile:
                student.student_profile.status = 'graduated'

            db.session.commit()

            log_security_event('PRACTICAL_EXAM_RECORDED',
                               f'Инструктор {current_user.email} зафиксировал практический экзамен курсанту {student.email}: штрафных {penalty_points}, результат: {"СДАН" if is_passed else "НЕ СДАН"} [HMAC: {exam.signature[:16]}...]')
            flash('Протокол практического экзамена успешно подписан криптографической подписью HMAC-SHA256 и внесен в блокчейн-реестр!', 'success')
            return redirect(url_for('my_exams_view'))

        return render_template('instructor/practical_exam.html', form=form)

    @app.route('/exams')
    @login_required
    def my_exams_view():
        if current_user.is_student():
            exams = InternalExam.query.filter_by(student_id=current_user.id).order_by(InternalExam.passed_at.desc()).all()
        elif current_user.is_instructor():
            exams = InternalExam.query.filter_by(examiner_id=current_user.id).order_by(InternalExam.passed_at.desc()).all()
        else:
            exams = InternalExam.query.order_by(InternalExam.passed_at.desc()).limit(100).all()
        return render_template('student/exam_results.html', exams=exams)

    # --- ОТЗЫВЫ С ЗАЩИТОЙ BLEACH ---
    @app.route('/reviews', methods=['GET', 'POST'])
    def reviews_view():
        form = ReviewForm()
        instructors = InstructorProfile.query.join(User).all()
        form.instructor_id.choices = [(i.user_id, f"{i.user.full_name} ({i.car_model})") for i in instructors]

        if form.validate_on_submit():
            if not current_user.is_authenticated:
                flash('Пожалуйста, авторизуйтесь для публикации отзыва.', 'warning')
                return redirect(url_for('login'))

            # Двухконтурная защита от Stored XSS: санитизация bleach
            safe_comment = bleach.clean(form.comment.data, tags=[], strip=True)

            rev = Review(
                student_id=current_user.id,
                instructor_id=form.instructor_id.data,
                rating=int(form.rating.data),
                comment=safe_comment
            )
            db.session.add(rev)
            db.session.commit()
            log_security_event('REVIEW_ADDED', f'Курсант {current_user.email} оставил отзыв инструктору #{rev.instructor_id}')
            flash('Ваш отзыв успешно опубликован после автоматической проверки безопасности!', 'success')
            return redirect(url_for('reviews_view'))

        reviews = Review.query.order_by(Review.created_at.desc()).limit(30).all()
        return render_template('reviews.html', form=form, reviews=reviews)

    # --- ПАНЕЛЬ АДМИНИСТРАТОРА И КОНТРОЛЬ ЦЕЛОСТНОСТИ ---
    @app.route('/admin')
    @login_required
    @role_required('admin', 'owner')
    def admin_dashboard():
        total_users = User.query.count()
        total_students = User.query.filter_by(role='student').count()
        total_instructors = User.query.filter_by(role='instructor').count()
        total_bookings = DrivingBooking.query.count()
        total_exams = InternalExam.query.count()
        active_sessions = UserSession.query.filter_by(is_active=True).count()

        # Быстрая проверка целостности для статус-индикатора
        exams_sample = InternalExam.query.order_by(InternalExam.id).all()
        integrity_status = check_exam_ledger_integrity(exams_sample)

        recent_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()

        return render_template('admin/dashboard.html',
                               total_users=total_users,
                               total_students=total_students,
                               total_instructors=total_instructors,
                               total_bookings=total_bookings,
                               total_exams=total_exams,
                               active_sessions=active_sessions,
                               integrity_status=integrity_status,
                               recent_logs=recent_logs)

    @app.route('/admin/users')
    @login_required
    @role_required('admin', 'owner')
    def admin_users():
        role_filter = request.args.get('role')
        query = User.query
        if role_filter:
            query = query.filter_by(role=role_filter)
        users = query.order_by(User.id).all()
        return render_template('admin/users.html', users=users, selected_role=role_filter)

    @app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
    @login_required
    @role_required('admin', 'owner')
    def admin_edit_user(user_id):
        user = User.query.get_or_404(user_id)
        if not current_user.can_manage_user(user):
            flash('У вас недостаточно полномочий для изменения данного администратора.', 'danger')
            return redirect(url_for('admin_users'))

        form = UserEditAdminForm(
            full_name=user.full_name,
            email=user.email,
            phone=user.phone or '',
            role=user.role
        )

        if form.validate_on_submit():
            user.full_name = form.full_name.data.strip()
            user.email = form.email.data.strip().lower()
            if form.phone.data:
                user.phone = form.phone.data.strip()

            # Только владелец может назначать администраторов
            if form.role.data in ('admin', 'owner') and not current_user.is_owner():
                flash('Только владелец системы (Owner) имеет право повышать пользователей до роли администратора.', 'danger')
            else:
                user.role = form.role.data

            if form.new_password.data:
                user.set_password(form.new_password.data)

            db.session.commit()
            log_security_event('USER_MODIFIED', f'Администратор {current_user.email} изменил профиль пользователя {user.email}')
            flash('Данные пользователя обновлены.', 'success')
            return redirect(url_for('admin_users'))

        return render_template('admin/edit_user.html', form=form, user=user)

    @app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin', 'owner')
    def admin_delete_user(user_id):
        user = User.query.get_or_404(user_id)
        if not current_user.can_manage_user(user) or user.id == current_user.id:
            flash('Невозможно удалить данного пользователя.', 'danger')
            return redirect(url_for('admin_users'))

        email = user.email
        db.session.delete(user)
        db.session.commit()
        log_security_event('USER_DELETED', f'Удален пользователь {email}')
        flash('Пользователь успешно удален.', 'info')
        return redirect(url_for('admin_users'))

    @app.route('/admin/sessions')
    @login_required
    @role_required('admin', 'owner')
    def admin_sessions():
        sessions = UserSession.query.order_by(UserSession.created_at.desc()).limit(100).all()
        return render_template('admin/sessions.html', sessions=sessions)

    @app.route('/admin/sessions/<int:session_id>/revoke', methods=['POST'])
    @login_required
    @role_required('admin', 'owner')
    def admin_revoke_session(session_id):
        sess = UserSession.query.get_or_404(session_id)
        sess.is_active = False
        db.session.commit()
        log_security_event('SESSION_REVOKED', f'Администратор отозвал сессию токена #{sess.id} пользователя {sess.user.email}')
        flash('Сессия пользователя успешно отозвана. Он будет разлогинен при следующем запросе.', 'warning')
        return redirect(url_for('admin_sessions'))

    @app.route('/admin/audit')
    @login_required
    @role_required('admin', 'owner')
    def admin_audit():
        logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
        return render_template('admin/audit.html', logs=logs)

    @app.route('/admin/integrity')
    @login_required
    @role_required('admin', 'owner')
    def admin_integrity():
        exams = InternalExam.query.order_by(InternalExam.id).all()
        report = check_exam_ledger_integrity(exams)
        log_security_event('INTEGRITY_SCAN_RUN', f'Запущен аудит целостности БД: проверено {report["total"]} записей, статус: {report["is_healthy"]}')
        return render_template('admin/integrity.html', report=report, exams=exams)

    @app.route('/admin/integrity/tamper-demo', methods=['POST'])
    @login_required
    @role_required('admin', 'owner')
    def admin_tamper_demo():
        """Симуляция несанкционированной подделки оценки экзамена в БД для пентестинга."""
        action = request.form.get('action')
        target_exam = InternalExam.query.order_by(InternalExam.id.desc()).first()

        if not target_exam:
            flash('В базе нет экзаменов для демонстрации.', 'warning')
            return redirect(url_for('admin_integrity'))

        if action == 'tamper':
            # Злоумышленник изменил результат не сдавшего студента на «СДАН»
            target_exam.is_passed = not target_exam.is_passed
            target_exam.score = 20 if target_exam.exam_type == 'theory' else 0
            # Обратите внимание: HMAC подпись и hash НЕ обновляются, симулируя прямой UPDATE в БД!
            db.session.commit()
            log_security_event('SIMULATED_TAMPER_ATTACK', f'СИМУЛЯЦИЯ АТАКИ: Прямая модификация в БД записи #{target_exam.id}')
            flash(f'🚨 СИМУЛЯЦИЯ АТАКИ ВЫПОЛНЕНА: В записи #{target_exam.id} напрямую изменен результат без переподписания!', 'danger')
        elif action == 'restore':
            # Восстановление подписи и хеша
            prev_hash = GENESIS_PREV_HASH
            all_exams = InternalExam.query.order_by(InternalExam.id).all()
            for ex in all_exams:
                ex.sign_and_seal(prev_hash)
                prev_hash = ex.record_hash
            db.session.commit()
            log_security_event('INTEGRITY_RESTORED', 'Администратор выполнил криптографическую регенерацию журнала')
            flash('Реестр экзаменов успешно восстановлен и повторно опечатан криптографическими подписями.', 'success')

        return redirect(url_for('admin_integrity'))

    # --- СТРАНИЦЫ ОШИБОК ---
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
