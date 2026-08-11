from rest_framework import serializers
from .models import Test, Question, Answer, UserTestResult, UserAnswerDetail
from .services import calculate_test_score


class AnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['id', 'text', 'is_correct']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Hide is_correct from students taking tests unless specified in context
        request = self.context.get('request')
        hide_correct = self.context.get('hide_correct', False)
        if hide_correct:
            data.pop('is_correct', None)
        return data


class QuestionSerializer(serializers.ModelSerializer):
    options = AnswerSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = [
            'id', 'test', 'question_text', 'passage',
            'image', 'audio', 'question_type', 'points',
            'order', 'options'
        ]

    def create(self, validated_data):
        options_data = validated_data.pop('options', [])
        question = Question.objects.create(**validated_data)
        for option_data in options_data:
            Answer.objects.create(question=question, **option_data)
        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop('options', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if options_data is not None:
            instance.options.all().delete()
            for option_data in options_data:
                Answer.objects.create(question=instance, **option_data)

        return instance


class TestSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    questions_count = serializers.IntegerField(source='questions.count', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Test
        fields = [
            'id', 'title', 'description', 'category', 'category_display',
            'subcategory', 'duration_minutes', 'is_published',
            'created_by', 'created_at', 'updated_at', 'questions_count',
            'questions'
        ]
        read_only_fields = ['created_by', 'created_at', 'updated_at']


class SubmitAnswerItemSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    selected_option_id = serializers.IntegerField(required=False, allow_null=True)
    text_answer = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class SubmitTestSerializer(serializers.Serializer):
    test_id = serializers.IntegerField()
    answers = SubmitAnswerItemSerializer(many=True)

    def validate_test_id(self, value):
        try:
            test = Test.objects.get(id=value)
            return test.id
        except Test.DoesNotExist:
            raise serializers.ValidationError("Test topilmadi.")

    def create(self, validated_data):
        user = self.context['request'].user
        test_id = validated_data['test_id']
        answers_data = validated_data['answers']

        test = Test.objects.get(id=test_id)
        questions = test.questions.all().prefetch_related('options')
        question_map = {q.id: q for q in questions}

        total_questions = len(question_map)
        correct_count = 0
        incorrect_count = 0

        # Create Result record
        result = UserTestResult.objects.create(
            user=user,
            test=test,
            total_questions=total_questions
        )

        for ans in answers_data:
            q_id = ans.get('question_id')
            selected_opt_id = ans.get('selected_option_id')
            text_ans = ans.get('text_answer')

            question = question_map.get(q_id)
            if not question:
                continue

            selected_option = None
            is_correct = False

            if selected_opt_id:
                try:
                    selected_option = Answer.objects.get(id=selected_opt_id, question=question)
                    if selected_option.is_correct:
                        is_correct = True
                except Answer.DoesNotExist:
                    pass

            if is_correct:
                correct_count += 1
            else:
                incorrect_count += 1

            UserAnswerDetail.objects.create(
                result=result,
                question=question,
                selected_option=selected_option,
                text_answer=text_ans,
                is_correct=is_correct
            )

        # Calculate score using service
        score = calculate_test_score(test.category, correct_count, total_questions)

        result.score = score
        result.correct_count = correct_count
        result.incorrect_count = incorrect_count
        result.save()

        return result


class UserAnswerDetailSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    selected_option_text = serializers.CharField(source='selected_option.text', read_only=True, default=None)
    correct_option_text = serializers.SerializerMethodField()

    class Meta:
        model = UserAnswerDetail
        fields = [
            'id', 'question', 'question_text',
            'selected_option', 'selected_option_text',
            'text_answer', 'is_correct', 'correct_option_text'
        ]

    def get_correct_option_text(self, obj):
        correct_opt = obj.question.options.filter(is_correct=True).first()
        return correct_opt.text if correct_opt else None


class UserTestResultSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='test.title', read_only=True)
    category = serializers.CharField(source='test.category', read_only=True)
    subcategory = serializers.CharField(source='test.subcategory', read_only=True)
    answers_breakdown = UserAnswerDetailSerializer(many=True, read_only=True)

    class Meta:
        model = UserTestResult
        fields = [
            'id', 'user', 'test', 'test_title', 'category', 'subcategory',
            'score', 'correct_count', 'incorrect_count',
            'total_questions', 'completed_at', 'answers_breakdown'
        ]
