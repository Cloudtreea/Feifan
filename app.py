import json
import os
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
database_url = os.getenv("DATABASE_URL", "sqlite:///history_match_demo.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    JSON_AS_ASCII=False,
)
db = SQLAlchemy(app)

MODULES = ("ancient", "modern", "world")
MODULE_ALIASES = {
    "china-ancient": "ancient",
    "china-modern": "modern",
    "world": "world",
    "ancient": "ancient",
    "modern": "modern",
}


def load_question_bank_manifest():
    path = os.path.join(BASE_DIR, "question_bank_manifest.json")
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    totals = manifest.get("knowledgeTotals", {})
    if set(totals) != {"ancient", "modern", "world"} or any(int(value) <= 0 for value in totals.values()):
        raise RuntimeError("question_bank_manifest.json contains invalid knowledge totals")
    manifest["knowledgeTotals"] = {key: int(value) for key, value in totals.items()}
    return manifest


QUESTION_BANK_MANIFEST = load_question_bank_manifest()
MODULE_KNOWLEDGE_TOTALS = QUESTION_BANK_MANIFEST["knowledgeTotals"]
MASTERY_UNSEEN_PRIOR = 35
MASTERY_COVERAGE_EXPONENT = 0.65


def coverage_adjusted_mastery(observed_average, practiced_count, total_count):
    """Blend observed performance with a neutral prior until coverage is sufficient."""
    total = max(1, int(total_count or 0))
    practiced = max(0, min(total, int(practiced_count or 0)))
    if not practiced or observed_average is None:
        return 0, 0, 0
    coverage = practiced / total
    reliability = coverage ** MASTERY_COVERAGE_EXPONENT
    adjusted = round(float(observed_average) * reliability + MASTERY_UNSEEN_PRIOR * (1 - reliability))
    return max(0, min(100, adjusted)), round(coverage * 100), round(reliability * 100)


def mastery_evidence_state(score, coverage_percent, practiced_count):
    """Describe whether the current percentage is sufficiently supported for teaching use."""
    if practiced_count == 0 or coverage_percent < 30:
        return {"key": "insufficient", "label": "证据不足"}
    if score < 65:
        return {"key": "weak", "label": "暴露薄弱"}
    if score >= 85 and coverage_percent >= 60:
        return {"key": "stable", "label": "稳定掌握"}
    return {"key": "developing", "label": "持续积累"}


class SchoolClass(db.Model):
    __tablename__ = "school_classes"
    id = db.Column(db.String(32), primary_key=True)
    grade_id = db.Column(db.String(16), nullable=False, index=True)
    name = db.Column(db.String(40), nullable=False)


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.String(48), primary_key=True)
    display_name = db.Column(db.String(40), nullable=False)
    grade_id = db.Column(db.String(16), nullable=False, index=True)
    class_id = db.Column(db.String(32), nullable=False, index=True)
    demo = db.Column(db.Boolean, nullable=False, default=True)


class LearningEvent(db.Model):
    __tablename__ = "learning_events"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(80), nullable=False, unique=True, index=True)
    session_id = db.Column(db.String(80), index=True)
    student_id = db.Column(db.String(48), nullable=False, index=True)
    event_type = db.Column(db.String(48), nullable=False, index=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=False)


class GameSession(db.Model):
    __tablename__ = "game_sessions"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(80), nullable=False, unique=True, index=True)
    student_id = db.Column(db.String(48), nullable=False, index=True)
    module_id = db.Column(db.String(24), nullable=False, index=True)
    relation_type = db.Column(db.String(32))
    board_size = db.Column(db.Integer, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    game_score = db.Column(db.Integer, nullable=False, default=0)
    independent_accuracy = db.Column(db.Integer, nullable=False, default=0)
    assessed_wrong_attempts = db.Column(db.Integer, nullable=False, default=0)
    raw_wrong_attempts = db.Column(db.Integer, nullable=False, default=0)
    first_reveal_exemptions = db.Column(db.Integer, nullable=False, default=0)
    hint_count = db.Column(db.Integer, nullable=False, default=0)


class PairResult(db.Model):
    __tablename__ = "pair_results"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(80), nullable=False, index=True)
    student_id = db.Column(db.String(48), nullable=False, index=True)
    module_id = db.Column(db.String(24), nullable=False, index=True)
    pair_id = db.Column(db.String(120), nullable=False)
    knowledge_id = db.Column(db.String(120), nullable=False, index=True)
    evidence_score = db.Column(db.Integer, nullable=False)
    wrong_attempts = db.Column(db.Integer, nullable=False, default=0)
    raw_wrong_attempts = db.Column(db.Integer, nullable=False, default=0)
    first_reveal_exemptions = db.Column(db.Integer, nullable=False, default=0)
    hint_used = db.Column(db.Boolean, nullable=False, default=False)
    clue_visible = db.Column(db.Boolean, nullable=False, default=False)
    completed = db.Column(db.Boolean, nullable=False, default=True)
    occurred_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    __table_args__ = (UniqueConstraint("session_id", "pair_id", name="uq_session_pair"),)


class MasterySnapshot(db.Model):
    __tablename__ = "mastery_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(48), nullable=False, index=True)
    module_id = db.Column(db.String(24), nullable=False, index=True)
    knowledge_id = db.Column(db.String(120), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(16), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint("student_id", "knowledge_id", name="uq_student_knowledge"),)


def utcnow():
    return datetime.now(timezone.utc)


def parse_time(value):
    if not value:
        return utcnow()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return utcnow()


def normalized_module(value):
    return MODULE_ALIASES.get(value, "ancient")


BOARD_EVIDENCE_ADJUST = {3: -6, 4: 0, 5: 6}


def evidence_score(result, board_size=3):
    if not result.get("completed", True):
        score = 20
    else:
        wrong = int(result.get("wrongAttempts", 0) or 0)
        score = 96 if wrong == 0 else 80 if wrong == 1 else max(48, 80 - (wrong - 1) * 12)
        score += BOARD_EVIDENCE_ADJUST.get(int(board_size or 3), 0)
        score += {"识记": -2, "理解": 2, "辨析": 4}.get(result.get("cognitiveLevel"), 0)
    if result.get("clueVisible"):
        score *= 0.97
    if result.get("hintUsed"):
        score *= 0.95
    if result.get("checkpointCorrect") is True:
        score += 10
    elif result.get("checkpointCorrect") is False:
        score -= 12
    return max(0, min(100, round(score)))


def mastery_status(score):
    if score >= 85:
        return "已掌握"
    if score >= 65:
        return "基本掌握"
    if score >= 40:
        return "需要巩固"
    return "重点复习"


def ensure_demo_data():
    if SchoolClass.query.first():
        return
    grade_names = {"g1": "高一", "g2": "高二", "g3": "高三"}
    for grade_id, grade_name in grade_names.items():
        for class_no in range(1, 4):
            class_id = f"{grade_id}c{class_no}"
            db.session.add(SchoolClass(id=class_id, grade_id=grade_id, name=f"{grade_name}（{class_no}）班"))
            for index in range(1, 9):
                student_id = f"demo-s{grade_id[-1]}{class_no}{index:02d}"
                db.session.add(Student(id=student_id, display_name=f"学生{index:02d}", grade_id=grade_id, class_id=class_id))
    db.session.commit()


def ensure_student(event):
    student_id = str(event.get("studentId") or "demo-s2101")[:48]
    student = db.session.get(Student, student_id)
    if student:
        return student
    grade_id = str(event.get("gradeId") or "g2")[:16]
    class_id = str(event.get("classId") or f"{grade_id}c1")[:32]
    school_class = db.session.get(SchoolClass, class_id)
    if not school_class:
        school_class = SchoolClass(id=class_id, grade_id=grade_id, name=f"{grade_id} 演示班")
        db.session.add(school_class)
    student = Student(id=student_id, display_name=f"学生{student_id[-4:]}", grade_id=grade_id, class_id=class_id)
    db.session.add(student)
    return student


def refresh_mastery(student_id, knowledge_id, module_id, occurred_at):
    rows = (PairResult.query.filter_by(student_id=student_id, knowledge_id=knowledge_id)
            .order_by(PairResult.occurred_at.desc()).limit(5).all())
    weights = (0.40, 0.25, 0.15, 0.12, 0.08)
    used = sum(weights[:len(rows)])
    score = round(sum(row.evidence_score * weights[index] for index, row in enumerate(rows)) / used)
    snapshot = MasterySnapshot.query.filter_by(student_id=student_id, knowledge_id=knowledge_id).first()
    if not snapshot:
        snapshot = MasterySnapshot(student_id=student_id, knowledge_id=knowledge_id, module_id=module_id)
        db.session.add(snapshot)
    snapshot.score = score
    snapshot.status = mastery_status(score)
    snapshot.updated_at = occurred_at


def ingest_completed_session(event):
    session_id = event.get("sessionId")
    if not session_id or GameSession.query.filter_by(session_id=session_id).first():
        return
    student_id = str(event.get("studentId"))
    module_id = normalized_module(event.get("moduleId"))
    occurred_at = parse_time(event.get("timestamp"))
    results = event.get("pairResults") or []
    raw_wrong = sum(int(item.get("rawWrongAttempts", 0) or 0) for item in results)
    exemptions = sum(int(item.get("firstRevealExemptions", 0) or 0) for item in results)
    board_size = int(event.get("boardSize", 3) or 3)
    db.session.add(GameSession(
        session_id=session_id, student_id=student_id, module_id=module_id,
        relation_type=event.get("relationType"), board_size=board_size,
        completed_at=occurred_at, game_score=int(event.get("gameScore", 0) or 0),
        independent_accuracy=int(event.get("independentAccuracy", 0) or 0),
        assessed_wrong_attempts=int(event.get("assessedWrongAttempts", 0) or 0),
        raw_wrong_attempts=raw_wrong, first_reveal_exemptions=exemptions,
        hint_count=int(event.get("hintCount", 0) or 0),
    ))
    for item in results:
        pair_id = str(item.get("pairId") or "")
        knowledge_id = str(item.get("knowledgeId") or pair_id)
        if not pair_id:
            continue
        db.session.add(PairResult(
            session_id=session_id, student_id=student_id, module_id=module_id,
            pair_id=pair_id, knowledge_id=knowledge_id, evidence_score=evidence_score(item, board_size),
            wrong_attempts=int(item.get("wrongAttempts", 0) or 0),
            raw_wrong_attempts=int(item.get("rawWrongAttempts", 0) or 0),
            first_reveal_exemptions=int(item.get("firstRevealExemptions", 0) or 0),
            hint_used=bool(item.get("hintUsed")), clue_visible=bool(item.get("clueVisible")),
            completed=bool(item.get("completed", True)), occurred_at=occurred_at,
        ))
        db.session.flush()
        refresh_mastery(student_id, knowledge_id, module_id, occurred_at)


def student_rows(grade, class_id):
    query = Student.query
    if grade != "all":
        query = query.filter_by(grade_id=grade)
    if class_id != "all":
        query = query.filter_by(class_id=class_id)
    return query.all()


def student_metrics(student):
    sessions = GameSession.query.filter_by(student_id=student.id).all()
    scores, coverage = {}, {}
    for module in MODULES:
        rows = MasterySnapshot.query.filter_by(student_id=student.id, module_id=module).all()
        practiced = len({row.knowledge_id for row in rows})
        observed = sum(row.score for row in rows) / len(rows) if rows else None
        total = MODULE_KNOWLEDGE_TOTALS[module]
        score, percent, reliability = coverage_adjusted_mastery(observed, practiced, total)
        scores[module] = score
        coverage[module] = {
            "practiced": practiced, "total": total, "percent": percent,
            "observedAverage": round(observed) if observed is not None else 0,
            "reliability": reliability,
            "state": mastery_evidence_state(score, percent, practiced),
        }
    latest = max((row.completed_at for row in sessions), default=None)
    last = 999 if latest is None else max(0, (utcnow().date() - latest.date()).days)
    pair_count = PairResult.query.filter_by(student_id=student.id).count()
    hint_count = PairResult.query.filter_by(student_id=student.id, hint_used=True).count()
    return {
        "id": student.id, "name": student.display_name, "grade": student.grade_id,
        "clazz": student.class_id, "className": db.session.get(SchoolClass, student.class_id).name,
        "scores": scores, "coverage": coverage,
        "learningState": next((item["state"] for item in coverage.values() if item["state"]["key"] == "weak"),
                              next((item["state"] for item in coverage.values() if item["state"]["key"] == "insufficient"),
                                   {"key": "stable", "label": "稳定掌握"}
                                   if coverage and all(item["state"]["key"] == "stable" for item in coverage.values())
                                   else {"key": "developing", "label": "持续积累"})),
        "games": len(sessions),
        "hints": round(hint_count / max(1, pair_count) * 100), "last": last,
    }


def aggregate(metrics):
    count = len(metrics)
    mods = {module: round(sum(row["scores"][module] for row in metrics) / max(1, count)) for module in MODULES}
    coverage = {
        module: round(sum(row["coverage"][module]["percent"] for row in metrics) / max(1, count))
        for module in MODULES
    }
    practiced = [value for row in metrics for value in row["scores"].values() if value > 0]
    return {
        "count": count, "active": sum(row["last"] < 7 for row in metrics),
        "games": sum(row["games"] for row in metrics),
        "average": round(sum(practiced) / len(practiced)) if practiced else 0,
        "mods": mods, "coverage": coverage,
        "risk": sum(row["learningState"]["key"] == "weak" for row in metrics),
    }


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "memory_station.html")


@app.get("/student")
def student_page():
    return send_from_directory(BASE_DIR, "memory_station.html")


@app.get("/teacher")
def teacher_page():
    return send_from_directory(BASE_DIR, "teacher_dashboard.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", database="connected", timestamp=utcnow().isoformat(),
                   questionBank={"version": QUESTION_BANK_MANIFEST["version"],
                                 "knowledgeTotals": MODULE_KNOWLEDGE_TOTALS})


@app.post("/api/v1/learning-events/batch")
def receive_events():
    body = request.get_json(silent=True) or {}
    events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(events, list) or len(events) > 50:
        return jsonify(error="events must be an array with at most 50 items"), 400
    accepted, duplicates, rejected = [], [], []
    for event in events:
        event_id = str(event.get("eventId") or "")
        if not event_id:
            rejected.append({"eventId": None, "reason": "missing_event_id"})
            continue
        if LearningEvent.query.filter_by(event_id=event_id).first():
            duplicates.append(event_id)
            continue
        ensure_student(event)
        db.session.add(LearningEvent(
            event_id=event_id, session_id=event.get("sessionId"), student_id=str(event.get("studentId")),
            event_type=str(event.get("type") or "unknown"), occurred_at=parse_time(event.get("timestamp")),
            payload=json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        ))
        if event.get("type") == "session_completed":
            ingest_completed_session(event)
        accepted.append(event_id)
    db.session.commit()
    return jsonify(acceptedEventIds=accepted, duplicateEventIds=duplicates, rejected=rejected,
                   acknowledgedEventIds=accepted + duplicates)


@app.get("/api/v1/teacher/dashboard")
def teacher_dashboard():
    grade, class_id = request.args.get("grade", "all"), request.args.get("clazz", "all")
    students = student_rows(grade, class_id)
    metrics = [student_metrics(student) for student in students]
    classes_query = SchoolClass.query
    if grade != "all":
        classes_query = classes_query.filter_by(grade_id=grade)
    classes = classes_query.order_by(SchoolClass.id).all()
    if class_id != "all":
        classes = [item for item in classes if item.id == class_id]
    since = utcnow().date() - timedelta(days=6)
    trend = []
    student_ids = [student.id for student in students]
    for offset in range(7):
        day = since + timedelta(days=offset)
        count = (GameSession.query.filter(GameSession.student_id.in_(student_ids),
                 func.date(GameSession.completed_at) == day.isoformat()).count() if student_ids else 0)
        trend.append(count)
    latest_event = db.session.query(func.max(LearningEvent.occurred_at)).scalar()
    return jsonify(
        summary=aggregate(metrics), trend=trend,
        classes=[{"info": {"id": item.id, "grade": item.grade_id, "name": item.name},
                  **aggregate([row for row in metrics if row["clazz"] == item.id])} for item in classes],
        classesMeta=[{"id": item.id, "grade": item.grade_id, "name": item.name} for item in SchoolClass.query.order_by(SchoolClass.id)],
        sync={"receivedEvents": LearningEvent.query.count(), "completedSessions": GameSession.query.count(),
              "duplicateProtection": "eventId", "success": 100,
              "updatedAt": latest_event.isoformat() if latest_event else None},
        updatedAt=utcnow().isoformat(),
    )


@app.get("/api/v1/teacher/students")
def teacher_students():
    grade, class_id = request.args.get("grade", "all"), request.args.get("clazz", "all")
    module, status = request.args.get("module", "all"), request.args.get("status", "all")
    search = request.args.get("search", "").lower()
    page, page_size = max(1, request.args.get("page", 1, type=int)), min(50, request.args.get("pageSize", 8, type=int))
    rows = [student_metrics(student) for student in student_rows(grade, class_id)]
    if search:
        rows = [row for row in rows if search in row["id"].lower() or search in row["name"].lower()]
    if status == "risk":
        rows = [row for row in rows if row["learningState"]["key"] == "weak"]
    elif status == "good":
        rows = [row for row in rows if row["learningState"]["key"] == "stable"]
    key = (lambda row: min(row["scores"].values())) if module == "all" else (lambda row: row["scores"].get(module, 0))
    rows.sort(key=key)
    start = (page - 1) * page_size
    return jsonify(rows=rows[start:start + page_size], total=len(rows), page=page, pageSize=page_size)


@app.get("/api/v1/teacher/students/<student_id>")
def teacher_student(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify(error="student_not_found"), 404
    metrics = student_metrics(student)
    sessions = GameSession.query.filter_by(student_id=student_id).order_by(GameSession.completed_at.desc()).limit(5).all()
    recent = [{"module": row.module_id, "done": True, "hints": row.hint_count,
               "boardSize": row.board_size, "gameScore": row.game_score,
               "accuracy": row.independent_accuracy, "rawWrongAttempts": row.raw_wrong_attempts,
               "assessedWrongAttempts": row.assessed_wrong_attempts,
               "firstRevealExemptions": row.first_reveal_exemptions,
               "date": row.completed_at.isoformat()} for row in sessions]
    evidence = PairResult.query.filter_by(student_id=student_id).order_by(PairResult.occurred_at.desc()).limit(20).all()
    session_ids = {row.session_id for row in evidence}
    board_by_session = {row.session_id: row.board_size for row in GameSession.query.filter(GameSession.session_id.in_(session_ids)).all()} if session_ids else {}
    evidence_counts = {}
    evidence_boards = {}
    for row in PairResult.query.filter_by(student_id=student_id).all():
        evidence_counts[row.knowledge_id] = evidence_counts.get(row.knowledge_id, 0) + 1
        board = board_by_session.get(row.session_id)
        if board is None:
            session = GameSession.query.filter_by(session_id=row.session_id).first()
            board = session.board_size if session else 3
        evidence_boards.setdefault(row.knowledge_id, set()).add(board)
    return jsonify(student=metrics, recent=recent, evidence=[{
        "knowledgeId": row.knowledge_id, "module": row.module_id, "score": row.evidence_score,
        "boardSize": board_by_session.get(row.session_id, 3),
        "evidenceCount": evidence_counts.get(row.knowledge_id, 1),
        "confidence": ("高" if evidence_counts.get(row.knowledge_id, 1) >= 5 and len(evidence_boards.get(row.knowledge_id, ())) >= 2
                       else "中" if evidence_counts.get(row.knowledge_id, 1) >= 3 or max(evidence_boards.get(row.knowledge_id, {3})) >= 5 else "低"),
        "wrongAttempts": row.wrong_attempts, "rawWrongAttempts": row.raw_wrong_attempts,
        "firstRevealExemptions": row.first_reveal_exemptions, "hintUsed": row.hint_used,
        "clueVisible": row.clue_visible, "date": row.occurred_at.isoformat(),
    } for row in evidence])


@app.post("/api/v1/demo/reset")
def reset_demo():
    expected = os.getenv("DEMO_ADMIN_KEY")
    if not expected or request.headers.get("X-Demo-Admin-Key") != expected:
        return jsonify(error="forbidden"), 403
    for model in (MasterySnapshot, PairResult, GameSession, LearningEvent):
        db.session.query(model).delete()
    db.session.commit()
    return jsonify(status="reset", timestamp=utcnow().isoformat())


with app.app_context():
    db.create_all()
    ensure_demo_data()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
