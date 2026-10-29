from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, FloatField, IntegerField, TextAreaField, DateField, TimeField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, NumberRange, Optional
from models import User

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(message='Введите email'), Email(message='Некорректный email')])
    password = PasswordField('Пароль', validators=[DataRequired(message='Введите пароль')])
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')

class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(message='Введите email'), Email(message='Некорректный email')])
    full_name = StringField('ФИО', validators=[DataRequired(message='Введите ФИО'), Length(min=3, max=100)])
    phone = StringField('Номер телефона', validators=[DataRequired(message='Введите телефон'), Length(min=10, max=20)])
    role = SelectField('Роль в системе', choices=[('student', 'Курсант (обучающийся)'), ('instructor', 'Инструктор по вождению')], default='student')
    category = SelectField('Категория обучения', choices=[('B', 'Категория B (Легковые авто)'), ('A', 'Категория A (Мотоциклы)'), ('C', 'Категория C (Грузовые авто)')], default='B')
    password = PasswordField('Пароль', validators=[DataRequired(message='Введите пароль'), Length(min=6, message='Пароль должен содержать не менее 6 символов')])
    confirm_password = PasswordField('Повторите пароль', validators=[DataRequired(), EqualTo('password', message='Пароли должны совпадать')])
    submit = SubmitField('Зарегистрироваться')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.strip().lower()).first()
        if user:
            raise ValidationError('Пользователь с таким email уже зарегистрирован.')

class ProfileForm(FlaskForm):
    full_name = StringField('ФИО', validators=[DataRequired(), Length(min=3, max=100)])
    phone = StringField('Телефон', validators=[DataRequired(), Length(min=10, max=20)])
    passport_data = StringField('Паспортные данные (серия, номер, кем выдан)', validators=[Optional(), Length(max=200)])
    medical_cert = StringField('Номер мед. заключения водителя', validators=[Optional(), Length(max=100)])
    old_password = PasswordField('Текущий пароль (для изменения пароля)', validators=[Optional()])
    new_password = PasswordField('Новый пароль', validators=[Optional(), Length(min=6)])
    confirm_new_password = PasswordField('Повтор нового пароля', validators=[Optional(), EqualTo('new_password', message='Пароли должны совпадать')])
    submit = SubmitField('Сохранить изменения')

class DrivingSlotForm(FlaskForm):
    date = DateField('Дата занятия', validators=[DataRequired(message='Укажите дату')])
    start_time = TimeField('Время начала', validators=[DataRequired(message='Укажите время начала')])
    end_time = TimeField('Время окончания', validators=[DataRequired(message='Укажите время окончания')])
    price = FloatField('Стоимость занятия (руб.)', validators=[DataRequired(), NumberRange(min=500, max=10000)], default=1200.0)
    submit = SubmitField('Добавить слот в расписание')

class PracticalExamForm(FlaskForm):
    student_id = SelectField('Курсант', coerce=int, validators=[DataRequired(message='Выберите курсанта')])
    score = IntegerField('Штрафные баллы (0..15)', validators=[DataRequired(), NumberRange(min=0, max=15)], default=0)
    is_passed = BooleanField('Экзамен сдан (не более 4 штрафных баллов)', default=True)
    notes = TextAreaField('Замечания экзаменатора / упражнения автодрома и города', validators=[Optional()])
    submit = SubmitField('Подписать протокол практического экзамена (HMAC-SHA256)')

class ReviewForm(FlaskForm):
    instructor_id = SelectField('Инструктор', coerce=int, validators=[DataRequired()])
    rating = SelectField('Оценка', choices=[('5', '⭐⭐⭐⭐⭐ 5 - Отлично'), ('4', '⭐⭐⭐⭐ 4 - Хорошо'), ('3', '⭐⭐⭐ 3 - Удовлетворительно'), ('2', '⭐⭐ 2 - Плохо'), ('1', '⭐ 1 - Ужасно')], default='5')
    comment = TextAreaField('Текст отзыва', validators=[DataRequired(message='Напишите комментарий'), Length(min=5, max=1000)])
    submit = SubmitField('Оставить отзыв')

class UserEditAdminForm(FlaskForm):
    full_name = StringField('ФИО', validators=[DataRequired(), Length(min=3, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Телефон', validators=[Optional(), Length(max=20)])
    role = SelectField('Роль', choices=[('student', 'Курсант'), ('instructor', 'Инструктор'), ('admin', 'Администратор'), ('owner', 'Владелец')])
    new_password = PasswordField('Установить новый пароль (оставьте пустым, если не меняется)', validators=[Optional(), Length(min=6)])
    submit = SubmitField('Сохранить данные пользователя')
