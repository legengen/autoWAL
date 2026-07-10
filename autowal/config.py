import os
import re


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURVEY_BASE_URL = "https://myd.iscn.org.cn/#/s/yCWFPyRr"
DEFAULT_SOURCE_ID = "719419"
SURVEY_JSON = os.path.join(PROJECT_ROOT, "survey_structured.json")
CHROMEDRIVER = os.path.join(PROJECT_ROOT, "drivers", "chromedriver-win64", "chromedriver.exe")


def validate_source_id(value):
    source_id = str(value)
    if re.fullmatch(r"[0-9]{6}", source_id) is None:
        raise ValueError("source ID 必须是恰好 6 位数字")
    return source_id


def build_survey_url(source_id=DEFAULT_SOURCE_ID):
    return f"{SURVEY_BASE_URL}?sourceID={validate_source_id(source_id)}"


SURVEY_URL = build_survey_url()
