import logging
import os
import time


LOG_DIR_PATH    = os.path.join(os.getcwd(), 'logs')
LOG_FILE_PATH   = os.path.join(os.getcwd(), 'logs', f'{time.strftime("%Y-%m-%d-%I-%M-%S")}.log')
LOG_FORMAT      = '[%(asctime)s] [%(name)s] %(levelname)s: %(message)s' # [%(funcName)s:%(lineno)d]
LOG_DATE_FORMAT = '%I:%M:%S'
LOG_LEVEL       = logging.INFO


HOME_DIR     = os.getcwd()
DOWNLOAD_DIR = os.path.join(os.getcwd(), 'out')
TEMP_DIR     = os.path.join(os.getcwd(), 'tmp')


COURSE_URL     = 'https://{}/api/course_player/v2/courses/{}'
HTML_URL       = 'https://{}/api/course_player/v2/html_items/{}'
LESSON_URL     = 'https://{}/api/course_player/v2/lessons/{}'
VIDEOPROXY_URL = 'https://platform.thinkific.com/videoproxy/v1/play/{}'
DOWNLOAD_URL   = 'https://{}/api/course_player/v2/downloads/{}'


# HOME https://cursos.devtalles.com/api/course_player/v2/courses/flutter-movil-cero-a-experto
# CHAPTERS https://cursos.devtalles.com/api/course_player/v2/courses/17628065/chapters
# LESSONS https://cursos.devtalles.com/api/course_player/v2/lessons/17628065
# CONTENTS https://cursos.devtalles.com/api/course_player/v2/contents/42481177