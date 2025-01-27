from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from datetime import datetime
from threading import Timer
from apscheduler.schedulers.background import BackgroundScheduler
import os


# Create a Flask Instance
app = Flask(__name__)

# Database Configuration
app.config["SECRET_KEY"] = "thisisasecretkey"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///todo.db"
# Mail Configuration
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")  # Get from environment variable
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")  # Get from environment variable


# Initialize Database
db = SQLAlchemy(app)

# Initialize Bcrypt
bcrypt = Bcrypt(app)

# Initialize Mail
mail = Mail(app)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Define the User Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False) # Email (required, unique)
    username = db.Column(db.String(20), unique=True, nullable=False)  # Username (required, unique)
    password = db.Column(db.String(60), nullable=False) # Password (hashed)


# Define the Task Model
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(10), default="Medium") # Low, Medium, High
    category = db.Column(db.String(20), default="personal")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def send_reminder():
    with app.app_context():
        overdue_tasks = Task.query.filter(Task.due_date < datetime.today(), Task.completed == False).all()
        for task in overdue_tasks:
            user = db.session.get(User, task.user_id)
            if user:
                msg = Message("Task Overdue Reminder",
                                sender=app.config["MAIL_USERNAME"],
                                recipients=[user.email])

                msg.body = f"Reminder: Your task '{task.content}' was due on {task.due_date}. Please complete it soon."
                mail.send(msg)

scheduler = BackgroundScheduler()
scheduler.add_job(send_reminder, 'interval', hours=1)
scheduler.start()
def schedule_reminders():
    with app.app_context():
        send_reminder()

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        password = request.form.get("password")

        # Ensure all fields are filled
        if not email or not username or not password:
            flash("All fields are required!", "danger")
            return redirect(url_for("register"))

        # Check if email or username is already taken
        existing_email = User.query.filter_by(email=email).first()
        existing_username = User.query.filter_by(username=username).first()

        if existing_email:
            flash("Email already registered. Use another email.", "danger")
            return redirect(url_for("register"))
        if existing_username:
            flash("Username already taken. Choose another one.", "danger")
            return redirect(url_for("register"))

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
        new_user = User(email=email, username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash("Account created successfully! You can log in now.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()  # Find user by username
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password", "danger")
    
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# Home Route - Show Tasks
@app.route("/")
@login_required
def index():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    return render_template('index.html', tasks=tasks)

@app.route("/dashboard")
@login_required
def dashboard():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    total_tasks = len(tasks)
    completed_tasks = len([task for task in tasks if task.completed])
    pending_tasks = total_tasks - completed_tasks
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    return render_template(
        "dashboard.html",
        tasks=tasks,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        pending_tasks=pending_tasks,
        completion_rate=completion_rate,
        today=datetime.today()
    )



# Add Task Route
@app.route("/add", methods=["POST"])
@login_required
def add_task():
    content = request.form.get("content")
    due_date = request.form.get("due_date")
    priority = request.form.get("priority")

    if not content:  # Check if content is empty
        flash("Task content cannot be empty.", "danger")
        return redirect(url_for('index'))

    new_task = Task(
        content=content,
        user_id=current_user.id,
        due_date=datetime.strptime(due_date, '%Y-%m-%d') if due_date else None,
        priority=priority
    )
    try:
        db.session.add(new_task)
        db.session.commit()
        flash("Task added successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {str(e)}", "danger")
    return redirect(url_for("index"))

# Mark Task as Completed
@app.route("/complete/<int:task_id>")
@login_required
def complete_task(task_id):
    task = db.session.get(Task, task_id)
    if task and task.user_id == current_user.id:
        task.completed = True
        db.session.commit()
    return redirect(url_for("index"))

# Delete Task
@app.route("/delete/<int:task_id>")
@login_required
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if task and task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
    return redirect(url_for("index"))

# Run Flask App
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    schedule_reminders() # Start reminder scheduling
    app.run(debug=True)
