from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def role_required(*allowed_roles):
    """Декоратор для проверки ролей пользователя (RBAC)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Для доступа к данному разделу необходимо авторизоваться.', 'warning')
                return redirect(url_for('login'))
            if current_user.role not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
