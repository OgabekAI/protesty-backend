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

    def test_01_content_manager_can_create_and_publish_test(self):
        self.client.force_authenticate(user=self.cm_user)

        # Create IELTS Test
        test_payload = {
            "title": "IELTS Full Mock #1",
            "description": "IELTS Full Reading and Listening test",
            "category": TestCategory.IELTS,
            "subcategory": "Full Mock",
            "duration_minutes": 120,
            "is_published": False
        }
        response = self.client.post('/api/v1/tests/', test_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        test_id = response.data['id']

        # Add Question to Test
        question_payload = {
            "test": test_id,
            "question_text": "What is the capital of Uzbekistan?",
            "question_type": QuestionType.SINGLE_CHOICE,
            "points": 1,
            "order": 1,
            "options": [
                {"text": "Tashkent", "is_correct": True},
                {"text": "Samarkand", "is_correct": False},
                {"text": "Bukhara", "is_correct": False},
                {"text": "Khiva", "is_correct": False}
            ]
        }
        q_response = self.client.post('/api/v1/questions/', question_payload, format='json')
        self.assertEqual(q_response.status_code, status.HTTP_201_CREATED)

        # Direct Publish by Content Manager
        pub_response = self.client.post(f'/api/v1/tests/{test_id}/publish/')
        self.assertEqual(pub_response.status_code, status.HTTP_200_OK)

        test_obj = Test.objects.get(id=test_id)
        self.assertTrue(test_obj.is_published)

    def test_02_student_can_list_published_tests_and_submit_attempt(self):
        # Setup published SAT test
        sat_test = Test.objects.create(
            title="SAT Math Test #1",
            category=TestCategory.SAT,
            subcategory="Math",
            duration_minutes=60,
            is_published=True
        )

        q1 = Question.objects.create(
            test=sat_test,
            question_text="If 2x = 10, what is x?",
            question_type=QuestionType.SINGLE_CHOICE,
            order=1
        )
        opt1_correct = Answer.objects.create(question=q1, text="5", is_correct=True)
        opt1_wrong = Answer.objects.create(question=q1, text="10", is_correct=False)

        # Student logs in
        self.client.force_authenticate(user=self.student_user)

        # 1. Student lists published tests
        list_res = self.client.get('/api/v1/tests/')
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)

        # 2. Student submits test answer
        submit_payload = {
            "test_id": sat_test.id,
            "answers": [
                {
                    "question_id": q1.id,
                    "selected_option_id": opt1_correct.id
                }
            ]
        }
        submit_res = self.client.post('/api/v1/results/', submit_payload, format='json')
        self.assertEqual(submit_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(submit_res.data['correct_count'], 1)
        self.assertGreaterEqual(submit_res.data['score'], 400.0)

        # 3. Student checks results history
        results_history = self.client.get('/api/v1/results/')
        self.assertEqual(results_history.status_code, status.HTTP_200_OK)
        self.assertEqual(len(results_history.data), 1)

        # 4. Student checks detailed question breakdown review
        result_id = submit_res.data['id']
        detail_res = self.client.get(f'/api/v1/results/{result_id}/')
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(detail_res.data['answers_breakdown']), 1)
        self.assertTrue(detail_res.data['answers_breakdown'][0]['is_correct'])
