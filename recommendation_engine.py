from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))
load_dotenv()


def _get_env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DAYS = ("월", "화", "수", "목", "금", "토", "일")
WEEKDAYS = set(DAYS[:5])
FIRST_PERIOD_START_MINUTES = 9 * 60
FIRST_PERIOD_END_MINUTES = 10 * 60
SPACE_GAP_MINUTES = 2 * 60
DEFAULT_LLM_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_LLM_CANDIDATE_LIMIT = _get_env_int("LLM_CANDIDATE_LIMIT", 0)


TIMETABLE_ALIASES = {
    "timetables": ("candidates", "timetables", "timeTables"),
    "summary": ("feature", "features", "summary", "meta"),
    "courses": ("courses", "subjects", "classes"),
    "id": ("timetableId", "timeTableId", "id", "timetable_id"),
    "free_days": ("freeDays", "free_days"),
    "commute_days": ("attendanceDays", "commuteDays", "commute_days"),
    "course_name": ("courseName", "name", "course_name", "subjectName"),
    "course_credits": ("credits", "credit"),
    "course_time": ("schedules", "schedule", "time", "class_time"),
    "course_category": ("category", "courseType", "type", "classification"),
}


def _get_any(data: dict[str, Any], aliases: tuple[str, ...], default: Any = None) -> Any:
    for key in aliases:
        if key in data:
            return data[key]
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_int_any(data: dict[str, Any], aliases: tuple[str, ...]) -> int | None:
    return _as_int(_get_any(data, aliases))


def _time_to_minutes(value: Any) -> int | None:
    if value in (None, ""):
        return None
    match = re.search(r"(\d{1,2}):(\d{2})", str(value))
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _extract_start_end(time_value: Any) -> tuple[int | None, int | None]:
    times = re.findall(r"(\d{1,2}:\d{2})", str(time_value or ""))
    if not times:
        return None, None
    start = _time_to_minutes(times[0])
    end = _time_to_minutes(times[-1]) if len(times) >= 2 else None
    return start, end


def _extract_days_from_text(value: Any) -> set[str]:
    text = str(value or "")
    return {day for day in DAYS if day in text}


def _looks_like_time_text(value: Any) -> bool:
    return isinstance(value, str) and re.search(r"\d{1,2}:\d{2}", value) is not None


def _find_first_dict_list_value(data: dict[str, Any]) -> list[dict[str, Any]]:
    for value in data.values():
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    return []


def extract_timetables(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise TypeError("payload must be a list or dict")

    timetables = _get_any(payload, TIMETABLE_ALIASES["timetables"])
    if isinstance(timetables, list):
        return [item for item in timetables if isinstance(item, dict)]

    fallback = _find_first_dict_list_value(payload)
    if fallback:
        return fallback

    raise ValueError("candidates list was not found in payload")


def get_timetable_id(timetable: dict[str, Any]) -> Any:
    timetable_id = _get_any(timetable, TIMETABLE_ALIASES["id"])
    if timetable_id is None:
        raise ValueError("timetableId is missing")
    return timetable_id


def format_timetable_id(timetable_id: Any) -> Any:
    if isinstance(timetable_id, int):
        return timetable_id

    text = str(timetable_id)
    if text.isdigit():
        return int(text)

    match = re.fullmatch(r"tt_(\d+)", text)
    if match:
        return int(match.group(1))

    return timetable_id


def _timetable_id_sort_value(timetable_id: Any) -> int:
    formatted = format_timetable_id(timetable_id)
    return formatted if isinstance(formatted, int) else 0


def get_summary(timetable: dict[str, Any]) -> dict[str, Any]:
    summary = _get_any(timetable, TIMETABLE_ALIASES["summary"])
    return summary if isinstance(summary, dict) else {}


def get_courses(timetable: dict[str, Any]) -> list[dict[str, Any]]:
    courses = _get_any(timetable, TIMETABLE_ALIASES["courses"])
    if isinstance(courses, list):
        return [course for course in courses if isinstance(course, dict)]
    return []


def get_course_name(course: dict[str, Any]) -> str:
    return str(_get_any(course, TIMETABLE_ALIASES["course_name"], ""))


def iter_course_time_blocks(course: dict[str, Any]) -> list[dict[str, Any]]:
    times = course.get("times")
    if isinstance(times, list):
        return [time_info for time_info in times if isinstance(time_info, dict)]
    return []


def iter_course_time_texts(course: dict[str, Any]) -> list[str]:
    values: list[str] = []
    time_value = _get_any(course, TIMETABLE_ALIASES["course_time"])

    for item in _as_list(time_value):
        if item is not None:
            values.append(str(item))

    for value in course.values():
        if _looks_like_time_text(value):
            values.append(str(value))
        elif isinstance(value, list):
            values.extend(str(item) for item in value if _looks_like_time_text(item))

    return list(dict.fromkeys(values))


def iter_time_ranges(timetable: dict[str, Any]) -> list[tuple[str, int, int]]:
    ranges: list[tuple[str, int, int]] = []

    for course in get_courses(timetable):
        for time_info in iter_course_time_blocks(course):
            day = time_info.get("dayOfWeek") or time_info.get("day")
            start = _time_to_minutes(time_info.get("startTime") or time_info.get("start"))
            end = _time_to_minutes(time_info.get("endTime") or time_info.get("end"))
            if day and start is not None and end is not None:
                ranges.append((str(day), start, end))

        for time_text in iter_course_time_texts(course):
            start, end = _extract_start_end(time_text)
            if start is None or end is None:
                continue
            for day in _extract_days_from_text(time_text):
                ranges.append((day, start, end))

    return ranges


def get_class_days(timetable: dict[str, Any]) -> set[str]:
    return {day for day, _, _ in iter_time_ranges(timetable)}


def get_free_days(timetable: dict[str, Any]) -> set[str]:
    summary = get_summary(timetable)
    free_days = _get_any(summary, TIMETABLE_ALIASES["free_days"])
    if free_days is not None:
        return {str(day) for day in _as_list(free_days)}
    return WEEKDAYS - get_class_days(timetable)


def get_commute_days(timetable: dict[str, Any]) -> int:
    summary = get_summary(timetable)
    commute_days = _get_int_any(summary, TIMETABLE_ALIASES["commute_days"])
    if commute_days is not None:
        return commute_days
    return len(get_class_days(timetable))


def has_lunch_break(timetable: dict[str, Any]) -> bool:
    summary = get_summary(timetable)
    lunch_break_count = _get_int_any(summary, ("lunchBreakCount", "lunch_break_count"))
    attendance_days = _get_int_any(summary, ("attendanceDays", "attendance_days"))
    if lunch_break_count is not None:
        if attendance_days is not None and attendance_days > 0:
            return lunch_break_count >= attendance_days
        return lunch_break_count > 0

    lunch_start = 11 * 60
    lunch_end = 13 * 60
    ranges = iter_time_ranges(timetable)
    class_days = {day for day, _, _ in ranges}
    if not class_days:
        return False

    for day in class_days:
        day_ranges = [(start, end) for range_day, start, end in ranges if range_day == day]
        if any(start < lunch_end and end > lunch_start for start, end in day_ranges):
            return False
    return True


def get_max_same_day_gap_minutes(timetable: dict[str, Any]) -> int:
    summary = get_summary(timetable)
    longest_break = _get_int_any(summary, ("longestBreakMinutes", "longest_break_minutes"))
    if longest_break is not None:
        return longest_break

    max_gap = 0
    ranges_by_day: dict[str, list[tuple[int, int]]] = {}
    for day, start, end in iter_time_ranges(timetable):
        ranges_by_day.setdefault(day, []).append((start, end))

    for ranges in ranges_by_day.values():
        ordered = sorted(ranges)
        for index in range(1, len(ordered)):
            max_gap = max(max_gap, ordered[index][0] - ordered[index - 1][1])
    return max_gap


def has_space_gap(timetable: dict[str, Any]) -> bool:
    summary = get_summary(timetable)
    long_break_count = _get_int_any(summary, ("longBreakCount", "long_break_count"))
    if long_break_count is not None:
        return long_break_count > 0
    return get_max_same_day_gap_minutes(timetable) >= SPACE_GAP_MINUTES


def count_first_periods(timetable: dict[str, Any]) -> int:
    summary = get_summary(timetable)
    first_period_count = _get_int_any(summary, ("firstPeriodCount", "first_period_count"))
    if first_period_count is not None:
        return first_period_count

    return sum(
        1
        for _, start, _ in iter_time_ranges(timetable)
        if FIRST_PERIOD_START_MINUTES <= start < FIRST_PERIOD_END_MINUTES
    )


def contains_first_period(timetable: dict[str, Any]) -> bool:
    return count_first_periods(timetable) > 0


def is_required_major_course(course: dict[str, Any]) -> bool:
    category_values = [
        str(course.get("category", "")),
        str(course.get("courseType", "")),
        str(course.get("type", "")),
        str(course.get("classification", "")),
    ]
    return any("전공필수" in value or value == "전필" for value in category_values)


def count_required_major_courses(timetable: dict[str, Any]) -> int:
    return sum(1 for course in get_courses(timetable) if is_required_major_course(course))


def count_graduation_guidance_courses(timetable: dict[str, Any]) -> int:
    return sum(1 for course in get_courses(timetable) if "졸업지도" in get_course_name(course))


def score(timetable: dict[str, Any]) -> tuple[float, str]:
    summary = get_summary(timetable)
    base_score = 70
    reasons: list[str] = []

    graduation_guidance_count = count_graduation_guidance_courses(timetable)
    if graduation_guidance_count >= 2:
        base_score -= 40
        reasons.append("졸업지도 과목 중복")

    required_major_count = count_required_major_courses(timetable)
    if required_major_count:
        base_score += min(6, required_major_count * 3)
        reasons.append(f"전공필수 {required_major_count}개")

    commute_days = get_commute_days(timetable)
    if commute_days <= 2:
        base_score += 12
        reasons.append(f"등교 {commute_days}일")
    elif commute_days == 3:
        base_score += 7
        reasons.append("등교 3일")
    elif commute_days >= 5:
        base_score -= 8
        reasons.append("등교일 많음")

    lunch_break_count = _get_int_any(summary, ("lunchBreakCount", "lunch_break_count"))
    if has_lunch_break(timetable):
        base_score += 10
        reasons.append("점심시간 보장")
    elif lunch_break_count is not None and lunch_break_count > 0:
        base_score += min(8, lunch_break_count * 2)
        reasons.append(f"점심 가능 {lunch_break_count}일")
    else:
        base_score -= 6
        reasons.append("점심시간 부족")

    max_gap = get_max_same_day_gap_minutes(timetable)
    long_break_count = _get_int_any(summary, ("longBreakCount", "long_break_count"))
    if long_break_count is not None and long_break_count > 0:
        base_score -= min(24, long_break_count * 8)
        reasons.append(f"긴 공강 {long_break_count}일")
    elif max_gap >= SPACE_GAP_MINUTES:
        base_score -= 15
        reasons.append("우주공강 있음")
    elif max_gap > 0:
        base_score += 6
        reasons.append("공강 짧음")

    first_period_count = count_first_periods(timetable)
    if first_period_count == 0:
        base_score += 12
        reasons.append("1교시 없음")
    else:
        base_score -= min(24, first_period_count * 6)
        reasons.append(f"1교시 {first_period_count}개")

    early_finish_day_count = _get_int_any(summary, ("earlyFinishDayCount", "early_finish_day_count"))
    if early_finish_day_count:
        base_score += min(8, early_finish_day_count * 2)
        reasons.append(f"15시 이전 종료 {early_finish_day_count}일")

    earliest_start = _time_to_minutes(_get_any(summary, ("earliestStartTime", "earliest_start_time")))
    if earliest_start is not None:
        if earliest_start >= 12 * 60:
            base_score += 8
            reasons.append("오후 수업 위주")
        elif earliest_start >= 10 * 60:
            base_score += 4
            reasons.append("이른 오전 적음")

    latest_end = _time_to_minutes(_get_any(summary, ("latestEndTime", "latest_end_time")))
    if latest_end is not None:
        if latest_end <= 15 * 60:
            base_score += 8
            reasons.append("일찍 귀가")
        elif latest_end > 18 * 60:
            base_score -= 6
            reasons.append("늦은 종료")

    final_score = float(round(max(0, min(100, base_score)), 1))
    return final_score, ", ".join(reasons)


def _unique_tags(tags: list[str]) -> list[str]:
    unique = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            unique.append(tag)
            seen.add(tag)
    return unique


def _sort_days(days: set[str] | list[str]) -> list[str]:
    return sorted([day for day in days if day in DAYS], key=DAYS.index)


def build_recommendation_tags(timetable: dict[str, Any]) -> list[str]:
    tags: list[str] = []

    for day in _sort_days(get_free_days(timetable).intersection(WEEKDAYS))[:3]:
        tags.append(f"#{day}공강")

    if not contains_first_period(timetable):
        tags.append("#1교시없음")
    if has_lunch_break(timetable):
        tags.append("#점심시간보장")
    if not has_space_gap(timetable):
        tags.append("#우주공강없음")

    return _unique_tags(tags)


def rank(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked_list = []
    for timetable in candidates:
        current_score, reason_text = score(timetable)
        ranked_list.append(
            {
                "id": get_timetable_id(timetable),
                "score": current_score,
                "reason": reason_text,
                "tags": build_recommendation_tags(timetable),
                "requiredMajorCount": count_required_major_courses(timetable),
            }
        )

    ranked_list.sort(
        key=lambda item: (
            item["score"],
            item["requiredMajorCount"],
            -_timetable_id_sort_value(item["id"]),
        ),
        reverse=True,
    )
    return ranked_list


def build_tie_breakers(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tie_breakers = rank(candidates)
    for index, item in enumerate(tie_breakers):
        item["tieBreakerRank"] = index + 1
    return tie_breakers


def top_n(ranked_list: list[dict[str, Any]], count: int = 3) -> list[dict[str, Any]]:
    recommendations = []
    for index, item in enumerate(ranked_list[:count]):
        recommendations.append(
            {
                "timetableId": format_timetable_id(item["id"]),
                "rank": index + 1,
                "score": item["score"],
                "tags": item.get("tags", []),
            }
        )
    return recommendations


def _find_timetable_by_id(candidates: list[dict[str, Any]], timetable_id: Any) -> dict[str, Any] | None:
    formatted_target = format_timetable_id(timetable_id)
    for candidate in candidates:
        if format_timetable_id(get_timetable_id(candidate)) == formatted_target:
            return candidate
    return None


def _summarize_courses(timetable: dict[str, Any]) -> list[dict[str, Any]]:
    courses = []
    for course in get_courses(timetable)[:8]:
        courses.append(
            {
                "name": get_course_name(course),
                "category": _get_any(course, TIMETABLE_ALIASES["course_category"], ""),
                "credits": _get_any(course, TIMETABLE_ALIASES["course_credits"], ""),
                "times": iter_course_time_texts(course) or iter_course_time_blocks(course),
            }
        )
    return courses


def _summarize_timetable_for_llm(timetable: dict[str, Any], tie_breaker_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "timetableId": format_timetable_id(get_timetable_id(timetable)),
        "tags": build_recommendation_tags(timetable),
        "freeDays": _sort_days(get_free_days(timetable).intersection(WEEKDAYS)),
        "commuteDays": get_commute_days(timetable),
        "firstPeriodCount": count_first_periods(timetable),
        "hasLunchBreak": has_lunch_break(timetable),
        "hasSpaceGap": has_space_gap(timetable),
        "maxSameDayGapMinutes": get_max_same_day_gap_minutes(timetable),
        "requiredMajorCount": count_required_major_courses(timetable),
        "graduationGuidanceCount": count_graduation_guidance_courses(timetable),
        "tieBreakerRank": tie_breaker_item["tieBreakerRank"],
        "tieBreakerReason": tie_breaker_item["reason"],
        "courses": _summarize_courses(timetable),
    }


def _summarize_user_preferences(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    for key in ("preferences", "preference", "options", "userOptions", "condition", "conditions"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    return {}


def _build_llm_prompt(
    payload: Any,
    candidates: list[dict[str, Any]],
    tie_breakers: list[dict[str, Any]],
    top_n_count: int,
    candidate_limit: int,
) -> str:
    tie_breaker_by_id = {format_timetable_id(item["id"]): item for item in tie_breakers}
    summarized_candidates = []

    llm_candidates = candidates if candidate_limit <= 0 else candidates[:candidate_limit]

    for timetable in llm_candidates:
        timetable_id = format_timetable_id(get_timetable_id(timetable))
        tie_breaker_item = tie_breaker_by_id[timetable_id]
        summarized_candidates.append(_summarize_timetable_for_llm(timetable, tie_breaker_item))

    body = {
        "task": f"시간표 후보를 직접 평가해 0~100점 점수를 매기고, 가장 적합한 Top {top_n_count}개를 고르세요.",
        "selectionRules": [
            "반드시 candidates 안에 있는 timetableId만 선택하세요.",
            "rank는 1부터 시작하고 중복 없이 반환하세요.",
            "score는 LLM이 직접 산정한 0~100 사이 숫자로 반환하세요.",
            "사용자 조건이 있으면 사용자 조건을 최우선으로 반영하세요.",
            "시간표 품질은 졸업지도 중복, 전공필수 포함, 등교일 수, 점심시간, 긴 공강, 1교시, 빠른 종료를 종합해서 판단하세요.",
            "응답에는 timetableId, rank, score, tags만 포함하세요.",
        ],
        "tieBreakerRules": [
            "LLM이 두 후보에 같은 score를 부여할 정도로 우열이 비슷하면 tieBreakerRank가 더 작은 후보를 우선하세요.",
            "tieBreakerRank는 이전에 합의한 규칙을 반영합니다: 졸업지도 중복 감점, 전공필수 우대, 등교일 적음 우대, 점심시간 보장 우대, 우주공강 감점, 1교시 감점, 빠른 종료 우대.",
            "점수가 다르면 tieBreakerRank를 사용하지 말고 LLM이 산정한 score를 우선하세요.",
        ],
        "userPreferences": _summarize_user_preferences(payload),
        "candidates": summarized_candidates,
    }
    return json.dumps(body, ensure_ascii=False)


def _parse_llm_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _get_google_api_key() -> str | None:
    return os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")


def _normalize_llm_recommendations(
    llm_result: dict[str, Any],
    tie_breakers: list[dict[str, Any]],
    top_n_count: int,
) -> list[dict[str, Any]]:
    tie_breaker_by_id = {format_timetable_id(item["id"]): item for item in tie_breakers}
    normalized = []
    seen = set()

    for item in llm_result.get("recommendations", []):
        timetable_id = format_timetable_id(item.get("timetableId"))
        if timetable_id in seen or timetable_id not in tie_breaker_by_id:
            continue

        fallback = tie_breaker_by_id[timetable_id]
        normalized.append(
            {
                "timetableId": timetable_id,
                "rank": int(item.get("rank", len(normalized) + 1)),
                "score": float(item.get("score", fallback["score"])),
                "tags": item.get("tags") or fallback.get("tags", []),
            }
        )
        seen.add(timetable_id)

    normalized.sort(
        key=lambda item: (
            item["score"],
            -tie_breaker_by_id[item["timetableId"]]["tieBreakerRank"],
        ),
        reverse=True,
    )

    for index, item in enumerate(normalized[:top_n_count]):
        item["rank"] = index + 1

    return normalized[:top_n_count]


def recommend_with_llm(
    payload: Any,
    candidates: list[dict[str, Any]],
    tie_breakers: list[dict[str, Any]],
    top_n_count: int = 3,
    model: str = DEFAULT_LLM_MODEL,
    candidate_limit: int = DEFAULT_LLM_CANDIDATE_LIMIT,
) -> list[dict[str, Any]]:
    from google import genai
    from google.genai import types
    from pydantic import BaseModel

    api_key = _get_google_api_key()
    if not api_key:
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY is required for Gemini ranking")

    class LlmRecommendation(BaseModel):
        timetableId: str
        rank: int
        score: float
        tags: list[str]

    class LlmRecommendationResponse(BaseModel):
        recommendations: list[LlmRecommendation]

    client = genai.Client(api_key=api_key)
    prompt = _build_llm_prompt(payload, candidates, tie_breakers, top_n_count, candidate_limit)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "당신은 대학생 시간표 추천 전문가입니다. "
                "규칙 점수를 받지 않고 후보 시간표를 직접 평가해 점수와 Top 3 추천 결과만 JSON으로 반환합니다. "
                "각 추천 항목에는 timetableId, rank, score, tags만 포함합니다."
            ),
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=LlmRecommendationResponse,
        ),
    )

    content = response.text or "{}"
    llm_result = _parse_llm_json(content)
    recommendations = _normalize_llm_recommendations(llm_result, tie_breakers, top_n_count)

    if not recommendations:
        raise ValueError("LLM did not return valid recommendations")

    return recommendations


def filter_payload(
    payload: Any,
    top_n_count: int = 3,
    use_llm: bool = True,
    llm_model: str = DEFAULT_LLM_MODEL,
) -> dict[str, Any]:
    timetables = extract_timetables(payload)
    tie_breakers = build_tie_breakers(timetables)
    recommendation_source = "rule"
    llm_error = None

    if use_llm and _get_google_api_key():
        try:
            recommendations = recommend_with_llm(payload, timetables, tie_breakers, top_n_count, llm_model)
            recommendation_source = "llm"
        except Exception as exc:
            llm_error = str(exc)
            recommendations = top_n(tie_breakers, top_n_count)
    else:
        recommendations = top_n(tie_breakers, top_n_count)

    result = {
        "count": len(timetables),
        "top_n": top_n_count,
        "source": recommendation_source,
        "recommendations": recommendations,
    }
    if llm_error:
        result["llm_error"] = llm_error
    return result


def resolve_default_input(script_dir: Path) -> Path:
    return script_dir / "sample_request.json"


def resolve_path(path_text: str | None, default_path: Path, script_dir: Path) -> Path:
    path = Path(path_text) if path_text else default_path
    if not path.is_absolute() and not path.exists():
        script_relative = script_dir / path
        if script_relative.exists():
            path = script_relative
    if not path.is_absolute() and path.parent == Path("."):
        path = script_dir / path
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Recommend Top3 timetable candidates.")
    parser.add_argument("--input", required=False, help="Path to timetable candidates JSON.")
    parser.add_argument("--output", required=False, help="Optional path to save recommendation result JSON.")
    parser.add_argument("--top-n", type=int, default=3, help="Number of recommendations to return.")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM ranking and use rule-based ranking only.")
    parser.add_argument("--model", default=DEFAULT_LLM_MODEL, help="Gemini model name for LLM ranking.")
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    input_path = resolve_path(args.input, resolve_default_input(script_dir), script_dir)

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = filter_payload(payload, top_n_count=args.top_n, use_llm=not args.no_llm, llm_model=args.model)
    recommendations_json = json.dumps(result["recommendations"], ensure_ascii=False, indent=2)

    if args.output:
        output_path = resolve_path(args.output, script_dir / args.output, script_dir)
        output_path.write_text(recommendations_json, encoding="utf-8")
        print(f"추천 결과를 저장했습니다: {output_path}")
    if result["recommendations"]:
        print(recommendations_json)
    else:
        print("추천할 시간표가 없습니다.")


if __name__ == "__main__":
    main()
