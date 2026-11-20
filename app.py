import os
import traceback
from PyPDF2 import PdfReader
from datetime import datetime
from dotenv import load_dotenv
from google import genai
import pandas as pd

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from flask_mail import Mail, Message
import random
import re

load_dotenv()

app = Flask(__name__)

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

def ask_gemini(prompt):
    if client is None:
        return "AI features are unavailable until GEMINI_API_KEY is configured."
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt
        )
        return response.text
    except Exception as e:
        return f"AI service is temporarily unavailable: {e}"

def ask_interview_gemini(prompt):
    """Generate a short interview turn without retrying a busy provider."""
    if client is None:
        app.logger.error("AI interview unavailable: GEMINI_API_KEY is not configured")
        return None
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_INTERVIEW_MODEL", "gemini-flash-latest"),
            contents=prompt,
            config={"temperature": 0.35, "max_output_tokens": 120}
        )
        text = (response.text or "").strip()
        return text or None
    except Exception:
        app.logger.exception("AI interview generation failed")
        return None

@app.route("/test_ai")
@login_required
def test_ai():

    answer = ask_gemini(
        "Introduce yourself as PrepAI Interview Assistant in 3 lines."
    )

    return f"<h2>{answer}</h2>"


# ==========================================
# App Configuration
# ==========================================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or os.urandom(32)
database_url = os.getenv("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True} if database_url else {}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
db = SQLAlchemy(app)

bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False

app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

app.config["MAIL_DEFAULT_SENDER"] = "khadarshaikk24@gmail.com"
app.config["MAIL_TIMEOUT"] = 15   

mail = Mail(app)

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

class InterviewResult(db.Model):

    __tablename__ = "interview_result"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    company = db.Column(db.String(100), nullable=False)

    role = db.Column(db.String(100), nullable=False)

    feedback = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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
    answer = db.Column(db.String(255))
    explanation = db.Column(db.Text)
    difficulty = db.Column(db.String(20))
    source_type = db.Column(db.String(40), nullable=False, default="generated_practice")
    source_name = db.Column(db.String(255), nullable=False, default="PrepAI generated practice")
    source_url = db.Column(db.Text)
    verified_at = db.Column(db.DateTime(timezone=True))


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
    return render_template(
        "index.html",
        company_count=Company.query.count(),
        paper_count=Paper.query.count(),
        question_count=Question.query.count()
    )


# ==========================
# Register
# ==========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm = request.form["confirm_password"]
        otp = request.form["otp"]

        # Allow only Gmail accounts
        if not email.endswith("@gmail.com"):
            flash("Only Gmail accounts are allowed.", "danger")
            return redirect(url_for("register"))

        # Verify OTP and Email
        if otp != session.get("otp") or email != session.get("email"):
            flash("Invalid OTP or Email.", "danger")
            return redirect(url_for("register"))

        # Password validation
        regex = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}$'

        if not re.match(regex, password):
            flash(
                "Password must contain at least 8 characters, one uppercase letter, one lowercase letter, one number and one special character.",
                "danger"
            )
            return redirect(url_for("register"))

        # Confirm password
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        # Check if email already exists
        user = User.query.filter_by(email=email).first()

        if user:
            flash("Email already exists.", "danger")
            return redirect(url_for("register"))

        # Encrypt password
        hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

        # Create new user
        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            role="user"
        )

        db.session.add(new_user)
        db.session.commit()

        # Clear OTP session
        session.pop("otp", None)
        session.pop("email", None)

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

    # ADD THIS
    users = User.query.order_by(User.id).all()

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        total_companies=total_companies,
        total_papers=total_papers,
        total_sections=total_sections,
        total_questions=total_questions,
        total_exams=total_exams,
        recent_results=recent_results,
        users=users          # ADD THIS
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
    company_list = Company.query.order_by(Company.company_name.asc()).all()
    return render_template("companies.html", companies=company_list)


# ==========================================
# Company practice papers
# ==========================================

@app.route("/papers/<company>")
@login_required
def papers(company):
    company_obj = Company.query.filter_by(company_name=company).first_or_404()
    papers_list = (Paper.query
                   .filter_by(company_id=company_obj.id)
                   .order_by(Paper.year.desc())
                   .all())
    return render_template("papers.html", company=company_obj.company_name,
                           papers=papers_list, years=[p.year for p in papers_list])


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

@app.route("/exam/<company>/<int:year>/<path:section>", methods=["GET", "POST"])
@login_required
def exam(company, year, section):

    company_obj = Company.query.filter_by(
        company_name=company
    ).first_or_404()

    paper = Paper.query.filter_by(
        company_id=company_obj.id,
        year=year
    ).first()
    if paper is None:
        flash(f"No {year} practice set is available for {company}. Choose an available year instead.", "warning")
        return redirect(url_for("papers", company=company_obj.company_name))

    selected_section = Section.query.filter_by(
        paper_id=paper.id,
        section_name=section
    ).first()

    if selected_section is None:
        normalized_section = section.strip().casefold()
        selected_section = next(
            (item for item in Section.query.filter_by(paper_id=paper.id).all()
             if item.section_name.strip().casefold() == normalized_section),
            None
        )

    if selected_section is None:
        flash(f'"{section}" is not listed for {company} {year}. Choose an available practice area.', "warning")
        return redirect(url_for("sections", company=company_obj.company_name, year=year))

    questions = Question.query.filter_by(
        section_id=selected_section.id
    ).all()

    if request.method == "POST":

        score = 0

        for question in questions:

            user_answer = request.form.get(
                f"question_{question.id}"
            )

            print("================================")
            print("Question ID :", question.id)
            print("Question    :", question.question)
            print("Selected    :", user_answer)
            print("Correct     :", question.answer)
            print("================================")

            if user_answer == question.answer:
                score += 1

        print(f"Final Score : {score}/{len(questions)}")

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

# Stable exam route: use the section's database ID instead of a URL-encoded
# section name. This avoids route/encoding mismatches for names such as
# "Logical Reasoning" and "Quantitative Aptitude".
@app.route("/exam/id/<int:section_id>", methods=["GET", "POST"])
@login_required
def exam_by_id(section_id):
    selected_section = Section.query.get_or_404(section_id)
    paper = Paper.query.get_or_404(selected_section.paper_id)
    company_obj = Company.query.get_or_404(paper.company_id)
    questions = Question.query.filter_by(section_id=selected_section.id).order_by(Question.id.asc()).all()

    if request.method == "POST":
        score = sum(
            1 for question in questions
            if request.form.get(f"question_{question.id}") == question.answer
        )
        result = Result(
            user_id=current_user.id,
            company=company_obj.company_name,
            year=paper.year,
            section=selected_section.section_name,
            score=score,
            total=len(questions)
        )
        db.session.add(result)
        db.session.commit()
        flash("Exam submitted successfully!", "success")
        return redirect(url_for("result", result_id=result.id))

    return render_template(
        "exam.html",
        company=company_obj.company_name,
        year=paper.year,
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
@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html"), 404


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

@app.route("/admin/students")
@login_required
def view_students():

    if current_user.role != "admin":
        return redirect(url_for("dashboard"))

    students = User.query.filter_by(role="user").all()

    return render_template("view_students.html", students=students)

# ==========================================
# send otp
# ==========================================

from flask import jsonify, session, request
from flask_mail import Message
import random

@app.route("/send_otp", methods=["POST"])
def send_otp():

    import random
    import re
    import traceback

    email = request.form.get("email", "").strip()

    # Validate Gmail address
    gmail_pattern = r'^[a-zA-Z0-9._%+-]+@gmail\.com$'

    if not re.match(gmail_pattern, email):
        return jsonify({
            "status": "error",
            "message": "Please enter a valid Gmail address."
        })

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))

    # Store OTP in session
    session["otp"] = otp
    session["email"] = email

    try:

        msg = Message(
            subject="PrepAI - Email Verification",
            sender=app.config["MAIL_DEFAULT_SENDER"],
            recipients=[email]
        )

        msg.html = f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;">

        <div style="
            max-width:600px;
            margin:auto;
            background:#ffffff;
            padding:30px;
            border-radius:10px;
            box-shadow:0 0 10px rgba(0,0,0,0.1);
        ">

            <h2 style="color:#0d6efd;text-align:center;">
                PrepAI
            </h2>

            <p>Hello,</p>

            <p>Thank you for registering with <b>PrepAI</b>.</p>

            <p>Your One-Time Password (OTP) is:</p>

            <h1 style="
                text-align:center;
                color:#0d6efd;
                letter-spacing:5px;
            ">
                {otp}
            </h1>

            <p>This OTP is valid for <b>5 minutes</b>.</p>

            <p>Please do not share this OTP with anyone.</p>

            <hr>

            <p style="text-align:center;color:gray;">
                PrepAI - AI Based Placement Preparation Portal
            </p>

        </div>

        </body>
        </html>
        """

        mail.send(msg)

        return jsonify({
            "status": "success",
            "message": "OTP sent successfully."
        })

    except Exception as e:

        traceback.print_exc()

        print("=" * 60)
        print("SMTP ERROR:", repr(e))
        print("=" * 60)

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
class ResultAnswer(db.Model):
    __tablename__ = "result_answers"

    id = db.Column(db.Integer, primary_key=True)

    result_id = db.Column(
        db.Integer,
        db.ForeignKey("results.id"),
        nullable=False
    )

    question_id = db.Column(
        db.Integer,
        db.ForeignKey("questions.id"),
        nullable=False
    )

    selected_answer = db.Column(db.String(255))

    result = db.relationship("Result", backref="answers")
    question = db.relationship("Question")

    
@app.route("/topic_practice")
@login_required
def topic_practice():
    return render_template("topic_practice.html")


@app.route("/mock_test")
@login_required
def mock_test():
    return render_template("mock_test.html")

@app.route("/ai_interview")
@login_required
def ai_interview():
    return render_template("ai_interview.html")


@app.route("/start_interview", methods=["POST"])
@login_required
def start_interview():
    company = request.form.get("company", "General").strip()
    role = request.form.get("role", "Software Engineer").strip()
    difficulty = request.form.get("difficulty", "Medium").strip()
    mode = request.form.get("mode", "Text").strip()

    # A real interview starts with an introduction, not a random technical quiz.
    question = "Good morning. Thank you for joining us. To begin, could you please introduce yourself and walk me through your background?"

    session["company"] = company
    session["role"] = role
    session["difficulty"] = difficulty
    session["mode"] = mode
    session["question_no"] = 1
    session["history"] = []

    return render_template(
        "interview.html", company=company, role=role,
        difficulty=difficulty, mode=mode,
        question=question, question_no=1
    )


@app.route("/submit_answer", methods=["POST"])
@login_required
def submit_answer():
    question = request.form.get("question", "").strip()
    answer = request.form.get("answer", "").strip()
    if not answer:
        flash("Please enter or speak an answer before submitting.", "warning")
        return redirect(url_for("ai_interview"))

    history = session.get("history", [])
    history.append({"question": question, "answer": answer})
    session["history"] = history
    question_no = session.get("question_no", 1)

    if question_no >= 10:
        prompt = f"""
You are a fair, experienced placement interviewer conducting a realistic {session['company']} interview for a {session['role']} role.
Assess only what the candidate actually said. Do not invent achievements or assume knowledge that was not demonstrated.
Interview transcript:
{history}

Give concise, useful feedback with:
Overall rating /10; communication /10; role knowledge /10;
2-3 strengths; 2-3 improvement areas; one example of how to improve a weak answer;
a clear hiring-style recommendation (Strong / Potential / Not yet ready);
and three specific next steps.
Be constructive and do not penalize a candidate for being nervous.
"""
        feedback = ask_gemini(prompt)
        result = InterviewResult(
            user_id=current_user.id,
            company=session["company"],
            role=session["role"],
            feedback=feedback
        )
        db.session.add(result)
        db.session.commit()

        company = session.get("company", "")
        role = session.get("role", "")
        session.pop("history", None)
        session.pop("question_no", None)
        session.pop("company", None)
        session.pop("role", None)
        session.pop("difficulty", None)
        session.pop("mode", None)

        return render_template(
            "feedback.html", company=company, role=role,
            question="Interview Completed",
            answer="You completed the 10-question interview.",
            feedback=feedback
        )

    next_no = question_no + 1
    transcript = "\n".join(
        f"Interviewer: {item['question']}\nCandidate: {item['answer']}"
        for item in history
    )
    prompt = f"""
You are a professional human placement interviewer at {session['company']}.
You are interviewing a candidate for {session['role']}. Difficulty: {session['difficulty']}.
This is question {next_no} of 10 in one continuous interview.

Conversation so far:
{transcript}

Conduct the interview naturally and progressively:
- Q2: ask about one project, responsibility, or experience mentioned in the introduction.
- Q3: ask a relevant follow-up about the candidate's own contribution or a challenge.
- Q4-Q7: assess role-related fundamentals and practical problem solving, one subject at a time.
- Q8: ask a scenario-based question relevant to the role.
- Q9: ask a behavioral question about teamwork, conflict, failure, or learning.
- Q10: ask a suitable closing question, such as why the candidate is a good fit or whether they have questions.

Adapt the next question to the candidate's previous answers. If they mention a specific project, skill, or technology, use it for a natural follow-up. Do not ask the same question again. Avoid generic quiz wording and avoid multiple questions in one turn. Ask exactly ONE clear question, with a brief natural interviewer transition if useful. Do not provide hints, answers, scoring, or explanations. Return only the interviewer’s spoken words.
"""
    next_question = ask_interview_gemini(prompt)
    if not next_question:
        # Keep the session usable if the model provider is temporarily unavailable.
        fallbacks = {
            2: "Thank you. Could you tell me about one project you have worked on and the problem it was designed to solve?",
            3: "What was your specific contribution to that project, and what was the most challenging part?",
            4: f"Which technical skill do you think is most important for a {session['role']}, and why?",
            5: "Can you describe a technical problem you faced and how you worked through it?",
            6: "How would you explain one of the technologies you used in your project to a non-technical person?",
            7: "If you had more time to improve your project, what would you change first?",
            8: "Suppose a critical issue appears just before a deadline. How would you investigate and handle it?",
            9: "Tell me about a time you received feedback or made a mistake. How did you respond?",
            10: "Why do you think you are a good fit for this role?"
        }
        next_question = fallbacks.get(next_no, "What would you like us to know about your approach to this role?")

    session["question_no"] = next_no
    return render_template(
        "interview.html", company=session["company"], role=session["role"],
        difficulty=session["difficulty"], mode=session["mode"],
        question=next_question, question_no=next_no
    )

@app.route("/interview_history")
@login_required
def interview_history():

    interviews = InterviewResult.query.filter_by(
        user_id=current_user.id
    ).order_by(
        InterviewResult.created_at.desc()
    ).all()

    return render_template(
        "interview_history.html",
        interviews=interviews
    )

@app.route("/resume_analyzer", methods=["GET", "POST"])
@login_required
def resume_analyzer():

    if request.method == "POST":

        file = request.files["resume"]

        reader = PdfReader(file)

        text = ""

        for page in reader.pages:
            text += page.extract_text() or ""

        prompt = f"""
You are an ATS Resume Reviewer.

Analyze this resume.

Resume:

{text}

Give:

1. ATS Score (/100)

2. Strengths

3. Weaknesses

4. Missing Skills

5. Improvement Suggestions

6. Overall Recommendation
"""

        feedback = ask_gemini(prompt)

        return render_template(
            "resume_feedback.html",
            feedback=feedback
        )

    return render_template("resume_analyzer.html")

@app.route("/roadmap", methods=["GET", "POST"])
@login_required
def roadmap():

    if request.method == "POST":

        company = request.form["company"]
        language = request.form["language"]
        year = request.form["year"]

        prompt = f"""
You are a placement mentor.

Student Year: {year}
Target Company: {company}
Programming Language: {language}

Generate a complete preparation roadmap.

Include:

1. Aptitude Topics
2. Coding Topics
3. Core Subjects
4. HR Preparation
5. Projects to Build
6. Weekly Plan
7. Interview Tips

Return in a clean format.
"""

        roadmap = ask_gemini(prompt)

        return render_template(
            "roadmap_result.html",
            roadmap=roadmap
        )

    return render_template("roadmap.html")

@app.route("/chatbot", methods=["GET", "POST"])
@login_required
def chatbot():

    if request.method == "POST":

        question = request.form["question"]

        prompt = f"""
You are PrepAI Assistant.

Your job is to help students preparing for placements.

You can answer only about:

- Aptitude
- Coding
- Programming
- DBMS
- OS
- CN
- OOP
- Java
- Python
- C
- C++
- SQL
- HR Interview
- Technical Interview
- Resume
- Placement Preparation
- Career Guidance

Question:
{question}

If the question is unrelated to placement, politely say that you only assist with placement preparation.

Keep answers clear and concise.
"""

        answer = ask_gemini(prompt)

        return render_template(
            "chatbot.html",
            question=question,
            answer=answer
        )

    return render_template("chatbot.html")

@app.route("/delete_user/<int:user_id>")
@login_required
def delete_user(user_id):

    if current_user.email != "khadarshaikk24@gmail.com":
        flash("Access Denied!", "danger")
        return redirect(url_for("dashboard"))

    user = User.query.get_or_404(user_id)

    # Prevent admin from deleting themselves
    if user.email == "khadarshaikk24@gmail.com":
        flash("Admin account cannot be deleted.", "warning")
        return redirect(url_for("admin_dashboard"))

    # Delete data linked to this user before deleting the user
    ResultAnswer.query.filter(
        ResultAnswer.result_id.in_(
            db.session.query(Result.id).filter_by(user_id=user.id)
        )
    ).delete(synchronize_session=False)

    Result.query.filter_by(user_id=user.id).delete(
        synchronize_session=False
    )

    InterviewResult.query.filter_by(user_id=user.id).delete(
        synchronize_session=False
    )

    db.session.delete(user)
    db.session.commit()

    flash("User and related data deleted successfully!", "success")

    return redirect(url_for("admin_dashboard"))

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"]

        user = User.query.filter_by(email=email).first()

        if not user:
            flash("Email not registered!", "danger")
            return redirect(url_for("forgot_password"))

        otp = str(random.randint(100000, 999999))

        session["reset_email"] = email
        session["reset_otp"] = otp

        msg = Message(
            "PrepAI Password Reset OTP",
            sender=app.config["MAIL_USERNAME"],
            recipients=[email]
        )

        msg.body = f"Your password reset OTP is: {otp}"

        mail.send(msg)

        flash("OTP sent to your email.", "success")

        return redirect(url_for("verify_reset_otp"))

    return render_template("forgot_password.html")

@app.route("/verify_reset_otp", methods=["GET", "POST"])
def verify_reset_otp():

    if request.method == "POST":

        otp = request.form["otp"]

        if otp == session.get("reset_otp"):

            flash("OTP Verified Successfully!", "success")

            return redirect(url_for("reset_password"))

        else:

            flash("Invalid OTP!", "danger")

    return render_template("verify_reset_otp.html")

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():

    if "reset_email" not in session:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":

        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for("reset_password"))

        user = User.query.filter_by(
            email=session["reset_email"]
        ).first()

        user.password = bcrypt.generate_password_hash(password).decode("utf-8")

        db.session.commit()

        session.pop("reset_email", None)
        session.pop("reset_otp", None)

        flash("Password changed successfully! Please login.", "success")

        return redirect(url_for("login"))

    return render_template("reset_password.html")

# ==========================================
# Create Database
# ==========================================

with app.app_context():
    if app.config["SQLALCHEMY_DATABASE_URI"]:
        db.create_all()
        # Optional first-admin bootstrap. Existing accounts are never reset.
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if admin_email and admin_password:
            existing_admin = User.query.filter_by(email=admin_email).first()
            if not existing_admin:
                admin = User(
                    name=os.getenv("ADMIN_NAME", "PrepAI Administrator"),
                    email=admin_email,
                    password=bcrypt.generate_password_hash(admin_password).decode("utf-8"),
                    role="admin"
                )
                db.session.add(admin)
                db.session.commit()
    else:
        app.logger.error("DATABASE_URL is missing. Configure the Supabase PostgreSQL connection string.")


# ==========================================
# Run Application
# ==========================================

from student_practice import create_practice_blueprint
app.register_blueprint(create_practice_blueprint(db, Company, Paper, Section, Question, Result))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
