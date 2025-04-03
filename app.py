from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from functools import wraps
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, SubmitField, FileField
from wtforms.validators import DataRequired, Optional, Email
from werkzeug.security import generate_password_hash, check_password_hash
concurrent_path = os.path.dirname(__file__)
os.chdir(concurrent_path)
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Создаем директорию для загрузок, если она не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    ratings = db.relationship('Rating', backref='user', lazy=True)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    is_draft = db.Column(db.Boolean, default=False)
    tags = db.relationship('Tag', secondary='post_tags', backref=db.backref('posts', lazy=True))
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    ratings = db.relationship('Rating', backref='post', lazy=True, cascade='all, delete-orphan')
    image_path = db.Column(db.String(200))

    @property
    def average_rating(self):
        if not self.ratings:
            return 0
        return sum(r.value for r in self.ratings) / len(self.ratings)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy=True, cascade='all, delete-orphan')

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer, nullable=False)  # от 1 до 5
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='user_post_rating'),)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.String(200))
    posts = db.relationship('Post', backref='category', lazy=True)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)

# Таблица для связи many-to-many между постами и тегами
post_tags = db.Table('post_tags',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class AuthorInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    education = db.Column(db.Text, nullable=False)
    experience = db.Column(db.Text, nullable=False)
    achievements = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    image_path = db.Column(db.String(200))

class AuthorInfoForm(FlaskForm):
    name = StringField('ФИО', validators=[DataRequired()])
    position = StringField('Должность', validators=[DataRequired()])
    description = TextAreaField('Описание', validators=[DataRequired()])
    education = TextAreaField('Образование', validators=[DataRequired()])
    experience = TextAreaField('Опыт работы', validators=[DataRequired()])
    achievements = TextAreaField('Достижения', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Телефон', validators=[DataRequired()])
    image = FileField('Фото', validators=[Optional()])
    submit = SubmitField('Сохранить')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category', type=int)
    author_id = request.args.get('author', type=int)
    tag_id = request.args.get('tag', type=int)
    search_query = request.args.get('q', '')
    
    query = Post.query.filter_by(is_draft=False)
    
    if category_id:
        query = query.filter_by(category_id=category_id)
    if author_id:
        query = query.filter_by(user_id=author_id)
    if tag_id:
        query = query.join(post_tags).filter(post_tags.c.tag_id == tag_id)
    if search_query:
        query = query.filter(
            db.or_(
                Post.title.ilike(f'%{search_query}%'),
                Post.content.ilike(f'%{search_query}%')
            )
        )
    
    posts = query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    categories = Category.query.all()
    tags = Tag.query.all()
    
    return render_template('home.html', posts=posts, categories=categories, tags=tags)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'danger')
            return redirect(url_for('register'))
            
        user = User(username=username, password=password, is_admin=False)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, author=current_user, 
                   category_id=form.category.data, is_draft=form.is_draft.data)
        
        # Обработка тегов
        tags_str = form.tags.data
        if tags_str:
            tags = [tag.strip() for tag in tags_str.split(',')]
            for tag_name in tags:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                post.tags.append(tag)
        
        # Обработка изображения
        if form.image.data:
            file = form.image.data
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                post.image_path = f"uploads/{filename}"
            else:
                flash('Неподдерживаемый тип файла', 'danger')
                return redirect(url_for('new_post'))
        
        db.session.add(post)
        db.session.commit()
        flash('Ваш пост создан!', 'success')
        return redirect(url_for('home'))
    return render_template('create_post.html', title='Новый пост', form=form)

@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.is_draft and (not current_user.is_authenticated or current_user.id != post.user_id):
        abort(403)
    return render_template('post.html', title=post.title, post=post)

@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        abort(403)
    
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        post.category_id = form.category.data
        post.is_draft = form.is_draft.data
        
        # Обработка тегов
        post.tags = []
        if form.tags.data:
            tag_names = [tag.strip() for tag in form.tags.data.split(',')]
            for tag_name in tag_names:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                post.tags.append(tag)
        
        # Обработка изображения
        if form.image.data:
            # Удаляем старое изображение, если оно есть
            if post.image_path:
                old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_path.split('/')[-1])
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)
            
            file = form.image.data
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                post.image_path = f"uploads/{filename}"
        
        db.session.commit()
        flash('Запись успешно обновлена!', 'success')
        return redirect(url_for('post', post_id=post.id))
    
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
        form.category.data = post.category_id
        form.tags.data = ', '.join(tag.name for tag in post.tags)
        form.is_draft.data = post.is_draft
    
    return render_template('create_post.html', title='Редактировать запись', form=form, post=post)

@app.route('/post/<int:post_id>/publish', methods=['POST'])
@login_required
@admin_required
def publish_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        abort(403)
    
    post.is_draft = False
    db.session.commit()
    flash('Запись успешно опубликована!', 'success')
    return redirect(url_for('post', post_id=post.id))

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')
    parent_id = request.form.get('parent_id', type=int)
    
    if content:
        comment = Comment(
            content=content,
            author=current_user,
            post=post,
            parent_id=parent_id
        )
        db.session.add(comment)
        db.session.commit()
        flash('Комментарий добавлен!', 'success')
    return redirect(url_for('post', post_id=post.id))

@app.route('/post/<int:post_id>/rate', methods=['POST'])
@login_required
def rate_post(post_id):
    post = Post.query.get_or_404(post_id)
    value = int(request.form.get('rating', 0))
    if 1 <= value <= 5:
        rating = Rating.query.filter_by(user=current_user, post=post).first()
        if rating:
            rating.value = value
        else:
            rating = Rating(value=value, user=current_user, post=post)
            db.session.add(rating)
        db.session.commit()
        flash('Оценка сохранена!', 'success')
    return redirect(url_for('post', post_id=post.id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('home'))
        flash('Неверное имя пользователя или пароль', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

def create_admin():
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', password='qNCkZjwz', is_admin=True)
            db.session.add(admin)
            db.session.commit()
            print('Администратор создан!')

@app.route("/category/new", methods=['GET', 'POST'])
@login_required
def new_category():
    if request.method == "POST":
        category = Category(name=request.form['name'], description=request.form['description'])
        db.session.add(category)
        db.session.commit()
        flash('Категория создана!', 'success')
        return redirect(url_for('home'))
    return render_template('create_category.html', title='Новая категория')

@app.route("/category/<int:category_id>")
def category_posts(category_id):
    category = Category.query.get_or_404(category_id)
    posts = Post.query.filter_by(category_id=category_id, is_draft=False).order_by(Post.date_posted.desc()).all()
    return render_template('category_posts.html', title=category.name, posts=posts, category=category)

@app.route("/tag/<int:tag_id>")
def tag_posts(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    posts = tag.posts.filter_by(is_draft=False).order_by(Post.date_posted.desc()).all()
    return render_template('tag_posts.html', title=f'Посты с тегом {tag.name}', posts=posts, tag=tag)

@app.route('/drafts')
@login_required
def drafts():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(user_id=current_user.id, is_draft=True)\
        .order_by(Post.date_posted.desc())\
        .paginate(page=page, per_page=5)
    return render_template('drafts.html', title='Черновики', posts=posts)

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    post_id = comment.post_id
    db.session.delete(comment)
    db.session.commit()
    flash('Комментарий успешно удален!', 'success')
    return redirect(url_for('post', post_id=post_id))

@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        abort(403)
    
    # Удаляем изображение, если оно есть
    if post.image_path:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_path.split('/')[-1])
        if os.path.exists(image_path):
            os.remove(image_path)
    
    db.session.delete(post)
    db.session.commit()
    flash('Запись успешно удалена!', 'success')
    return redirect(url_for('home'))

@app.route('/about')
def about():
    author_info = AuthorInfo.query.first()
    return render_template('about.html', title='Об авторе', author_info=author_info)

@app.route('/about/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_about():
    author_info = AuthorInfo.query.first()
    if not author_info:
        author_info = AuthorInfo(
            name='Путято Андрей Викторович',
            position='Учитель математики',
            description='Здравствуйте! Я - учитель математики с многолетним опытом преподавания. Моя миссия - сделать математику доступной и интересной для каждого ученика.',
            education='Высшее педагогическое образование\nСпециализация: математика и информатика',
            experience='Преподавание математики в средней школе\nПодготовка учащихся к олимпиадам\nРазработка методических материалов',
            achievements='Высшая квалификационная категория\nПобедитель конкурса "Учитель года"\nАвтор методических разработок',
            email='example@email.com',
            phone='+7 (XXX) XXX-XX-XX'
        )
        db.session.add(author_info)
        db.session.commit()
    
    form = AuthorInfoForm()
    if form.validate_on_submit():
        try:
            author_info.name = form.name.data
            author_info.position = form.position.data
            author_info.description = form.description.data
            author_info.education = form.education.data
            author_info.experience = form.experience.data
            author_info.achievements = form.achievements.data
            author_info.email = form.email.data
            author_info.phone = form.phone.data
            
            if form.image.data:
                file = form.image.data
                if file and allowed_file(file.filename):
                    # Удаляем старое изображение, если оно есть
                    if author_info.image_path:
                        old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], author_info.image_path.split('/')[-1])
                        if os.path.exists(old_image_path):
                            os.remove(old_image_path)
                    
                    filename = secure_filename(file.filename)
                    filename = f"author_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    author_info.image_path = f"uploads/{filename}"
            
            db.session.commit()
            flash('Информация об авторе успешно обновлена!', 'success')
            return redirect(url_for('about'))
        except Exception as e:
            db.session.rollback()
            flash(f'Произошла ошибка при сохранении: {str(e)}', 'danger')
            return redirect(url_for('edit_about'))
    
    elif request.method == 'GET':
        form.name.data = author_info.name
        form.position.data = author_info.position
        form.description.data = author_info.description
        form.education.data = author_info.education
        form.experience.data = author_info.experience
        form.achievements.data = author_info.achievements
        form.email.data = author_info.email
        form.phone.data = author_info.phone
    
    return render_template('edit_about.html', title='Редактировать информацию об авторе', form=form)

class PostForm(FlaskForm):
    title = StringField('Заголовок', validators=[DataRequired()])
    content = TextAreaField('Содержание', validators=[DataRequired()])
    category = SelectField('Категория', coerce=int, choices=[], validators=[Optional()])
    tags = StringField('Теги (через запятую)', validators=[Optional()])
    is_draft = BooleanField('Сохранить как черновик')
    image = FileField('Изображение', validators=[Optional()])
    submit = SubmitField('Опубликовать')

    def __init__(self, *args, **kwargs):
        super(PostForm, self).__init__(*args, **kwargs)
        self.category.choices = [(c.id, c.name) for c in Category.query.order_by('name')]

def init_categories():
    categories = [
        {'name': 'Интересная информация', 'description': 'Увлекательные факты и интересные материалы по математике'},
        {'name': 'Задача дня', 'description': 'Ежедневные математические задачи для размышления'},
        {'name': 'Юмор', 'description': 'Забавные математические шутки и карикатуры'},
        {'name': 'Полезная информация', 'description': 'Полезные материалы и советы для изучения математики'},
        {'name': 'Для учителей', 'description': 'Материалы и ресурсы для преподавателей математики'}
    ]
    
    for category_data in categories:
        category = Category.query.filter_by(name=category_data['name']).first()
        if not category:
            category = Category(**category_data)
            db.session.add(category)
    
    db.session.commit()

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin()
        init_categories()
    app.run(debug=True) 