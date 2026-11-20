"""Independent topic-practice and company-wide mock-test workflows."""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func


def create_practice_blueprint(db, Company, Paper, Section, Question, Result):
    bp = Blueprint("practice", __name__)

    TOPICS = {
        "quantitative": {
            "name": "Quantitative Aptitude", "icon": "∑",
            "description": "Percentages, ratios, averages, profit and loss, time and work, probability.",
            "aliases": ("quantitative", "aptitude", "numerical")
        },
        "reasoning": {
            "name": "Logical Reasoning", "icon": "◇",
            "description": "Series, arrangements, puzzles, coding-decoding and analytical reasoning.",
            "aliases": ("logical", "reasoning", "analytical")
        },
        "verbal": {
            "name": "Verbal Ability", "icon": "Aa",
            "description": "Grammar, vocabulary, comprehension, sentence correction and verbal logic.",
            "aliases": ("verbal", "english", "communication", "grammar")
        },
        "technical": {
            "name": "Technical MCQs", "icon": "</>",
            "description": "Programming fundamentals, DBMS, operating systems and computer networks.",
            "aliases": ("technical", "dbms", "operating system", "computer network", "java", "python", "programming fundamentals", "computer fundamentals")
        },
        "coding": {
            "name": "Coding Practice", "icon": "{ }",
            "description": "Problem solving, algorithms, arrays, strings, recursion and data structures.",
            "aliases": ("coding", "algorithm", "data structure", "programming")
        },
        "mixed": {
            "name": "Mixed Practice", "icon": "✦",
            "description": "A balanced random set drawn from all available practice sections.",
            "aliases": ()
        }
    }

    @bp.get("/practice/topics")
    @login_required
    def topic_library():
        topic_cards = []
        for slug, topic in TOPICS.items():
            if slug == "mixed":
                count = Question.query.count()
            else:
                filters = [Section.section_name.ilike(f"%{alias}%") for alias in topic["aliases"]]
                count = (db.session.query(Question.id).join(Section, Question.section_id == Section.id)
                         .filter(db.or_(*filters)).count()) if filters else 0
            topic_cards.append({**topic, "slug": slug, "count": count})
        return render_template("topic_practice.html", topics=topic_cards)

    @bp.route("/practice/topic/<slug>", methods=["GET", "POST"])
    @login_required
    def topic_exam(slug):
        topic = TOPICS.get(slug)
        if not topic:
            flash("That practice topic is not available.", "warning")
            return redirect(url_for("practice.topic_library"))

        query = Question.query.join(Section, Question.section_id == Section.id)
        if slug != "mixed":
            filters = [Section.section_name.ilike(f"%{alias}%") for alias in topic["aliases"]]
            query = query.filter(db.or_(*filters))
        questions = query.order_by(func.random()).limit(20).all()

        if request.method == "POST":
            score = sum(1 for q in questions if request.form.get(f"question_{q.id}") == q.answer)
            result = Result(user_id=current_user.id, company="Topic Practice",
                            year=datetime.now().year, section=topic["name"],
                            score=score, total=len(questions))
            db.session.add(result)
            db.session.commit()
            return redirect(url_for("result", result_id=result.id))

        return render_template("multi_exam.html", title=topic["name"],
                               subtitle="Topic-wise practice · 20-question set",
                               context_label="TOPIC PRACTICE", company_label="PrepAI",
                               year_label="Practice", questions=questions,
                               duration_minutes=25, back_url=url_for("practice.topic_library"))

    @bp.get("/mock-tests")
    @login_required
    def mock_test_library():
        companies = Company.query.order_by(Company.company_name.asc()).all()
        papers = (db.session.query(Paper, Company.company_name)
                  .join(Company, Paper.company_id == Company.id)
                  .order_by(Company.company_name.asc(), Paper.year.desc()).all())
        paper_cards = []
        for paper, company_name in papers:
            total = (db.session.query(Question.id).join(Section, Question.section_id == Section.id)
                     .filter(Section.paper_id == paper.id).count())
            section_count = Section.query.filter_by(paper_id=paper.id).count()
            paper_cards.append({"id": paper.id, "company": company_name, "year": paper.year,
                                "questions": total, "sections": section_count})
        return render_template("mock_test.html", companies=companies, papers=paper_cards)

    @bp.route("/mock-tests/start/<int:paper_id>", methods=["GET", "POST"])
    @login_required
    def start_full_mock(paper_id):
        paper = Paper.query.get_or_404(paper_id)
        company = Company.query.get_or_404(paper.company_id)
        questions = (Question.query.join(Section, Question.section_id == Section.id)
                     .filter(Section.paper_id == paper.id)
                     .order_by(Section.id.asc(), Question.id.asc()).all())
        if not questions:
            flash("This company-year paper has no questions yet.", "warning")
            return redirect(url_for("practice.mock_test_library"))

        if request.method == "POST":
            score = sum(1 for q in questions if request.form.get(f"question_{q.id}") == q.answer)
            result = Result(user_id=current_user.id, company=company.company_name,
                            year=paper.year, section="Full Mock Test",
                            score=score, total=len(questions))
            db.session.add(result)
            db.session.commit()
            return redirect(url_for("result", result_id=result.id))

        return render_template("multi_exam.html",
                               title=f"{company.company_name} · {paper.year} Full Mock Test",
                               subtitle="One complete assessment covering every section in this company-year paper.",
                               context_label="FULL COMPANY MOCK TEST",
                               company_label=company.company_name, year_label=paper.year,
                               questions=questions, duration_minutes=90,
                               back_url=url_for("practice.mock_test_library"))

    return bp
