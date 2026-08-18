from .models import TestCategory


def calculate_ielts_band(correct_count: int, total_questions: int) -> float:
    """
    Converts correct answer count out of total questions into IELTS Band Score (0 - 9.0).
    """
    if total_questions <= 0:
        return 0.0
    
    # Scale correct_count to standard 40 questions scale if needed
    raw_40 = (correct_count / total_questions) * 40.0

    if raw_40 >= 39:
        return 9.0
    elif raw_40 >= 37:
        return 8.5
    elif raw_40 >= 35:
        return 8.0
    elif raw_40 >= 33:
        return 7.5
    elif raw_40 >= 30:
        return 7.0
    elif raw_40 >= 27:
        return 6.5
    elif raw_40 >= 23:
        return 6.0
    elif raw_40 >= 19:
        return 5.5
    elif raw_40 >= 15:
        return 5.0
    elif raw_40 >= 13:
        return 4.5
    elif raw_40 >= 10:
        return 4.0
    elif raw_40 >= 6:
        return 3.5
    elif raw_40 >= 4:
        return 3.0
    else:
        return 2.0 if raw_40 > 0 else 0.0


def calculate_sat_score(correct_count: int, total_questions: int) -> float:
    """
    Converts correct answer ratio into SAT scale (400 - 1600).
    """
    if total_questions <= 0:
        return 400.0
    
    ratio = correct_count / total_questions
    sat_score = 400 + (ratio * 1200)
    return round(sat_score, 0)


def calculate_test_score(test_category: str, correct_count: int, total_questions: int) -> float:
    """
    Calculates appropriate score based on the category of test.
    """
    if test_category == TestCategory.IELTS:
        return calculate_ielts_band(correct_count, total_questions)
    elif test_category == TestCategory.SAT:
        return calculate_sat_score(correct_count, total_questions)
    else:
        if total_questions <= 0:
            return 0.0
        return round((correct_count / total_questions) * 100.0, 1)
