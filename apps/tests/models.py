from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class TestCategory(models.TextChoices):
    IELTS = 'IELTS', 'IELTS'
    SAT = 'SAT', 'SAT'
    MILLIY_SERTIFIKAT = 'MILLIY_SERTIFIKAT', 'Milliy Sertifikat'
    LANGUAGES = 'LANGUAGES', 'Tillar'
    DTM = 'DTM', 'DTM Testlari'
    TOPIC_BASED = 'TOPIC_BASED', 'Mavzulashtirilgan Testlar'


class QuestionType(models.TextChoices):
    SINGLE_CHOICE = 'SINGLE_CHOICE', 'Bitta to\'g\'ri javobli'
    MULTIPLE_CHOICE = 'MULTIPLE_CHOICE', 'Bir nechta to\'g\'ri javobli'
    TEXT_ANSWER = 'TEXT_ANSWER', 'Matnli javob (Writing)'
    AUDIO_ANSWER = 'AUDIO_ANSWER', 'Ovozli javob (Speaking)'


class Test(models.Model):
    title = models.CharField(max_length=255, verbose_name="Test nomi")
    description = models.TextField(blank=True, verbose_name="Test haqida tavsif")
    category = models.CharField(
        max_length=50,
        choices=TestCategory.choices,
        default=TestCategory.IELTS,
        verbose_name="Kategoriya"
    )
    subcategory = models.CharField(
        max_length=100,
        blank=True,
        help_text="Masalan: Full Mock, Reading, Math, 9-sinf Tarix 1-mavzu...",
        verbose_name="Ichki yo'nalish / Subkategoriya"
    )
    duration_minutes = models.PositiveIntegerField(default=60, verbose_name="Vaqt (daqiqa)")
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name="Test narxi (so'm)",
        help_text="0.00 = bepul test"
    )
    is_published = models.BooleanField(default=False, verbose_name="Nashr qilinganmi?")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tests",
        verbose_name="Yaratuvchi (Content Manager / Admin)"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan vaqti")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Tahrirlangan vaqti")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Test"
        verbose_name_plural = "Testlar"

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class Question(models.Model):
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Tegishli test"
    )
    question_text = models.TextField(verbose_name="Savol matni")
    passage = models.TextField(blank=True, null=True, verbose_name="Matn (Reading uchun matn)")
    image = models.ImageField(upload_to="questions/images/", blank=True, null=True, verbose_name="Savol rasmi")
    audio = models.FileField(upload_to="questions/audio/", blank=True, null=True, verbose_name="Listening audiosi")
    question_type = models.CharField(
        max_length=30,
        choices=QuestionType.choices,
        default=QuestionType.SINGLE_CHOICE,
        verbose_name="Savol turi"
    )
    points = models.PositiveIntegerField(default=1, verbose_name="Ball")
    order = models.PositiveIntegerField(default=1, verbose_name="Tartib raqami")

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Savol"
        verbose_name_plural = "Savollar"

    def __str__(self):
        return f"{self.test.title} - {self.order}-savol: {self.question_text[:50]}"


class Answer(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name="Savol"
    )
    text = models.TextField(verbose_name="Variant matni")
    is_correct = models.BooleanField(default=False, verbose_name="To'g'ri javobmi?")

    class Meta:
        verbose_name = "Javob varianti"
        verbose_name_plural = "Javob variantlari"

    def __str__(self):
        status = "✓" if self.is_correct else "✗"
        return f"[{status}] {self.text[:50]}"


class UserTestResult(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="test_results",
        verbose_name="Foydalanuvchi"
    )
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name="user_results",
        verbose_name="Test"
    )
    score = models.FloatField(default=0.0, verbose_name="Natija balli (Band / SAT score / %)")
    correct_count = models.PositiveIntegerField(default=0, verbose_name="To'g'ri javoblar soni")
    incorrect_count = models.PositiveIntegerField(default=0, verbose_name="Noto'g'ri javoblar soni")
    total_questions = models.PositiveIntegerField(default=0, verbose_name="Jami savollar soni")
    time_spent_seconds = models.PositiveIntegerField(default=0, verbose_name="Sarflangan vaqt (soniya)")
    completed_at = models.DateTimeField(auto_now_add=True, verbose_name="Topshirilgan vaqt")

    class Meta:
        ordering = ['-completed_at']
        verbose_name = "Test Natijasi"
        verbose_name_plural = "Test Natijalari"

    def __str__(self):
        return f"{self.user} - {self.test.title}: {self.score} ball ({self.completed_at.strftime('%Y-%m-%d %H:%M')})"


class UserAnswerDetail(models.Model):
    result = models.ForeignKey(
        UserTestResult,
        on_delete=models.CASCADE,
        related_name="answers_breakdown",
        verbose_name="Natija"
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        verbose_name="Savol"
    )
    selected_option = models.ForeignKey(
        Answer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Tanlangan variant"
    )
    text_answer = models.TextField(blank=True, null=True, verbose_name="Yozma javob")
    is_correct = models.BooleanField(default=False, verbose_name="To'g'ri bajarildimi?")

    class Meta:
        verbose_name = "Savol natijasi tafsiloti"
        verbose_name_plural = "Savollar natijasi tafsilotlari"

    def __str__(self):
        status = "To'g'ri" if self.is_correct else "Noto'g'ri"
        return f"Result #{self.result.id} - Question #{self.question.id}: {status}"
