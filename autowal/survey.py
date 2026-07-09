import json

from .config import SURVEY_JSON


def load_survey(path=SURVEY_JSON):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
