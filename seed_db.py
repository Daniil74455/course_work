import random
from datetime import datetime, date, time, timedelta, timezone
from faker import Faker
from app import create_app
from extensions import db
from models import (User, StudentProfile, InstructorProfile, DrivingSlot,
                    DrivingBooking, PddQuestion, InternalExam, Review,
                    UserSession, AuditLog)
from integrity import GENESIS_PREV_HASH

fake = Faker('ru_RU')

CARS = [
    ('Hyundai Solaris', 'А145ВС46', 'МКПП', 1200.0),
    ('Kia Rio', 'В782ОК46', 'АКПП', 1400.0),
    ('Skoda Octavia', 'Е319МН46', 'АКПП', 1500.0),
    ('Volkswagen Polo', 'К554РТ46', 'МКПП', 1200.0),
    ('Lada Vesta', 'М902УХ46', 'МКПП', 1100.0),
    ('Renault Logan', 'О411СЕ46', 'МКПП', 1100.0),
    ('Toyota Corolla', 'Р673ТА46', 'АКПП', 1500.0),
    ('Nissan Almera', 'С820ХВ46', 'АКПП', 1300.0),
    ('Ford Focus', 'Т105УЕ46', 'МКПП', 1300.0),
    ('Lada Granta', 'Х441КМ46', 'МКПП', 1000.0),
]

PDD_TEMPLATES = [
    {
        'q': 'Главная дорога на перекрестке обозначается знаками:',
        'o1': '«Главная дорога», «Пересечение со второстепенной дорогой», «Автомагистраль»',
        'o2': 'Только знаком «Главная дорога»',
        'o3': 'Любым знаком приоритета',
        'o4': 'Знаком «Уступите дорогу»',
        'ans': 1,
        'exp': 'Согласно ПДД РФ п. 1.2, главной дорогой считается дорога, обозначенная знаками 2.1, 2.3.1-2.3.7 или 5.1 («Автомагистраль»).',
        'topic': 'Общие положения и термины'
    },
    {
        'q': 'Какое максимальное количество штрафных баллов допускается на практическом экзамене?',
        'o1': 'До 4 штрафных баллов включительно',
        'o2': 'До 5 штрафных баллов',
        'o3': 'Штрафные баллы не начисляются',
        'o4': 'До 10 штрафных баллов',
        'ans': 1,
        'exp': 'По административному регламенту проведения экзаменов (ред. 2024-2026 гг.) кандидат в водители получает оценку «СДАН» при наборе не более 4 штрафных баллов.',
        'topic': 'Регламент сдачи экзамена'
    },
    {
        'q': 'Разрешается ли водителю пользоваться телефоном во время движения?',
        'o1': 'Запрещается без использования устройства Hands-Free',
        'o2': 'Разрешается в любых случаях',
        'o3': 'Разрешается только для навигации',
        'o4': 'Запрещается в любом виде',
        'ans': 1,
        'exp': 'Пункт 2.7 ПДД запрещает пользоваться во время движения телефоном, не оборудованным техническим устройством для переговоров без использования рук.',
        'topic': 'Общие обязанности водителей'
    },
    {
        'q': 'С какой максимальной скоростью разрешено движение в жилых зонах и на дворовых территориях?',
        'o1': 'Не более 20 км/ч',
        'o2': 'Не более 40 км/ч',
        'o3': 'Не более 10 км/ч',
        'o4': 'Не более 30 км/ч',
        'ans': 1,
        'exp': 'Согласно пункту 10.2 ПДД РФ, в жилых зонах, велосипедных зонах и на дворовых территориях скорость не должна превышать 20 км/ч.',
        'topic': 'Скорость движения'
    },
    {
        'q': 'Что означает мигание зеленого сигнала светофора?',
        'o1': 'Разрешает движение и информирует, что вскоре будет включен запрещающий сигнал',
        'o2': 'Запрещает движение',
        'o3': 'Означает неисправность светофора',
        'o4': 'Предупреждает о приближении к перекрестку со спецрегулированием',
        'ans': 1,
        'exp': 'Пункт 6.2 ПДД: зеленый мигающий сигнал разрешает движение и информирует о скором включении запрещающего сигнала.',
        'topic': 'Сигналы светофора и регулировщика'
    },
    {
        'q': 'В каком случае запрещается эксплуатация транспортного средства?',
        'o1': 'Не работает звуковой сигнал или неисправна тормозная система',
        'o2': 'Отсутствует знак аварийной остановки',
        'o3': 'Не работает стеклоподъемник правой двери',
        'o4': 'Загрязнен кузов автомобиля',
        'ans': 1,
        'exp': 'Перечень неисправностей п. 1.1 и п. 7.2 запрещает движение ТС при недействующей рабочей тормозной системе или звуковом сигнале.',
        'topic': 'Основные положения по допуску ТС'
    },
    {
        'q': 'Какова безопасная дистанция до впереди идущего автомобиля на сухом асфальте?',
        'o1': 'Дистанция, преодолеваемая автомобилем не менее чем за 2 секунды',
        'o2': 'Ровно 5 метров',
        'o3': 'Дистанция в 1 секунду',
        'o4': 'Не имеет значения при исправных тормозах',
        'ans': 1,
        'exp': 'Правило 2 секунд обеспечивает достаточное время реакции водителя и тормозной путь на сухом покрытии.',
        'topic': 'Основы безопасности движения'
    },
    {
        'q': 'Кому вы обязаны уступить дорогу при выезде из жилой зоны?',
        'o1': 'Всем участникам дорожного движения (пешеходам и ТС)',
        'o2': 'Только транспортным средствам, приближающимся справа',
        'o3': 'Только маршрутным транспортным средствам',
        'o4': 'Никому, если вы выезжаете прямо',
        'ans': 1,
        'exp': 'Пункт 17.3 ПДД РФ: при выезде из жилой зоны водители должны уступить дорогу другим участникам дорожного движения.',
        'topic': 'Движение в жилых зонах'
    }
]

def seed_database():
    app = create_app()
    with app.app_context():
        print("🔧 Инициализация таблиц базы данных...")
        db.drop_all()
        db.create_all()

        print("👤 Создание фиксированных учетных записей (Owner, Admin, Instructor, Student)...")

        # 1. Фиксированный Владелец
        owner = User(
            email='owner@autoschool.ru',
            full_name='Романов Александр Сергеевич',
            role='owner'
        )
        owner.set_password('owner123')
        owner.phone = '+7 (999) 000-00-01'
        db.session.add(owner)

        # 2. Фиксированный Администратор
        admin = User(
            email='admin@autoschool.ru',
            full_name='Пряхин Даниил Андреевич',
            role='admin'
        )
        admin.set_password('admin123')
        admin.phone = '+7 (999) 000-00-02'
        db.session.add(admin)

        # 3. Фиксированный Инструктор
        instructor_user = User(
            email='instructor@autoschool.ru',
            full_name='Соколов Виктор Михайлович',
            role='instructor'
        )
        instructor_user.set_password('instructor123')
        instructor_user.phone = '+7 (999) 111-22-33'
        db.session.add(instructor_user)
        db.session.flush()

        inst_profile = InstructorProfile(
            user_id=instructor_user.id,
            car_model='Hyundai Solaris',
            car_number='А145ВС46',
            transmission='МКПП',
            experience_years=12,
            hourly_rate=1200.0,
            bio='Старший инструктор высшей категории. Спокойный, внимательный, подготовил более 400 уверенных водителей.',
            rating=5.0
        )
        db.session.add(inst_profile)

        # 4. Фиксированный Курсант
        student_user = User(
            email='student@autoschool.ru',
            full_name='Смирнов Алексей Дмитриевич',
            role='student'
        )
        student_user.set_password('student123')
        student_user.phone = '+7 (999) 444-55-66'
        db.session.add(student_user)
        db.session.flush()

        stud_profile = StudentProfile(
            user_id=student_user.id,
            category='B',
            theory_hours=40,
            practice_hours=18,
            status='studying'
        )
        stud_profile.passport_data = 'Серия 3818 № 918234, выдан УМВД России по Курской обл.'
        stud_profile.medical_cert = 'Медсправка 003-В/у № 8721983 от 10.09.2026'
        db.session.add(stud_profile)

        # 5. Дополнительные 9 инструкторов с автопарком
        print("🚗 Создание автопарка и инструкторов...")
        instructors = [instructor_user]
        for car_model, car_number, transmission, rate in CARS[1:]:
            u = User(
                email=fake.unique.email(),
                full_name=f"{fake.last_name_male()} {fake.first_name_male()} {fake.middle_name_male()}",
                role='instructor'
            )
            u.set_password('instructor123')
            u.phone = fake.phone_number()
            db.session.add(u)
            db.session.flush()

            p = InstructorProfile(
                user_id=u.id,
                car_model=car_model,
                car_number=car_number,
                transmission=transmission,
                experience_years=random.randint(3, 20),
                hourly_rate=rate,
                bio=f"Инструктор производственного обучения. Специализация на категории B ({transmission}). Спокойная и доброжелательная подача материала.",
                rating=round(random.uniform(4.7, 5.0), 1)
            )
            db.session.add(p)
            instructors.append(u)

        # 6. 100 курсантов с зашифрованными ПДн
        print("🎓 Генерация 100 курсантов с шифрованием Fernet (телефоны, паспорта, медсправки)...")
        students = [student_user]
        for _ in range(100):
            gender = random.choice(['m', 'f'])
            if gender == 'm':
                fn = f"{fake.last_name_male()} {fake.first_name_male()} {fake.middle_name_male()}"
            else:
                fn = f"{fake.last_name_female()} {fake.first_name_female()} {fake.middle_name_female()}"

            st = User(
                email=fake.unique.email(),
                full_name=fn,
                role='student'
            )
            st.set_password('student123')
            st.phone = fake.phone_number() # Fernet transparent encryption
            db.session.add(st)
            db.session.flush()

            sp = StudentProfile(
                user_id=st.id,
                category=random.choice(['B', 'B', 'B', 'A', 'C']),
                theory_hours=random.randint(0, 40),
                practice_hours=random.randint(0, 30),
                status=random.choice(['studying', 'studying', 'admitted_to_exam', 'graduated'])
            )
            sp.passport_data = f"Паспорт РФ: {random.randint(1000, 9999)} № {random.randint(100000, 999999)}"
            sp.medical_cert = f"Справка 003-В/у № {random.randint(1000000, 9999999)}"
            db.session.add(sp)
            students.append(st)

        db.session.commit()

        # 7. Заполнение билетов ПДД (40 билетов по 20 вопросов = 800 вопросов)
        print("📚 Заполнение базы билетов ПДД (40 билетов)...")
        for ticket in range(1, 41):
            for q_num in range(1, 21):
                tmpl = random.choice(PDD_TEMPLATES)
                pq = PddQuestion(
                    ticket_number=ticket,
                    question_number=q_num,
                    question_text=f"[Билет {ticket}, Вопрос {q_num}] {tmpl['q']}",
                    option_1=tmpl['o1'],
                    option_2=tmpl['o2'],
                    option_3=tmpl['o3'],
                    option_4=tmpl['o4'],
                    correct_option=tmpl['ans'],
                    explanation=tmpl['exp'],
                    topic=tmpl['topic']
                )
                db.session.add(pq)
        db.session.commit()

        # 8. Генерация массива 5000+ слотов и записей на вождение (Критерий кафедры)
        print("⚡ Генерация 5200 слотов и записей на практическое вождение (выполнение кафедрального норматива 5000+)...")
        start_date = date.today() - timedelta(days=240) # за последние 8 месяцев
        end_date = date.today() + timedelta(days=30)     # и на 1 месяц вперед

        daily_times = [
            (time(8, 30), time(10, 0)),
            (time(10, 15), time(11, 45)),
            (time(12, 30), time(14, 0)),
            (time(14, 15), time(15, 45)),
            (time(16, 0), time(17, 30)),
            (time(17, 45), time(19, 15)),
        ]

        slot_count = 0
        bookings_to_add = []
        slots_to_add = []

        curr_date = start_date
        while curr_date <= end_date and slot_count < 5200:
            for inst in instructors:
                if random.random() < 0.85: # рабочий день инструктора
                    for start_t, end_t in daily_times:
                        is_past = (curr_date < date.today())
                        # Для прошедших дат 90% слотов забронированы и завершены
                        is_booked = (random.random() < 0.90) if is_past else (random.random() < 0.40)

                        slot = DrivingSlot(
                            instructor_id=inst.id,
                            date=curr_date,
                            start_time=start_t,
                            end_time=end_t,
                            is_booked=is_booked,
                            price=inst.instructor_profile.hourly_rate if inst.instructor_profile else 1200.0
                        )
                        slots_to_add.append(slot)
                        slot_count += 1
                        if slot_count >= 5200:
                            break
                if slot_count >= 5200:
                    break
            curr_date += timedelta(days=1)

        db.session.bulk_save_objects(slots_to_add, return_defaults=True)
        db.session.commit()

        # Создание связанных записей бронирований для забронированных слотов
        print("🔗 Привязка записей курсантов к слотам вождения...")
        booked_slots = DrivingSlot.query.filter_by(is_booked=True).all()
        for s in booked_slots:
            st = random.choice(students)
            status = 'completed' if s.date < date.today() else 'booked'
            notes = random.choice([
                'Отработаны упражнения на площадке: змейка, заезд в бокс задним ходом.',
                'Городской маршрут №2. Отработан проезд кругового движения и перекрестков.',
                'Отличный контроль сцепления, уверенная параллельная парковка.',
                'Учебный маршрут по центру города. Замечания по своевременному включению указателей поворота.',
                'Подготовка к внутреннему экзамену, все нормативы выполнены.'
            ]) if status == 'completed' else None

            bk = DrivingBooking(
                slot_id=s.id,
                student_id=st.id,
                instructor_id=s.instructor_id,
                status=status,
                instructor_notes=notes,
                created_at=datetime.combine(s.date - timedelta(days=2), s.start_time).replace(tzinfo=timezone.utc)
            )
            bookings_to_add.append(bk)

        db.session.bulk_save_objects(bookings_to_add)
        db.session.commit()

        # 9. Генерация защищенных протоколов экзаменов (HMAC-SHA256 + Блокчейн Hash-Chaining)
        print("🔒 Генерация протоколов экзаменов с цифровой подписью HMAC-SHA256 и хеш-цепочкой...")
        prev_hash = GENESIS_PREV_HASH

        exam_types = ['theory', 'practice']
        for i in range(120):
            st = random.choice(students)
            ex_type = random.choice(exam_types)
            examiner = None if ex_type == 'theory' else random.choice(instructors)

            if ex_type == 'theory':
                score = random.randint(15, 20)
                is_passed = (score >= 18)
                notes = f"Теория ПДД: {score}/20 верных ответов."
            else:
                score = random.randint(0, 8)
                is_passed = (score <= 4)
                notes = f"Практика (автодром и город): {score} штрафных баллов."

            passed_time = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 180), hours=random.randint(1, 23))

            exam = InternalExam(
                student_id=st.id,
                examiner_id=examiner.id if examiner else None,
                exam_type=ex_type,
                score=score,
                is_passed=is_passed,
                notes=notes,
                passed_at=passed_time
            )
            exam.sign_and_seal(prev_hash)
            db.session.add(exam)
            db.session.flush()

            prev_hash = exam.record_hash

        # 10. Отзывы курсантов
        print("⭐ Добавление отзывов...")
        reviews_comments = [
            "Виктор Михайлович — лучший инструктор! Сдал город с первого раза без единой ошибки!",
            "Отличная автошкола, очень удобный сайт и онлайн-запись на вождение.",
            "Прекрасный преподаватель, все спокойно объясняет, никогда не повышает голос.",
            "Машина чистая, коробка работает идеально, автодром просторный.",
            "Тренажер ПДД очень помог быстро выучить все каверзные вопросы!"
        ]
        for _ in range(30):
            r = Review(
                student_id=random.choice(students).id,
                instructor_id=random.choice(instructors).id,
                rating=random.choice([4, 5, 5, 5]),
                comment=random.choice(reviews_comments),
                created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 60))
            )
            db.session.add(r)

        # 11. Первоначальные записи журнала аудита
        log = AuditLog(
            user_id=admin.id,
            event_type='SYSTEM_INIT',
            description='Первичная инициализация защищенной базы данных Автошколы и сидирование тестового массива',
            ip_address='127.0.0.1'
        )
        db.session.add(log)
        db.session.commit()

        total_slots = DrivingSlot.query.count()
        total_bookings = DrivingBooking.query.count()
        total_exams = InternalExam.query.count()
        total_users = User.query.count()

        print("\n" + "="*60)
        print("🎉 БАЗА ДАННЫХ УСПЕШНО СФОРМИРОВАНА И НАПОЛНЕНА!")
        print(f"📊 Статистика массива данных:")
        print(f"   • Пользователей в системе: {total_users}")
        print(f"   • Вопросов ПДД (40 билетов): {PddQuestion.query.count()}")
        print(f"   • Слотов вождения (DrivingSlot): {total_slots} (ТРЕБОВАНИЕ КАФЕДРЫ 5000+ ВЫПОЛНЕНО)")
        print(f"   • Бронирований занятий (DrivingBooking): {total_bookings}")
        print(f"   • Протоколов экзаменов HMAC: {total_exams}")
        print(f"   • Отзывов: {Review.query.count()}")
        print("="*60)
        print("🔑 Учетные данные для входа:")
        print("   👑 Владелец:       owner@autoschool.ru      / owner123")
        print("   🛡️ Администратор:  admin@autoschool.ru      / admin123")
        print("   🚗 Инструктор:     instructor@autoschool.ru / instructor123")
        print("   🎓 Курсант:        student@autoschool.ru    / student123")
        print("="*60 + "\n")

if __name__ == '__main__':
    seed_database()
