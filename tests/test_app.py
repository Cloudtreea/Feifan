import os
import tempfile
import unittest


database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = "sqlite:///" + database_file.name.replace("\\", "/")
os.environ["DEMO_ADMIN_KEY"] = "test-reset-key"

from app import LearningEvent, PairResult, Student, app, db


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()
            from app import ensure_demo_data
            ensure_demo_data()

    def event(self):
        return {
            "eventId": "evt-demo-001", "sessionId": "session-demo-001",
            "studentId": "demo-s2101", "classId": "g2c1", "gradeId": "g2",
            "subject": "history", "type": "session_completed", "timestamp": "2026-08-18T08:00:00Z",
            "moduleId": "china-ancient", "relationType": "time-event", "boardSize": 3,
            "gameScore": 920, "independentAccuracy": 100, "assessedWrongAttempts": 0, "hintCount": 0,
            "pairResults": [{"pairId": "p1", "knowledgeId": "k1", "completed": True,
                             "wrongAttempts": 0, "rawWrongAttempts": 1,
                             "firstRevealExemptions": 1, "hintUsed": False, "clueVisible": False}],
        }

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

    def test_batch_is_idempotent_and_preserves_exemption(self):
        first = self.client.post("/api/v1/learning-events/batch", json={"events": [self.event()]})
        second = self.client.post("/api/v1/learning-events/batch", json={"events": [self.event()]})
        self.assertEqual(first.json["acceptedEventIds"], ["evt-demo-001"])
        self.assertEqual(second.json["duplicateEventIds"], ["evt-demo-001"])
        with app.app_context():
            self.assertEqual(LearningEvent.query.count(), 1)
            result = PairResult.query.one()
            self.assertEqual(result.wrong_attempts, 0)
            self.assertEqual(result.raw_wrong_attempts, 1)
            self.assertEqual(result.first_reveal_exemptions, 1)
            self.assertEqual(result.evidence_score, 100)

    def test_teacher_endpoints(self):
        self.client.post("/api/v1/learning-events/batch", json={"events": [self.event()]})
        dashboard = self.client.get("/api/v1/teacher/dashboard?grade=g2&clazz=all")
        students = self.client.get("/api/v1/teacher/students?grade=g2&clazz=all&page=1")
        detail = self.client.get("/api/v1/teacher/students/demo-s2101")
        self.assertEqual(dashboard.status_code, 200)
        self.assertGreaterEqual(dashboard.json["summary"]["games"], 1)
        self.assertGreaterEqual(students.json["total"], 1)
        self.assertEqual(detail.json["recent"][0]["firstRevealExemptions"], 1)

    def test_reset_requires_key(self):
        self.assertEqual(self.client.post("/api/v1/demo/reset").status_code, 403)
        response = self.client.post("/api/v1/demo/reset", headers={"X-Demo-Admin-Key": "test-reset-key"})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
