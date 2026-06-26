import argparse
import json
from pathlib import Path


def get_timetable(candidate):
    """
    AI1 결과 항목에서 실제 시간표 데이터를 꺼낸다.

    지원 형태:
    - {"id": "...", "특징": {...}, "과목": [...]}
    - {"id": "...", "reasons": [...], "warnings": [...], "timetable": {...}}
    """
    return candidate.get("timetable", candidate)


def get_option(user_options, korean_key, normalized_key=None, default=None):
    """
    사용자 옵션에서 한글 키와 normalized 키를 모두 지원해서 값을 꺼낸다.
    """
    if korean_key in user_options:
        return user_options[korean_key]

    if normalized_key and normalized_key in user_options:
        return user_options[normalized_key]

    return default


def get_subject_name(subject):
    """
    과목 데이터에서 과목명을 꺼낸다.

    지원 키:
    - 과목명
    - name
    """
    return subject.get("과목명", subject.get("name", ""))


def get_subjects(timetable_candidate):
    """
    시간표 데이터에서 과목 목록을 꺼낸다.

    지원 키:
    - 과목
    - courses
    """
    return timetable_candidate.get(
        "과목",
        timetable_candidate.get("courses", [])
    )


def get_features(timetable_candidate):
    """
    시간표 데이터에서 추천 점수 계산에 필요한 특징 정보를 꺼낸다.

    지원 구조:
    - {"특징": {"총학점": ..., "공강요일": ..., "등교일수": ...}}
    - {"summary": {"total_credits": ..., "free_days": ..., "commute_days": ...}}
    """
    if "특징" in timetable_candidate:
        return timetable_candidate.get("특징", {})

    summary = timetable_candidate.get("summary", {})
    return {
        "총학점": summary.get("total_credits"),
        "공강요일": summary.get("free_days", []),
        "등교일수": summary.get("commute_days")
    }


def score(timetable_candidate, user_options):
    """
    하나의 시간표 후보를 사용자 옵션과 비교하여 추천 점수와 사유를 계산한다.

    AI2 추천 엔진의 역할:
    - AI1이 필터링해서 넘긴 30개의 시간표 후보를 평가한다.
    - 각 후보에 점수를 부여한다.
    - 점수와 함께 추천/감점 사유를 반환한다.
    """
    base_score = 50
    reasons = []

    subjects = get_subjects(timetable_candidate)
    features = get_features(timetable_candidate)

    # 1. 사회봉사 과목 포함 여부 반영
    include_volunteer = get_option(
        user_options,
        "사회봉사포함",
        "include_social_service",
        True
    )
    has_volunteer = any(
        "사회봉사" in get_subject_name(subject)
        for subject in subjects
    )

    if not include_volunteer and has_volunteer:
        base_score -= 30
        reasons.append("사회봉사 과목 미선호 반영")

    # 2. 졸업지도 과목 중복 포함 여부 반영
    graduation_courses = [
        get_subject_name(subject)
        for subject in subjects
        if "졸업지도" in get_subject_name(subject)
    ]

    if len(graduation_courses) >= 2:
        base_score -= 40
        reasons.append("졸업지도 과목 중복 분반 포함으로 감점")

    # 3. 목표 학점과 실제 학점 차이 반영
    target_credits = get_option(
        user_options,
        "목표학점",
        "target_credits"
    )
    total_credits = features.get("총학점")

    if target_credits is not None and total_credits is not None:
        credit_diff = abs(total_credits - target_credits)

        if credit_diff == 0:
            base_score += 25
            reasons.append("목표 학점과 정확히 일치")
        elif credit_diff <= 2:
            base_score += 15
            reasons.append(f"목표 학점과 {credit_diff}학점 차이")
        elif credit_diff <= 4:
            base_score += 5
            reasons.append(f"목표 학점과 {credit_diff}학점 차이")
        else:
            penalty = min(30, credit_diff * 3)
            base_score -= penalty
            reasons.append(f"목표 학점과 {credit_diff}학점 차이로 감점")

    # 4. 선호 공강 요일 반영
    preferred_free_days = get_option(
        user_options,
        "선호공강요일",
        "preferred_free_days",
        []
    )
    actual_free_days = features.get("공강요일", [])

    if preferred_free_days:
        match_count = sum(
            1 for day in preferred_free_days
            if day in actual_free_days
        )

        if match_count > 0:
            base_score += match_count * 10
            reasons.append(
                f"선호 공강 요일 {match_count}개 일치"
            )

        missing_count = len(preferred_free_days) - match_count
        if missing_count > 0:
            base_score -= missing_count * 10
            reasons.append(
                f"선호 공강 요일 {missing_count}개 불일치"
            )
    elif len(actual_free_days) >= 3:
        base_score += len(actual_free_days) * 5
        reasons.append(f"주 {len(actual_free_days)}일 공강 확보")

    # 5. 등교일수 기반 통학 효율성 반영
    days_at_school = features.get("등교일수", 5)

    if days_at_school is not None:
        if days_at_school <= 2:
            base_score += 15
            reasons.append(f"주 {days_at_school}일 등교로 통학 효율 높음")
        elif days_at_school == 3:
            base_score += 10
            reasons.append("주 3일 등교로 무난한 시간표")
        elif days_at_school >= 5:
            base_score -= 10
            reasons.append("주 5일 이상 등교로 감점")

    if not reasons:
        reasons.append("기본 조건을 만족하는 안정적인 시간표")

    final_score = max(0, min(100, base_score))
    return final_score, ", ".join(reasons)


def rank(all_candidates, user_options):
    """
    AI1이 넘겨준 시간표 후보들을 전체 채점한 뒤 점수 높은 순으로 정렬한다.
    """
    ranked_list = []

    for candidate in all_candidates:
        timetable = get_timetable(candidate)
        current_score, reason_text = score(timetable, user_options)
        ranked_list.append({
            "id": timetable.get("id", candidate.get("id")),
            "점수": current_score,
            "이유": reason_text
        })

    ranked_list.sort(key=lambda item: item["점수"], reverse=True)
    return ranked_list


def top3(ranked_list):
    """
    점수 순으로 정렬된 시간표 목록에서 1등 시간표를 추천 결과 JSON으로 변환한다.
    """
    final_recommendations = []

    for index, item in enumerate(ranked_list[:3]):
        final_recommendations.append({
            "id": item["id"],
            "순위": index + 1,
            "점수": item["점수"],
            "이유": item["이유"]
        })

    return json.dumps(final_recommendations, ensure_ascii=False, indent=2)


def recommend(all_candidates, user_options):
    """
    AI2 추천 엔진의 전체 실행 함수.

    입력:
    - all_candidates: AI1이 필터링해서 넘긴 시간표 후보 리스트
    - user_options: 사용자가 선택한 옵션

    출력:
    - 상위 3개 추천 시간표 JSON 문자열
    """
    ranked_list = rank(all_candidates, user_options)
    return top3(ranked_list)


def recommend_from_ai1_output(ai1_output):
    """
    AI1의 단일 output 데이터를 받아 Top3 추천 JSON 문자열을 반환한다.

    입력 예시:
    {
      "source": "grade3",
      "options": {...},
      "results": [
        {"id": "tt_1", "timetable": {...}},
        ...
      ]
    }
    """
    user_options = ai1_output.get("options", {})
    candidates = ai1_output.get("results", [])
    return recommend(candidates, user_options)


def recommend_from_ai1_payload(payload):
    """
    AI1이 전달한 전체 JSON payload를 받아 source별 추천 결과를 반환한다.

    현재 예시 데이터처럼 최상위에 outputs가 있는 경우 사용한다.
    """
    recommendation_outputs = []

    for output in payload.get("outputs", []):
        user_options = output.get("options", {})
        candidates = output.get("results", [])
        ranked_list = rank(candidates, user_options)

        recommendation_outputs.append({
            "source": output.get("source"),
            "추천결과": json.loads(top3(ranked_list))
        })

    return json.dumps(
        {
            "description": "AI2 recommendation results",
            "outputs": recommendation_outputs
        },
        ensure_ascii=False,
        indent=2
    )


def recommend_from_payload(payload):
    """
    AI1 결과 JSON 형태에 맞춰 추천 결과를 만든다.

    지원 형태:
    - {"outputs": [...]}: 여러 학년/조건 결과가 들어있는 전체 payload
    - {"options": {...}, "results": [...]}: 단일 필터링 결과
    """
    if "outputs" in payload:
        return recommend_from_ai1_payload(payload)

    if "results" in payload:
        recommendation_result = json.loads(recommend_from_ai1_output(payload))
        return json.dumps(
            {
                "description": "AI2 recommendation results",
                "outputs": [
                    {
                        "source": payload.get("source"),
                        "추천결과": recommendation_result
                    }
                ]
            },
            ensure_ascii=False,
            indent=2
        )

    raise ValueError("입력 JSON에는 outputs 또는 results 배열이 필요합니다.")


def main():
    parser = argparse.ArgumentParser(
        description="AI1이 필터링한 시간표 결과에서 Top3 추천 결과를 생성합니다."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="AI1이 만든 filtered_timetables.json 파일 경로"
    )
    parser.add_argument(
        "--output",
        default="recommendation_results.json",
        help="AI2 추천 결과를 저장할 JSON 파일 경로"
    )

    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as input_file:
        payload = json.load(input_file)

    result_json = recommend_from_payload(payload)

    with open(args.output, "w", encoding="utf-8") as output_file:
        output_file.write(result_json)

    print(result_json)



if __name__ == "__main__":
    current_dir = Path(__file__).parent
    input_path = current_dir / "filtered_timetables.json"
    if not input_path.exists():
        input_path = current_dir / "filtered_combined_timetables.json"

    output_path = current_dir / "recommendation_results.json"

    with open(input_path, "r", encoding="utf-8") as input_file:
        payload = json.load(input_file)

    result_json = recommend_from_payload(payload)

    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write(result_json)

    print(result_json)
