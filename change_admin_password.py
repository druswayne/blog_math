from app import app, db, User
from werkzeug.security import generate_password_hash

# Новый пароль
new_password = "qNCkZjwz"

# Находим администратора и меняем пароль
with app.app_context():
    admin_user = User.query.filter_by(is_admin=True).first()
    
    if admin_user:
        admin_user.password = generate_password_hash(new_password)
        db.session.commit()
        print(f"Пароль администратора {admin_user.username} успешно изменен на {new_password}")
    else:
        print("Администратор не найден в базе данных") 