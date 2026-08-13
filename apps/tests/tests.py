from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from apps.tests.models import Test, Question, Answer, UserTestResult, TestCategory, QuestionType

User = get_user_model()


class TestsModuleTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.admin_user = User.objects.create_superuser(
            username='admin_user',
            email='admin@protesty.uz',
            password='Password123!'
        )
        self.cm_user = User.objects.create_user(
            username='content_manager',
            email='cm@protesty.uz',
            password='Password123!'
        )
        self.cm_user.role = 'CONTENT_MANAGER'
        self.cm_user.is_staff = True
        self.cm_user.save()

        self.student_user = User.objects.create_user(
            username='student_user',
            email='student@protesty.uz',
            password='Password123!'
        )

    def test_01_content_manager_can_create_publish_and_set_price(self):
        self.client.force_authenticate(user=self.cm_user)

        # Create IELTS Test with Price
        test_payload = {
            "title": "IELTS Full Mock #1",
            "description": "IELTS Full Reading and Listening test",
            "category": TestCategory.IELTS,
            "subcategory": "Full Mock",
            "duration_minutes": 120,
            "price": "49000.00",
            "is_published": False
        }
        response = self.client.post('/api/v1/tests/', test_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(response.data['price']), 49000.0)
        test_id = response.data['id']

        # Validation test: Adding Question with NO correct answer option should FAIL validation
        invalid_question_payload = {
            "test": test_id,
            "question_text": "Invalid Question?",
            "question_type": QuestionType.SINGLE_CHOICE,
            "options": [
                {"text": "A", "is_correct": False},
                {"text": "B", "is_correct": False}
            ]
        }
        invalid_q_res = self.client.post('/api/v1/questions/', invalid_question_payload, format='json')
        self.assertEqual(invalid_q_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid Question with correct answer option
        valid_question_payload = {
            "test": test_id,
            "question_text": "What is the capital of Uzbekistan?",
            "passage": "Uzbekistan is a country in Central Asia...",
            "question_type": QuestionType.SINGLE_CHOICE,
            "points": 1,
            "order": 1,
            "options": [
                {"text": "Tashkent", "is_correct": True},
                {"text": "Samarkand", "is_correct": False}
            ]
        }
        q_response = self.client.post('/api/v1/questions/', valid_question_payload, format='json')
        self.assertEqual(q_response.status_code, status.HTTP_201_CREATED)

        # Direct Publish by Content Manager
        pub_response = self.client.post(f'/api/v1/tests/{test_id}/publish/')
        self.assertEqual(pub_response.status_code, status.HTTP_200_OK)

        test_obj = Test.objects.get(id=test_id)
        self.assertTrue(test_obj.is_published)

    def test_02_student_unanswered_questions_and_time_spent_tracking(self):
        # Setup test with 2 questions
        sat_test = Test.objects.create(
            title="SAT Math Test #1",
            category=TestCategory.SAT,
            subcategory="Math",
            duration_minutes=60,
            price=0.00,
            is_published=True
        )

        q1 = Question.objects.create(
            test=sat_test,
            question_text="If 2x = 10, what is x?",
            passage="Math section 1 passage...",
            question_type=QuestionType.SINGLE_CHOICE,
            order=1
        )
        opt1_correct = Answer.objects.create(question=q1, text="5", is_correct=True)
        opt1_wrong = Answer.objects.create(question=q1, text="10", is_correct=False)

        q2 = Question.objects.create(
            test=sat_test,
            question_text="What is 3x + 1 when x = 2?",
            question_type=QuestionType.SINGLE_CHOICE,
            order=2
        )
        opt2_correct = Answer.objects.create(question=q2, text="7", is_correct=True)

        self.client.force_authenticate(user=self.student_user)

        # Student submits test answer for Q1 ONLY, leaving Q2 UNANSWERED, with 350 seconds time_spent
        submit_payload = {
            "test_id": sat_test.id,
            "time_spent_seconds": 350,
            "answers": [
                {
                    "question_id": q1.id,
                    "selected_option_id": opt1_correct.id
                }
                # q2 is intentionally left unanswered by student
            ]
        }
        submit_res = self.client.post('/api/v1/results/', submit_payload, format='json')
        self.assertEqual(submit_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(submit_res.data['total_questions'], 2)
        self.assertEqual(submit_res.data['correct_count'], 1)
        self.assertEqual(submit_res.data['incorrect_count'], 1)  # Q2 unanswered counted as incorrect
        self.assertEqual(submit_res.data['time_spent_seconds'], 350)

        # Student checks detailed review endpoint
        result_id = submit_res.data['id']
        detail_res = self.client.get(f'/api/v1/results/{result_id}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        
        breakdown = detail_res.data['answers_breakdown']
        self.assertEqual(len(breakdown), 2)  # BOTH questions present in review!

        q1_detail = next(item for item in breakdown if item['question'] == q1.id)
        self.assertTrue(q1_detail['is_correct'])
        self.assertEqual(q1_detail['passage'], "Math section 1 passage...")

        q2_detail = next(item for item in breakdown if item['question'] == q2.id)
        self.assertFalse(q2_detail['is_correct'])  # Unanswered question marked incorrect
        self.assertIsNone(q2_detail['selected_option'])
