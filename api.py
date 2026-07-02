from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from recommendation_engine import filter_payload


app = FastAPI(
    title="Timetable Recommendation API",
    description="Rank backend-filtered timetable candidates and return Top3 recommendations.",
    version="1.0.0",
)


BASE_DIR = Path(__file__).parent


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Timetable Recommendation API",
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/recommend")
def recommend_timetables(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Request body example:

    {
      "candidates": [
        {
          "timetableId": 7,
          "feature": {
            "attendanceDays": 4,
            "earliestStartTime": "09:00:00",
            "latestEndTime": "17:45:00",
            "firstPeriodCount": 1,
            "longestBreakMinutes": 15,
            "longBreakCount": 0,
            "lunchBreakCount": 2,
            "earlyFinishDayCount": 0
          },
          "courses": []
        }
      ]
    }
    """
    try:
        result = filter_payload(payload)
        return result["recommendations"]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/sample/recommend")
def recommend_sample() -> list[dict[str, Any]]:
    input_path = BASE_DIR / "sample_request.json"

    if not input_path.exists():
        raise HTTPException(status_code=404, detail=f"sample request not found: {input_path.name}")

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        result = filter_payload(payload)
        return result["recommendations"]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
