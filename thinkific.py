import argparse
import base64
import browser_cookie3
import json
import logging
import re
import requests
import subprocess
import sys


from bs4 import BeautifulSoup
from coloredlogs import ColoredFormatter
from constants import *
from pathlib import Path
from pathvalidate import sanitize_filename
from typing import IO


browser: str = None
cookies: str = None
course_url: str = None
disable_original: bool = False
logger: logging.Logger = None
quality: int = None


def aria_file_exists(file_path: str) -> bool:
    aria2_file = file_path + '.aria2'
    return os.path.exists(file_path) and not os.path.exists(aria2_file)


def calculate_time(func):
    def wrapper(*args, **kwargs):
        logger.info('> Starting Thinkific Downloader...')
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = int(end_time - start_time)
        minutes = elapsed_time // 60
        seconds = elapsed_time % 60
        logger.info(f'> Thinkific Downloader finished, elapsed time {minutes:02d}m {seconds:02d}s')
        return result
    return wrapper


def decode_base64(base64_str: str) -> str:
    message_bytes   = base64.b64decode(base64_str)
    message_decoded = message_bytes.decode('utf-8')
    message_string  = re.sub(r'\d', '', message_decoded)
    return message_string


def download_aria(url: str, filename: str, file_dir: str):
    args = [
        'aria2c',
        f'{url}',
        '-o',
        f'{filename}',
        '-d',
        f'{file_dir}',
        '-j16',
        '-s20',
        '-x16',
        '-c',
        '--auto-file-renaming=false',
        '--summary-interval=0',
        f'--file-allocation=none',
    ]
    process = subprocess.Popen(args)
    log_subprocess_output('aria2c-stdout', process.stdout)
    log_subprocess_output('aria2c-stderr', process.stderr)
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception('Return code from the downloader was non-0 (error)')
    return ret_code


def file_exists(file_name: str, file_path: str) -> bool:
    if os.path.exists(file_path):
        logger.info(f'> File {file_name} already exists, skipping...')
        return True
    return False


def log_subprocess_output(prefix: str, pipe: IO[bytes]):
    if pipe:
        for line in iter(lambda: pipe.read(1), ''):
            logger.debug('[%s]: %r', prefix, line.decode('utf8').strip())
        pipe.flush()


def init():
    global browser, course_url, disable_original, DOWNLOAD_DIR, logger, quality

    parser = argparse.ArgumentParser(description='Thinkific Downloader')
    parser.add_argument(
        '-b',
        '--browser',
        choices = [
            'brave',
            'chrome',
            'chromium',
            'edge',
            'firefox',
            'librewolf',
            'opera-gx',
            'opera',
            'safari',
            'vivaldi',
        ],
        dest     = 'browser',
        help     = 'The browser to use for authentication',
        required = True,
        type     = str,
    )
    parser.add_argument(
        '-c',
        '--course-url',
        dest     = 'course_url',
        help     = 'The URL of the course to download',
        required = True,
        type     = str,
    )
    parser.add_argument(
        '-q',
        '--quality',
        dest = 'quality',
        help = 'The quality of the video to download',
        type = int,
    )
    parser.add_argument(
        '-d',
        '--directory',
        dest = 'directory',
        help = 'The directory to download the course to',
        type = str,
    )
    parser.add_argument(
        '--disable-original',
        action = 'store_true',
        dest   = 'disable_original',
        help   = 'Disable downloading of original quality videos',
    )

    args = parser.parse_args()
    if args.browser:
        browser = args.browser
    if args.course_url:
        course_url = args.course_url
    if args.disable_original:
        disable_original = args.disable_original
    if args.directory is not None:
        DOWNLOAD_DIR = args.directory
    if args.quality:
        quality = args.quality

    # setup a logger
    logger = logging.getLogger(__name__)
    logging.root.setLevel(LOG_LEVEL)
    console_formatter = ColoredFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    stream = logging.StreamHandler()
    stream.setLevel(LOG_LEVEL)
    stream.setFormatter(console_formatter)

    logger = logging.getLogger('thinkific-downloader')
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(stream)

    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)


class MethodsRequests:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def _get(self, url: str, cookies=None) -> requests.Response:
        for retry in range(self.max_retries):
            try:
                resp = requests.get(url, cookies=cookies, timeout=10)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException:
                logger.warning(f'> Error fetching URL: {url}, retrying... ({retry + 1}) ')
        sys.exit(1)


class Thinkific:
    def __init__(self) -> None:
        global cookies

        self.methods_requests    = MethodsRequests()
        self.domain, self.course = self._extract_domain_course()
        cookies                  = self._extract_cookies()


    def _extract_cookies(self):
        browser_map = {
            'brave'     : browser_cookie3.brave,
            'chrome'    : browser_cookie3.chrome,
            'chromium'  : browser_cookie3.chromium,
            'edge'      : browser_cookie3.edge,
            'firefox'   : browser_cookie3.firefox,
            'librewolf' : browser_cookie3.librewolf,
            'opera-gx'  : browser_cookie3.opera_gx,
            'opera'     : browser_cookie3.opera,
            'safari'    : browser_cookie3.safari,
            'vivaldi'   : browser_cookie3.vivaldi,
        }

        return browser_map[browser](domain_name=self.domain)


    def _extract_domain_course(self) -> tuple[str, str]:
        regex = r'(?i)https?://(?P<domain>[\w.-]+)/(?:courses/)?(?P<course>[\w-]+)'
        match = re.search(regex, course_url)
        if match:
            return match.group('domain'), match.group('course')
        else:
            logger.error('> Error: Invalid URL format for course')
            sys.exit(1)


    def _course_info(self) -> dict:
        _url = COURSE_URL.format(self.domain, self.course)
        try:
            resp = self.methods_requests._get(_url, cookies).json()
            if 'error' in resp:
                logger.error(f'Error: {resp["error"]}')
                sys.exit(1)
            return resp
        except Exception as e:
            logger.error(f'> Error fetching course: {e}')


    def _thinkific_object(self, resp: dict) -> dict:
        types_course  = set()
        regex_section = r'(?:Sección \d+: |Sección \d+ - )(.+)'
        regex_chapter = r'^\d+\s*-\s*(.+)'
        try:
            thinkific_object = {}
            thinkific_object['id']           = resp['course']['id']
            thinkific_object['name']         = sanitize_filename(resp['course']['name'])
            thinkific_object['slug']         = resp['course']['slug']
            thinkific_object['len_sections'] = len(resp['chapters'])
            thinkific_object['len_chapters'] = len(resp['contents'])
            thinkific_object['sections']     = []
            for sec, chapter in enumerate(resp['chapters'], 1):
                section_info                 = {}
                section_name                 = re.sub(regex_section, r'\1', chapter['name'])
                section_info['name']         = f'{sanitize_filename(section_name)}'
                section_info['number']       = str(sec).zfill(2)
                section_info['len_chapters'] = len(chapter['content_ids'])
                section_info['chapters']     = []
                for chap, content_id in enumerate(chapter['content_ids'], 1):
                    for index, content in enumerate(resp['contents'], 1):
                        types_course.add(content['contentable_type'])
                        if content['id'] == content_id and not content['payment_required']:
                            chapter_name = re.sub(regex_chapter, r'\1', content['name'])
                            chapter_info = {
                                'index'            : index,
                                'name'             : f'{sanitize_filename(chapter_name)}',
                                'number'           : str(chap).zfill(2),
                                'display_name'     : content['display_name'],
                                'contentable_id'   : content['contentable_id'],
                                'contentable_type' : content['contentable_type'],
                            }
                            section_info['chapters'].append(chapter_info)
                thinkific_object['sections'].append(section_info)
            types_string = ' - '.join(types_course)
            logger.info(f'> Types    : {types_string}')
            return thinkific_object
        except Exception as e:
            logger.error(f'> Error generating thinkific object: {e}')


    def _extract_html(self, chapter: list, section_dir: str) -> None:
        try:
            _url = HTML_URL.format(self.domain, chapter['contentable_id'])
            file_name = f'{chapter["number"]} {chapter["name"]}.html'
            file_path = os.path.join(section_dir, file_name)
            if not file_exists(file_name, file_path):
                logger.info(f'> Getting information from the class {chapter["name"]}...')
                resp = self.methods_requests._get(_url, cookies).json()
                with open(file_path, 'w', encoding='utf8' ) as file:
                    file.write(resp['html_item']['html_text'])
                logger.info(f'> Successfully downloaded {file_name}')
        except Exception as e:
            logger.exception(f'> Could not get html type: {e}')


    def _verify_html(self, resp: dict, number_chapter: str, section_dir: str) -> None:
        html_text = resp['lesson']['html_text']
        if html_text is None:
            return
        logger.info('> External links found')
        soup = BeautifulSoup(html_text, 'html.parser')
        for a in soup.find_all('a', href=True):
            name = a.text.strip() if a.text else 'No name'
            href = a['href']

            file_name = f'{number_chapter} {sanitize_filename(name)}.url'
            file_path = os.path.join(section_dir, file_name)
            if not file_exists(file_name, file_path):
                url_body = f'[InternetShortcut]\nURL={href}'
                with open(os.path.join(section_dir, file_name), 'w', encoding='utf-8') as f:
                    f.write(url_body)
                logger.info(f'> Successfully downloaded {file_name}')


    def _files_download(self, resp: dict, chapter: list, section_dir: str) -> None:
        try:
            if 'download_files' in resp and len(resp['download_files']) > 0:
                logger.info('> Material download found')
                for file in resp['download_files']:
                    file_name = f'{chapter["number"]} {sanitize_filename(file["file_name"])}'
                    file_path = os.path.join(section_dir, file_name)
                    if not file_exists(file_name, file_path):
                        link = file['download_url']
                        download_aria(link, file_name, section_dir)
        except Exception as e:
            logger.exception(f'> Failed to download file: {e}')


    def _get_video_proxy(self, resp: dict) -> str:
        if 'videos' in resp and resp['videos'] is not None:
            identifier = resp['videos'][0]['identifier']
            try:
                proxy = VIDEOPROXY_URL.format(identifier)
                resp  = self.methods_requests._get(proxy).text
                soup  = BeautifulSoup(resp, 'html.parser')
                regex = re.compile(r'embed/medias/.*\.jsonp')
                for script_tag in soup.find_all('script', src=True):
                    url_jsonp = script_tag['src']
                    if regex.search(url_jsonp):
                        return url_jsonp
            except Exception as e:
                logger.exception(f'> Error in VideoProxy: {e}')
        return None


    def _get_jsonp_data(self, url_jsonp: str) -> dict:
        try:
            resp  = self.methods_requests._get(url_jsonp).text
            jsonp = re.search(r'window\[\'wistiajsonp-[^\'\]]+\'] = (.+?);', resp)
            if jsonp:
                jsonp_str = jsonp.group(1)
                json_data = json.loads(jsonp_str)
                return json_data
        except Exception as e:
            logger.exception(f'> Error in JSONP: {e}')


    def _get_qualities(self, jsonp: dict) -> list[dict]:
        unique_heights  = set()
        selected_assets = []
        try:
            for asset in jsonp['media']['assets']:
                height, type, url, width = asset['height'], asset['type'], asset['url'], asset['width']

                if not (type.endswith('_video') or (not disable_original and type == 'original')):
                    continue

                if height in unique_heights:
                    continue

                selected_assets.append({
                    'height' : height,
                    'type'   : type,
                    'url'    : url,
                    'width'  : width,
                })
                unique_heights.add(height)

            return selected_assets
        except Exception as e:
            logger.exception(f'> Error in Qualities: {e}')


    def _process_sources(self, resp: dict, number_chapter: str, chapter_name: str, section_dir: str) -> None:
        video_name = f'{number_chapter} {chapter_name}.mp4'
        video_path = os.path.join(section_dir, video_name)

        if not aria_file_exists(video_path):
            logger.info('> Extracting video sources...')
            try:
                proxy = self._get_video_proxy(resp)
                if proxy is None:
                    logger.info('> Identifier url could not be found')
                    return

                jsonp = self._get_jsonp_data(proxy)
                if jsonp is None:
                    logger.info('> Jsonp could not be found')
                    return

                qualities = self._get_qualities(jsonp)
                if qualities is None:
                    logger.info('> No video sources found')
                    return

                sources = sorted(qualities, key=lambda x: int(x.get('height')), reverse=True)
                source  = sources[0]
                if isinstance(quality, int):
                    source = min(sources, key=lambda x: abs(int(x.get('height')) - quality))
                video_url = source['url']

                logger.info(f'> Downloading video in resolution {source["height"]}p')

                download_aria(video_url, video_name, section_dir)
            except Exception as e:
                logger.exception(f'> Failed to process sources: {e}')
        else:
            logger.info(f'> File {video_name} already exists, skipping...')


    def _extract_lesson(self, chapter: list, section_dir: str) -> None:
        try:
            chapter_name   = chapter['name']
            chapter_number = chapter['number']

            logger.info(f'> Fetching video {chapter_name}...')
            _url = LESSON_URL.format(self.domain, chapter['contentable_id'])
            resp = self.methods_requests._get(_url, cookies).json()

            # Check if there are external links
            self._verify_html(resp, chapter_number, section_dir)

            # Check for downloadable content
            self._files_download(resp, chapter, section_dir)

            # Check if there is a video
            self._process_sources(resp, chapter_number, chapter_name, section_dir)
        except Exception as e:
            logger.exception(f'> Could not get lesson type: {e}')


    def _extract_download(self, chapter: list, section_dir: str) -> None:
        try:
            _url = DOWNLOAD_URL.format(self.domain, chapter['contentable_id'])
            resp = self.methods_requests._get(_url, cookies).json()

            # Save download files if exists
            self._files_download(resp, chapter, section_dir)

            # Save content html is exists
            html_description = resp['download'].get('html_description')
            if html_description is not None:
                file_name = f'{chapter["number"]} {chapter["name"]}.html'
                file_path = os.path.join(section_dir, file_name)
                if not file_exists(file_name, file_path):
                    with open(os.path.join(section_dir, file_name), 'w', encoding='utf8') as file:
                        file.write(html_description)
                    logger.info(f'> Successfully downloaded {file_name}')
        except Exception as e:
            logger.exception(f'> Could not get download type: {e}')


    def _get_quiz_questions(self, resp: str) -> str:
        try:
            file_contents = '<h3 style="color: red">The answers of this quiz are marked with [•]</h3>'
            for question in resp['questions']:
                prompt = BeautifulSoup(question['prompt'], 'html.parser')
                file_contents += f'<strong>{question["position"] + 1}) {prompt.text}</strong><br>'

                for img in prompt.find_all('img', src=True):
                    img = img['src']
                    file_contents += f'<br><img style="max-width: 70%" src="{img}"><br>'

                if question['text_explanation']:
                    explanation = BeautifulSoup(question['text_explanation'], 'html.parser').text
                    file_contents += f'Explanation: {explanation} <br>'

                for choice in resp['choices']:
                    if choice['question_id'] == question['id']:
                        answer = decode_base64(choice['credited'])
                        string = BeautifulSoup(choice['text'], 'html.parser').text
                        file_contents += f"<br>{'[•]' if answer == 'true' else '[ ]'} {string}"

                file_contents += '<br><br>'
            return file_contents
        except Exception as e:
            logger.exception(f'> Error while getting quiz questions: {e}')


    def _extract_quiz(self, chapter: dict, section_dir: str) -> None:
        try:
            _url = QUIZ_URL.format(self.domain, chapter['contentable_id'])
            resp = self.methods_requests._get(_url, cookies).json()

            file_name = f'{chapter["number"]} {chapter["name"]}.html'
            file_path = os.path.join(section_dir, file_name)

            if not file_exists(file_name, file_path):
                quiz_html = self._get_quiz_questions(resp)
                with open(os.path.join(section_dir, file_name), 'w', encoding='utf8') as file:
                    file.write(quiz_html)
                logger.info(f'> Successfully downloaded {file_name}')
        except Exception as e:
            logger.exception(f'> Could not get quiz type: {e}')


    def parse_sections(self, thinkific_object: dict) -> None:
        course_dir = os.path.join(DOWNLOAD_DIR, thinkific_object['name'])
        Path(course_dir).mkdir(parents=True, exist_ok=True)
        # with open(os.path.join(course_dir, f"{thinkific_object['slug']}.json"), 'w', encoding='utf-8') as file:
        #     json.dump(thinkific_object, file, indent=4, ensure_ascii=False)
        extract_functions = {
            'Download' : self._extract_download,
            'HtmlItem' : self._extract_html,
            'Lesson'   : self._extract_lesson,
            'Quiz'     : self._extract_quiz,
        }
        try:
            for section in thinkific_object['sections']:
                section_name = f'{section["number"]} {section["name"]}'
                section_dir  = os.path.join(course_dir, section_name)
                Path(section_dir).mkdir(parents=True, exist_ok=True)
                logger.info(f'==================== Processing section {section["number"]} of {thinkific_object["len_sections"]:02d} ====================')
                for chapter in section['chapters']:
                    logger.info(f'> Procesing chapter {chapter["number"]} of {section["len_chapters"]:02d}')
                    type = chapter['contentable_type']
                    if type in extract_functions:
                        extract_functions[type](chapter, section_dir)
                    else:
                        logger.warning(f'> Type {type} not found')
        except KeyboardInterrupt:
            logger.warning('> Program interrupted by user')


@calculate_time
def main():
    thinkific = Thinkific()

    logger.info('> Getting course information...')
    course_info = thinkific._course_info()

    logger.info('> Generating thinkific object...')
    course_json = thinkific._thinkific_object(course_info)

    course_title  = course_json.get('name')
    section_count = course_json.get('len_sections')
    chapter_count = course_json.get('len_chapters')
    logger.info(f'> Course   : {course_title}')
    logger.info(f'> Sections : {section_count}')
    logger.info(f'> Chapters : {chapter_count}')

    logger.info('> Starting download...')
    thinkific.parse_sections(course_json)


if __name__ == '__main__':
    init()
    main()