import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from io import BytesIO
from flask import send_file
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)

# ==========================================
# App Configuration
# ==========================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.config["SECRET_KEY"] = "prepai_secret_key_2026"

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///" + os.path.join(BASE_DIR, "database.db")
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db = SQLAlchemy(app)

bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


# ==========================
# Database Models
# ==========================

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False)

    papers = db.relationship("Paper", backref="company", lazy=True)

class Paper(db.Model):
    __tablename__ = "papers"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"))
    year = db.Column(db.Integer, nullable=False)

    sections = db.relationship("Section", backref="paper", lazy=True)


class Section(db.Model):
    __tablename__ = "sections"

    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey("papers.id"))
    section_name = db.Column(db.String(100), nullable=False)

    questions = db.relationship("Question", backref="section", lazy=True)

class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("sections.id"))
    question = db.Column(db.Text)
    option_a = db.Column(db.String(255))
    option_b = db.Column(db.String(255))
    option_c = db.Column(db.String(255))
    option_d = db.Column(db.String(255))
    answer = db.Column(db.String(10))
    explanation = db.Column(db.Text)
    difficulty = db.Column(db.String(20))


class Result(db.Model):
    __tablename__ = "results"

    id = db.Column(db.Integer, primary_key=True)

    # Foreign Key
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Relationship with User table
    user = db.relationship("User", backref="results")

    company = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(100), nullable=False)

    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<Result {self.user_id} - {self.company} - {self.score}/{self.total}>"
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==========================
# Home
# ==========================

@app.route("/")
def home():
    return render_template("index.html")


# ==========================
# Register
# ==========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user:
            flash("Email already exists.", "danger")
            return redirect(url_for("register"))

        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            role="user"
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Registration Successful. Please Login.", "success")

        return redirect(url_for("login"))

    return render_template("register.html")


# ==========================
# Login
# ==========================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password, password):
            if user.role == "admin":
                flash("Please use Admin Login.", "warning")
                return redirect(url_for("admin_login"))

            login_user(user)
            flash("Student Login Successful", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid Email or Password", "danger")

    return render_template("login.html")

# ==========================================
# Admin Login
# ==========================================

@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        app.logger.debug("Admin login attempt for email=%s", email)

        admin = User.query.filter_by(
            email=email,
            role="admin"
        ).first()

        app.logger.debug("Admin record found=%s", bool(admin))

        if admin and bcrypt.check_password_hash(admin.password, password):
            login_user(admin)
            app.logger.debug("Admin password verified and login_user called for email=%s", email)
            flash("Admin Login Successful", "success")
            return redirect(url_for("admin_dashboard"))

        app.logger.debug("Admin login failed for email=%s", email)
        flash("Invalid Admin Email or Password", "danger")

    return render_template("admin_login.html")
# ==========================================
# Dashboard
# ==========================================

@app.route("/dashboard")
@login_required
def dashboard():

    company_count = Company.query.count()
    paper_count = Paper.query.count()
    question_count = Question.query.count()

    total_exams = Result.query.filter_by(
        user_id=current_user.id
    ).count()

    latest_result = Result.query.filter_by(
        user_id=current_user.id
    ).order_by(Result.id.desc()).first()

    return render_template(
        "dashboard.html",
        user=current_user,
        company_count=company_count,
        paper_count=paper_count,
        question_count=question_count,
        total_exams=total_exams,
        latest_result=latest_result
    )
# ==========================================
# Admin Dashboard
# ==========================================

@app.route("/admin_dashboard")
@login_required
def admin_dashboard():

    if current_user.role != "admin":
        return redirect(url_for("dashboard"))

    total_students = User.query.filter_by(role="user").count()
    total_companies = Company.query.count()
    total_papers = Paper.query.count()
    total_sections = Section.query.count()
    total_questions = Question.query.count()
    total_exams = Result.query.count()

    recent_results = Result.query.order_by(Result.id.desc()).limit(10).all()

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        total_companies=total_companies,
        total_papers=total_papers,
        total_sections=total_sections,
        total_questions=total_questions,
        total_exams=total_exams,
        recent_results=recent_results
    )

# ==========================================
# Add Company
# ==========================================

@app.route("/admin/company", methods=["GET", "POST"])
@login_required
def add_company():
    if current_user.role != "admin":
        flash("Access Denied", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        company_name = request.form["company_name"]
        company = Company(company_name=company_name)

        db.session.add(company)
        db.session.commit()

        flash("Company Added Successfully", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_company.html")


# ==========================================
# Add Paper
# ==========================================

@app.route("/admin/paper", methods=["GET", "POST"])
@login_required
def add_paper():
    if current_user.role != "admin":
        flash("Access Denied", "danger")
        return redirect(url_for("dashboard"))

    companies = Company.query.order_by(Company.company_name).all()

    if request.method == "POST":
        company_id = request.form.get("company_id")
        year = request.form.get("year")

        if not company_id or not year:
            flash("Please select a company and enter a year.", "danger")
            return redirect(url_for("add_paper"))

        try:
            year = int(year)
        except ValueError:
            flash("Year must be a number.", "danger")
            return redirect(url_for("add_paper"))

        existing = Paper.query.filter_by(company_id=company_id, year=year).first()
        if existing:
            flash("A paper for this company and year already exists.", "danger")
            return redirect(url_for("add_paper"))

        paper = Paper(company_id=company_id, year=year)

        db.session.add(paper)
        db.session.commit()

        flash("Paper Added Successfully", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("add_paper.html", companies=companies)


# ==========================================
# Add Section
# ==========================================

@app.route("/admin/section", methods=["GET", "POST"])
@login_required
def add_section():

    if current_user.role != "admin":
        flash("Access Denied", "danger")
        return redirect(url_for("dashboard"))

    papers = Paper.query.order_by(Paper.year.desc()).all()

    if request.method == "POST":

        paper_id = request.form["paper_id"]
        section_name = request.form["section_name"]

        existing = Section.query.filter_by(
            paper_id=paper_id,
            section_name=section_name
        ).first()

        if existing:
            flash("Section already exists!", "warning")
            return redirect(url_for("add_section"))

        new_section = Section(
            paper_id=paper_id,
            section_name=section_name
        )

        db.session.add(new_section)
        db.session.commit()

        flash("Section Added Successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "add_section.html",
        papers=papers
    )
# ==========================================
# Add Question
# ==========================================

@app.route("/admin/question", methods=["GET", "POST"])
@login_required
def add_question():

    if current_user.role != "admin":
        flash("Access Denied", "danger")
        return redirect(url_for("dashboard"))

    sections = Section.query.order_by(Section.section_name).all()

    if request.method == "POST":

        new_question = Question(
            section_id=request.form["section_id"],
            question=request.form["question"],
            option_a=request.form["option_a"],
            option_b=request.form["option_b"],
            option_c=request.form["option_c"],
            option_d=request.form["option_d"],
            answer=request.form["answer"],
            explanation=request.form["explanation"],
            difficulty=request.form["difficulty"]
        )

        db.session.add(new_question)
        db.session.commit()

        flash("Question Added Successfully!", "success")

        return redirect(url_for("add_question"))

    return render_template(
        "add_question.html",
        sections=sections
    )

# ==========================================
# View Questions
# ==========================================

@app.route("/admin/questions")
@login_required
def view_questions():

    if current_user.role != "admin":
        flash("Access Denied", "danger")
        return redirect(url_for("dashboard"))

    questions = Question.query.order_by(Question.id.desc()).all()

    return render_template(
        "view_questions.html",
        questions=questions
    )

# ==========================================
# Edit Question
# ==========================================

@app.route("/admin/edit_question/<int:id>", methods=["GET", "POST"])
@login_required
def edit_question(id):

    if current_user.role != "admin":
        flash("Access Denied", "danger")
        return redirect(url_for("dashboard"))

    question = Question.query.get_or_404(id)

    sections = Section.query.order_by(
        Section.section_name
    ).all()

    if request.method == "POST":

        question.section_id = request.form["section_id"]
        question.question = request.form["question"]
        question.option_a = request.form["option_a"]
        question.option_b = request.form["option_b"]
        question.option_c = request.form["option_c"]
        question.option_d = request.form["option_d"]
        question.answer = request.form["answer"]
        question.explanation = request.form["explanation"]
        question.difficulty = request.form["difficulty"]

        db.session.commit()

        flash("Question Updated Successfully!", "success")

        return redirect(url_for("view_questions"))

    return render_template(
        "edit_question.html",
        question=question,
        sections=sections
    )
# ==========================================
# Delete Question
# ==========================================

@app.route("/admin/delete_question/<int:id>")
@login_required
def delete_question(id):

    if current_user.role != "admin":
        flash("Access Denied", "danger")
        return redirect(url_for("dashboard"))

    question = Question.query.get_or_404(id)

    db.session.delete(question)
    db.session.commit()

    flash("Question Deleted Successfully!", "success")

    return redirect(url_for("view_questions"))


# ==========================
# Logout
# ==========================

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))


# ==========================================
# Companies
# ==========================================

@app.route("/companies")
@login_required
def companies():
    company_list = [
        "TCS",
        "Accenture",
        "Infosys",
        "Wipro",
        "Capgemini",
        "Cognizant",
        "Deloitte",
        "EY"
    ]

    return render_template("companies.html", companies=company_list)


# ==========================================
# Previous Papers
# ==========================================

@app.route("/papers/<company>")
@login_required
def papers(company):
    years = [2025, 2024, 2023, 2022, 2021]

    return render_template("papers.html", company=company, years=years)


# ==========================================
# Paper Sections
# ==========================================

@app.route("/sections/<company>/<int:year>")
@login_required
def sections(company, year):

    # Find the company
    company_obj = Company.query.filter_by(
        company_name=company
    ).first_or_404()

    # Find the paper for that company and year
    paper = Paper.query.filter_by(
        company_id=company_obj.id,
        year=year
    ).first_or_404()

    # Get all sections of that paper
    section_list = Section.query.filter_by(
        paper_id=paper.id
    ).all()

    section_data = []

    for sec in section_list:

        total_questions = Question.query.filter_by(
            section_id=sec.id
        ).count()

        section_data.append({
            "id": sec.id,
            "name": sec.section_name,
            "questions": total_questions
        })

    return render_template(
        "sections.html",
        company=company,
        year=year,
        sections=section_data
    )

@app.route("/exam/<company>/<int:year>/<section>", methods=["GET", "POST"])
@login_required
def exam(company, year, section):

    company_obj = Company.query.filter_by(
        company_name=company
    ).first_or_404()

    paper = Paper.query.filter_by(
        company_id=company_obj.id,
        year=year
    ).first_or_404()

    selected_section = Section.query.filter_by(
        paper_id=paper.id,
        section_name=section
    ).first_or_404()

    questions = Question.query.filter_by(
        section_id=selected_section.id
    ).all()

    if request.method == "POST":

        score = 0

        for question in questions:

            user_answer = request.form.get(
                f"question_{question.id}"
            )

            if user_answer == question.answer:
                score += 1

        result = Result(
            user_id=current_user.id,
            company=company,
            year=year,
            section=selected_section.section_name,
            score=score,
            total=len(questions)
        )

        db.session.add(result)
        db.session.commit()

        flash("Exam Submitted Successfully!", "success")

        return redirect(
            url_for("result", result_id=result.id)
        )

    return render_template(
        "exam.html",
        company=company,
        year=year,
        section=selected_section,
        questions=questions
    )

# ==========================================
# Result Page
# ==========================================

@app.route("/result/<int:result_id>")
@login_required
def result(result_id):

    result = Result.query.get_or_404(result_id)

    return render_template(
        "result.html",
        result=result
    )
# ==========================================
# My Progress
# ==========================================

@app.route("/progress")
@login_required
def progress():

    results = Result.query.filter_by(
        user_id=current_user.id
    ).order_by(Result.id.desc()).all()

    total_exams = len(results)

    total_score = sum(r.score for r in results)

    total_questions = sum(r.total for r in results)

    average = 0

    if total_questions > 0:
        average = round((total_score / total_questions) * 100, 2)

    return render_template(
        "progress.html",
        results=results,
        total_exams=total_exams,
        average=average
    )

# ==========================================
# Student Profile
# ==========================================

@app.route("/profile")
@login_required
def profile():

    total_exams = Result.query.filter_by(
        user_id=current_user.id
    ).count()

    highest_score = 0

    results = Result.query.filter_by(
        user_id=current_user.id
    ).all()

    if results:
        highest_score = max(r.score for r in results)

    return render_template(
        "profile.html",
        user=current_user,
        total_exams=total_exams,
        highest_score=highest_score
    )

# ==========================================
# Change Password
# ==========================================

@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():

    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if not bcrypt.check_password_hash(current_user.password, current_password):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("change_password"))

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("change_password"))

        current_user.password = bcrypt.generate_password_hash(new_password).decode("utf-8")

        db.session.commit()

        flash("Password changed successfully!", "success")

        return redirect(url_for("profile"))

    return render_template("change_password.html")

# ==========================================
# Leaderboard
# ==========================================

@app.route("/leaderboard")
@login_required
def leaderboard():

    leaderboard = (
        db.session.query(
            User.name,
            db.func.sum(Result.score).label("total_score"),
            db.func.count(Result.id).label("total_exams")
        )
        .join(Result, User.id == Result.user_id)
        .group_by(User.id, User.name)
        .order_by(db.desc("total_score"))
        .all()
    )

    return render_template(
        "leaderboard.html",
        leaderboard=leaderboard
    )
# ==========================================
# PDF route
# ==========================================

@app.route("/download_result/<int:result_id>")
@login_required
def download_result(result_id):

    result = Result.query.get_or_404(result_id)

    if result.user_id != current_user.id and current_user.role != "admin":
        return "Unauthorized", 403

    buffer = BytesIO()

    pdf = canvas.Canvas(buffer, pagesize=letter)

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(180, 760, "PrepAI Exam Result")

    pdf.setFont("Helvetica", 12)

    pdf.drawString(60,720,f"Student : {current_user.name}")
    pdf.drawString(60,695,f"Company : {result.company}")
    pdf.drawString(60,670,f"Year : {result.year}")
    pdf.drawString(60,645,f"Section : {result.section}")
    pdf.drawString(60,620,f"Score : {result.score}/{result.total}")

    percentage = round((result.score/result.total)*100,2)

    pdf.drawString(60,595,f"Percentage : {percentage}%")

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="PrepAI_Result.pdf",
        mimetype="application/pdf"
    )

# ==========================================
# import questions
# ==========================================

@app.route("/import_questions", methods=["GET", "POST"])
@login_required
def import_questions():

    if current_user.role != "admin":
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        file = request.files["excel"]

        if file.filename == "":
            flash("Please select an Excel file.", "danger")
            return redirect(url_for("import_questions"))

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)

        df = pd.read_excel(filepath)

        for _, row in df.iterrows():

            section = Section.query.filter_by(
                section_name=row["Section"]
            ).first()

            if not section:
                continue

            question = Question(
                section_id=section.id,
                question=row["Question"],
                option_a=row["Option_A"],
                option_b=row["Option_B"],
                option_c=row["Option_C"],
                option_d=row["Option_D"],
                answer=row["Correct_Answer"],
                explanation=row["Explanation"],
                difficulty=row["Difficulty"]
            )

            db.session.add(question)

        db.session.commit()

        flash("Questions Imported Successfully!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("import_questions.html")
# ==========================================
# view section
# ==========================================
@app.route('/admin/sections')
@login_required
def view_sections():
    sections = Section.query.all()
    return render_template('view_sections.html', sections=sections)
# ==========================================
# delete section
# ==========================================
@app.route('/admin/delete_section/<int:id>')
@login_required
def delete_section(id):

    section = Section.query.get_or_404(id)

    # Delete all questions inside this section first
    Question.query.filter_by(section_id=section.id).delete()

    db.session.delete(section)
    db.session.commit()

    flash("Section deleted successfully!", "success")

    return redirect(url_for('view_sections'))

# ==========================================
# Create Database
# ==========================================

with app.app_context():
    db.create_all()

    admin = User.query.filter_by(email="admin@gmail.com").first()
    default_admin_password = "admin123"
    default_admin_hash = bcrypt.generate_password_hash(default_admin_password).decode("utf-8")

    if not admin:
        admin = User(
            name="Administrator",
            email="admin@gmail.com",
            password=default_admin_hash,
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin account created successfully!")
    else:
        changed = False
        if admin.role != "admin":
            admin.role = "admin"
            changed = True
            print("⚠️ Fixed admin role for existing admin account.")
        if not bcrypt.check_password_hash(admin.password, default_admin_password):
            admin.password = default_admin_hash
            changed = True
            print("⚠️ Reset admin password to the default admin123.")
        if changed:
            db.session.commit()
            print("✅ Admin account metadata corrected.")


# ==========================================
# Run Application
# ==========================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
