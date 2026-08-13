from django.contrib import admin
from .models import Test, Question, Answer, UserTestResult, UserAnswerDetail


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 4


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'category', 'subcategory', 'duration_minutes', 'price', 'is_published', 'created_at')
    list_filter = ('category', 'is_published', 'created_at')
    search_fields = ('title', 'subcategory', 'description')
    ordering = ('-created_at',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'test', 'order', 'question_type', 'points', 'question_text_short')
    list_filter = ('question_type', 'test__category')
    search_fields = ('question_text', 'passage')
    inlines = [AnswerInline]

    def question_text_short(self, obj):
        return obj.question_text[:50]
    question_text_short.short_description = "Savol matni"


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('id', 'question', 'text', 'is_correct')
    list_filter = ('is_correct',)
    search_fields = ('text',)


class UserAnswerDetailInline(admin.TabularInline):
    model = UserAnswerDetail
    extra = 0
    readonly_fields = ('question', 'selected_option', 'text_answer', 'is_correct')


@admin.register(UserTestResult)
class UserTestResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'test', 'score', 'correct_count', 'incorrect_count', 'total_questions', 'time_spent_seconds', 'completed_at')
    list_filter = ('test__category', 'completed_at')
    search_fields = ('user__username', 'user__email', 'test__title')
    inlines = [UserAnswerDetailInline]
