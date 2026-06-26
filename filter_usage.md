# filter.py 사용 방법

## 역할

`filter.py`는 AI 1의 필터링 엔진입니다.

백엔드가 생성한 여러 시간표 후보를 입력으로 받아서, 사용자가 선택한 조건을 검사한 뒤 조건을 통과한 시간표를 최대 30개까지 반환합니다.

추천 점수 계산, Top3 선정, 최종 추천 문구 생성은 AI 2의 `recommend.py`에서 처리합니다.

## 파일

- `filter.py`: 필터링 엔진
- `filter_sample_input.json`: 백엔드 시간표 후보 예시
- `filter_sample_options.json`: 사용자 옵션 예시
- `filtered_output.json`: 실행 후 생성되는 결과 예시 파일명

## 실행 명령

```bash
python filter.py --input filter_sample_input.json --options filter_sample_options.json --output filtered_output.json
```

현재 작업 폴더 기준으로 실행한다면:

```bash
cd outputs
python filter.py --input filter_sample_input.json --options filter_sample_options.json --output filtered_output.json
```

## 입력 데이터 형식

백엔드에서 넘겨주는 시간표 후보는 아래 구조를 권장합니다.

```json
{
  "timetables": [
    {
      "id": "tt_1",
      "summary": {
        "total_credits": 18,
        "free_days": ["월", "금"],
        "commute_days": 3
      },
      "courses": [
        {
          "name": "자료구조",
          "credits": 3,
          "time": "화 09:00~11:50",
          "major": "소프트웨어공학전공",
          "category": "전공"
        }
      ]
    }
  ]
}
```

## 옵션 데이터 형식

사용자가 화면에서 선택한 값은 옵션 JSON으로 들어갑니다.

예를 들어 사용자가 아래처럼 선택했다면:

```text
학년: 3학년
목표학점: 18학점
공강요일: 금요일
사회봉사: 포함 안 함
```

옵션 JSON은 이렇게 만들면 됩니다.

```json
{
  "현재학년": 3,
  "전공": ["소프트웨어공학전공", "정보통신공학전공"],
  "목표학점": 18,
  "선호공강요일": ["금"],
  "사회봉사포함": false
}
```

`목표학점`은 시간표를 탈락시키는 조건이 아니라 선호 조건으로 처리합니다.

목표학점과 일치하면 `reasons`에 기록하고, 다르면 `warnings`에 몇 학점 차이인지 기록합니다. 실제 점수 계산은 AI 2의 `recommend.py`에서 목표학점에 가까울수록 높은 점수를 주는 방식으로 처리하는 것이 좋습니다.

범위 조건을 쓰고 싶다면 `목표학점` 대신 `최소학점`, `최대학점`을 사용하면 됩니다.

```json
{
  "현재학년": 2,
  "전공": ["소프트웨어공학전공", "정보통신공학전공"],
  "선호공강요일": ["월", "금"],
  "필수공강요일": ["금"],
  "최소학점": 15,
  "최대학점": 21,
  "사회봉사포함": false,
  "최대등교일수": 4,
  "최소시작시간": "09:00",
  "최대종료시간": "18:00"
}
```

## 실행 방식

입력 JSON 안에 `옵션`과 `후보`가 같이 들어 있다면 옵션 파일 없이 실행할 수 있습니다.

```bash
python filter.py --input input_payload.json --output filtered_timetables.json
```

입력 시간표와 사용자 옵션을 따로 관리한다면 이렇게 실행합니다.

```bash
python filter.py --input candidate_timetables.json --options user_options_template.json --output filtered_timetables.json
```

매번 터미널에서 직접 선택지를 입력하고 싶다면 `--interactive`를 사용합니다.

```bash
python filter.py --input candidate_timetables.json --output filtered_timetables.json --interactive
```

실행하면 아래 값을 직접 입력할 수 있습니다.

```text
현재학년
전공
목표학점
최소학점 / 최대학점
선호공강요일
사회봉사 포함 여부
```

예시 입력:

```text
현재학년 (예: 3): 3
전공 (쉼표로 구분, 예: 소프트웨어공학전공,정보통신공학전공): 소프트웨어공학전공,정보통신공학전공
목표학점 (예: 18, 범위 조건이면 Enter): 18
선호공강요일 (예: 월 금 또는 금): 금
사회봉사 포함? (y/N): n
```

## 출력 형식

```json
{
  "count": 1,
  "limit": 30,
  "results": [
    {
      "id": "tt_1",
      "reasons": [
        "총 학점 18학점이 설정 범위에 맞습니다.",
        "필수 공강요일 금을 만족합니다.",
        "선호 공강요일 금, 월을 포함합니다."
      ],
      "timetable": {
        "id": "tt_1"
      }
    }
  ]
}
```

AI 2는 이 출력의 `results` 배열을 받아서 `score()`, `rank()`, `top3()`를 적용하면 됩니다.

## 코드에서 직접 사용하는 방법

```python
from filter import filter_payload

result = filter_payload(
    payload=backend_timetable_payload,
    options=user_options,
    limit=30,
)
```

## 현재 구현된 조건

- 최소 학점
- 최대 학점
- 필수 공강요일
- 제외요일
- 선호 공강요일
- 최대 등교일수
- 최소 시작시간
- 최대 종료시간
- 사회봉사 포함 여부
- 시간표 내부 시간 충돌
- 전공 조건

전공 조건은 과목 데이터에 `major` 값이 있을 때만 검사합니다. 백엔드 데이터에 전공 정보가 없다면 전공 조건 때문에 탈락시키지 않습니다.

## 사회봉사 조건 처리 방식

`사회봉사포함`이 `false`여도 무조건 탈락시키지 않습니다.

처리 방식은 아래와 같습니다.

```text
사회봉사 없는 시간표가 있으면
→ 사회봉사 없는 시간표만 결과에 포함

사회봉사 없는 시간표가 하나도 없으면
→ 사회봉사 포함 시간표도 결과에 포함
→ 대신 warnings에 이유 표시
```

예시:

```json
{
  "warnings": [
    "사회봉사 제외 조건을 만족하는 시간표가 없어 사회봉사 포함 후보를 결과에 포함했습니다."
  ],
  "results": [
    {
      "id": "tt_1",
      "warnings": [
        "사회봉사Ⅰ가 포함되어 있지만 대체 후보가 없어 유지되었습니다."
      ]
    }
  ]
}
```

이렇게 하면 필터 결과가 0개로 끊기지 않고, AI 2가 추천 점수 계산에서 사회봉사 포함 후보를 낮게 평가할 수 있습니다.
