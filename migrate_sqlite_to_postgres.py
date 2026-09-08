import sqlite3
from app import app, db
from app import (
    User,
    Company,
    Paper,
    Section,
    Question,
    Result,
    ResultAnswer,
    InterviewResult,
)

sqlite_conn = sqlite3.connect("recovered_database.db")
sqlite_conn.row_factory = sqlite3.Row
cursor = sqlite_conn.cursor()


def migrate_table(table_name, model):
    rows = cursor.execute(f"SELECT * FROM {table_name}").fetchall()

    for row in rows:
        data = dict(row)

        # Skip if already exists
        if model.query.get(data["id"]):
            continue
        if model is User and User.query.filter_by(email=data["email"]).first():
            continue

        obj = model(**data)
        db.session.add(obj)

    db.session.commit()
    print(f"✅ {table_name}: {len(rows)} rows migrated")


with app.app_context():
    db.create_all()

    migrate_table("users", User)
    migrate_table("companies", Company)
    migrate_table("papers", Paper)
    migrate_table("sections", Section)
    migrate_table("questions", Question)
    migrate_table("results", Result)
    migrate_table("result_answers", ResultAnswer)
    migrate_table("interview_result", InterviewResult)

print("\n🎉 Migration completed successfully!")