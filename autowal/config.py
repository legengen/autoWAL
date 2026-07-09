import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SURVEY_URL = "https://myd.iscn.org.cn/#/s/yCWFPyRr?sourceID=719419"
SURVEY_JSON = os.path.join(PROJECT_ROOT, "survey_structured.json")
CHROMEDRIVER = os.path.join(PROJECT_ROOT, "drivers", "chromedriver-win64", "chromedriver.exe")
