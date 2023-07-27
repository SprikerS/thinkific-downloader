import argparse
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
from pathvalidate import sanitize_filename
from typing import IO


browser = None
cookies = None
course_url  = None
logger: logging.Logger = None
quality = None


def log_subprocess_output(prefix: str, pipe: IO[bytes]):
    if pipe:
        for line in iter(lambda: pipe.read(1), ''):
            logger.debug('[%s]: %r', prefix, line.decode('utf8').strip())
        pipe.flush()


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


def init():
    global browser, course_url, DOWNLOAD_DIR, logger, quality

    parser = argparse.ArgumentParser(description='Thinkific Downloader')
    parser.add_argument('-c', '--course-url', dest='course_url', type=str, help='The URL of the course to download', required=True)
    parser.add_argument('-q', '--quality', dest='quality', type=int, help='The quality of the video to download')
    parser.add_argument('-b', '--browser', dest='browser', choices=['chrome', 'firefox', 'opera', 'edge', 'brave', 'chromium', 'vivaldi', 'safari'], help='The browser to use for authentication', required=True)
    parser.add_argument('-d', '--directory', dest='directory', type=str, help='The directory to download the course to')

    args = parser.parse_args()
    if args.browser:
        browser = args.browser
    if args.course_url:
        course_url = args.course_url
    if args.directory is not None:
        DOWNLOAD_DIR = args.directory
    if args.quality:
        quality = args.quality

    # setup a logger
    logger = logging.getLogger(__name__)
    logging.root.setLevel(LOG_LEVEL)

    # create a colored formatter for the console
    console_formatter = ColoredFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # create a handler for console logging
    stream = logging.StreamHandler()
    stream.setLevel(LOG_LEVEL)
    stream.setFormatter(console_formatter)

    # construct the logger
    logger = logging.getLogger('thinkific-downloader')
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(stream)


class MethodsRequests:
    @staticmethod
    def _get(url: str, cookies=None, max_retries=3):
        for i in range(max_retries):
            try:
                resp = requests.get(url, cookies=cookies, timeout=10)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                # Si ocurre un error en la solicitud, se imprimirá un mensaje de advertencia
                # y se intentará nuevamente hasta que se alcance el máximo de intentos
                logger.warning('Error fetching URL: {}, retrying... ({}) '.format(url, i + 1))
        sys.exit(1)
        # raise Exception('Error fetching url: {}'.format(url) + str(e))


class Thinkific:
    def __init__(self) -> None:
        global cookies
        self.domain, self.course = self._extract_domain_course()

        if browser == 'chrome':
            cookies = browser_cookie3.chrome()
        elif browser == 'firefox':
            cookies = browser_cookie3.firefox()
        elif browser == 'opera':
            cookies = browser_cookie3.opera()
        elif browser == 'edge':
            cookies = browser_cookie3.edge()
        elif browser == 'brave':
            cookies = browser_cookie3.brave()
        elif browser == 'chromium':
            cookies = browser_cookie3.chromium()
        elif browser == 'vivaldi':
            cookies = browser_cookie3.vivaldi()

    def _extract_domain_course(self):
        pattern = r'(?i)https?://(?P<domain>[\w.-]+)/(?:courses/)?(?P<course>[\w-]+)'
        match = re.search(pattern, course_url)
        if match:
            return match.group('domain'), match.group('course')
        else:
            logger.error('> Error: Invalid URL format for course')
            sys.exit(1)

    def _course_info(self):
        _url = COURSE_URL.format(self.domain, self.course)
        try:
            resp = MethodsRequests._get(_url, cookies).json()
            if 'error' in resp:
                logger.error('Error: {}'.format(resp['error']))
                sys.exit(1)
            return resp
        except Exception as e:
            logger.error(f'> Error fetching course: {e}')

    def _thinkific_object(self, resp: dict):
        types_of_course = set()
        pattern_section = r'(?:Sección \d+: |Sección \d+ - )(.+)'
        pattern_chapter = r'^\d+\s*-\s*(.+)'
        try:
            thinkific_object = {}
            thinkific_object['id'] = resp['course']['id']
            thinkific_object['name'] = sanitize_filename(resp['course']['name'])
            thinkific_object['slug'] = resp['course']['slug']
            thinkific_object['len_sections'] = len(resp['chapters'])
            thinkific_object['len_chapters'] = len(resp['contents'])
            thinkific_object['sections'] = []
            for sec, chapter in enumerate(resp['chapters'], 1):
                section_info = {}
                section_name = re.sub(pattern_section, r'\1', chapter['name'])
                section_info['name'] = '{}'.format(sanitize_filename(section_name))
                section_info['number'] = str(sec).zfill(2)
                section_info['len_chapters'] = len(chapter['content_ids'])
                section_info['chapters'] = []
                for chap, content_id in enumerate(chapter['content_ids'], 1):
                    for index, content in enumerate(resp['contents'], 1):
                        types_of_course.add(content['contentable_type'])
                        if content['id'] == content_id and not content['payment_required']:
                            chapter_name = re.sub(pattern_chapter, r'\1', content['name'])
                            chapter_info = {
                                'index': index,
                                'name': '{}'.format(sanitize_filename(chapter_name)),
                                'number': str(chap).zfill(2),
                                'contentable_type': content['contentable_type'],
                                'contentable_id': content['contentable_id'],
                                'display_name': content['display_name'],
                            }
                            section_info['chapters'].append(chapter_info)
                thinkific_object['sections'].append(section_info)
            types_string = ' - '.join(types_of_course)
            logger.info(f'> Types    : {types_string}')
            return thinkific_object
        except Exception as e:
            logger.error(f'> Error generating thinkific object: {e}')

    def _extract_html(self, chapter: list, section_dir: str):
        try:
            _url = HTML_URL.format(self.domain, chapter['contentable_id'])
            file_name = '{} {}.html'.format(chapter['number'], chapter['name'])
            file_path = os.path.join(section_dir, file_name)
            if not os.path.exists(file_path):
                logger.info(f'> Getting information from the class {chapter["name"]}...')
                resp = MethodsRequests._get(_url, cookies).json()
                with open(file_path, 'w', encoding='utf8' ) as file:
                    file.write(resp['html_item']['html_text'])
                logger.info(f'> Successfully downloaded {file_name}')
            else:
                logger.info('> File {} already exists, skipping...'.format(file_name))
        except Exception as e:
            logger.exception('> Failed to write html file: {}'.format(e))

    def _verify_html(self, resp: dict, number_chapter: str, section_dir: str):
        html_text = resp['lesson']['html_text']
        if html_text is None:
            return
        logger.info('> External links found')
        soup = BeautifulSoup(html_text, 'html.parser')
        for a in soup.find_all('a', href=True):
            name = a.text.strip() if a.text else 'No name'
            href = a['href']

            url_name  = '{} {}.url'.format(number_chapter, sanitize_filename(name))
            file_path = os.path.join(section_dir, url_name)
            if not os.path.exists(file_path):
                url_body = f'[InternetShortcut]\nURL={href}'
                with open(os.path.join(section_dir, url_name), 'w', encoding='utf-8') as f:
                    f.write(url_body)
                logger.info(f'> Successfully downloaded {url_name}')
            else:
                logger.info('> File {} already exists, skipping...'.format(url_name))

    def _download_content(self, resp: dict, number_chapter: str, section_dir: str):
        if 'download_files' in resp and len(resp['download_files']) > 0:
            logger.info('> Material download found')
            for file in resp['download_files']:
                name = '{} {}'.format(number_chapter, sanitize_filename(file['file_name']))
                file_path = os.path.join(section_dir, name)
                if not os.path.exists(file_path):
                    link = file['download_url']
                    download_aria(link, name, section_dir)
                else:
                    logger.info('> File {} already exists, skipping...'.format(name))

    def _get_video_proxy(self, resp: dict):
        if 'videos' in resp and resp['videos'] is not None:
            identifier = resp['videos'][0]['identifier']
            try:
                videoproxy = VIDEOPROXY_URL.format(identifier)
                resp = MethodsRequests._get(videoproxy).text
                soup = BeautifulSoup(resp, 'html.parser')
                pattern = re.compile(r'embed/medias/.*\.jsonp')
                for script_tag in soup.find_all('script', src=True):
                    url_jsonp = script_tag['src']
                    if pattern.search(url_jsonp):
                        return url_jsonp
            except Exception as e:
                logger.exception(f'Error in VideoProxy: {e}')
        return None

    def _get_jsonp_data(self, url_jsonp: str):
        try:
            resp  = MethodsRequests._get(url_jsonp).text
            jsonp = re.search(r'window\[\'wistiajsonp-[^\'\]]+\'] = (.+?);', resp)
            if jsonp:
                jsonp_str = jsonp.group(1)
                json_data = json.loads(jsonp_str)
                return json_data
        except Exception as e:
            logger.exception(f'Error in JSONP: {e}')

    def _get_qualities(self, jsonp: list):
        selected_assets = []
        unique_heights  = set()
        try:
            for asset in jsonp['media']['assets']:
                type, height, width, url = asset['type'], asset['height'], asset['width'], asset['url']

                if height in unique_heights:
                    continue

                if type.endswith('_video') or type == 'original':
                    selected_assets.append({
                        'type'   : type,
                        'width'  : width,
                        'height' : height,
                        'url'    : url,
                    })
                unique_heights.add(height)

            return selected_assets
        except Exception as e:
            logger.exception(f'Error in Qualities: {e}')

    def _file_already_downloaded(self, file_path):
        aria2_file = file_path + '.aria2'
        return os.path.exists(file_path) and not os.path.exists(aria2_file)

    def _process_sources(self, resp: dict, number_chapter: str, chapter_name: str, section_dir: str):
        video_name = '{} {}.mp4'.format(number_chapter, chapter_name)
        video_path = os.path.join(section_dir, video_name)

        if not self._file_already_downloaded(video_path):
            try:
                logger.info('> Extracting video sources...')

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

                logger.info('> Successfully extracted video source')

                sources = sorted(qualities, key=lambda x: int(x.get('height')), reverse=True)
                source  = sources[0]
                if isinstance(quality, int):
                    source = min(sources, key=lambda x: abs(int(x.get('height')) - quality))
                video_url = source['url']

                logger.info('> Downloading video in resolution {}p'.format(source['height']))

                download_aria(video_url, video_name, section_dir)
            except Exception as e:
                logger.exception('> Failed to process sources: {}'.format(e))
        else:
            logger.info('> File {} already exists, skipping...'.format(video_name))

    def _extract_lesson(self, chapter: list, section_dir: str):
        try:
            number_chapter = chapter['number']
            chapter_name = chapter['name']
            logger.info('> Fetching video {}...'.format(chapter_name))
            _url = LESSON_URL.format(self.domain, chapter['contentable_id'])
            resp = MethodsRequests._get(_url, cookies).json()
            logger.info('> Successfully fetched video')

            # Check if there are external links
            self._verify_html(resp, number_chapter, section_dir)

            # Check for downloadable content
            self._download_content(resp, number_chapter, section_dir)

            # Check if there is a video
            self._process_sources(resp, number_chapter, chapter_name, section_dir)
        except Exception as e:
            logger.exception('> Failed to extract lesson: {}'.format(e))

    def _extract_download(self, chapter: list, section_dir: str):
        try:
            _url = DOWNLOAD_URL.format(self.domain, chapter['contentable_id'])
            resp = MethodsRequests._get(_url, cookies).json()

            # Save download files if exists
            if 'download_files' in resp and len(resp['download_files']) > 0:
                for file in resp['download_files']:
                    name = '{} {}'.format(chapter['number'], sanitize_filename(file['file_name']))
                    file_path = os.path.join(section_dir, name)
                    if not self._file_already_downloaded(file_path):
                        link = file['download_url']
                        download_aria(link, name, section_dir)
                    else:
                        logger.info('> File {} already exists, skipping...'.format(name))

            # Save content html is exists
            html_description = resp['download'].get('html_description')
            if html_description is not None:
                name = '{} {}.html'.format(chapter['number'], chapter['name'])
                file_path = os.path.join(section_dir, name)
                if not os.path.exists(file_path):
                    with open(os.path.join(section_dir, name), 'w', encoding='utf8') as file:
                        file.write(html_description)
                    logger.info(f'> Successfully downloaded {name}')
                else:
                    logger.info('> File {} already exists, skipping...'.format(name))

        except Exception as e:
            logger.exception('Could not get download type: {}'.format(e))

    def parse_sections(self, thinkific_object: dict):
        course_dir = os.path.join(DOWNLOAD_DIR, thinkific_object['name'])
        if not os.path.exists(course_dir):
            os.mkdir(course_dir)
        # with open(os.path.join(course_dir, f"{thinkific_object['slug']}.json"), 'w', encoding='utf-8') as file:
        #     json.dump(thinkific_object, file, indent=4, ensure_ascii=False)
        try:
            for sec, section in enumerate(thinkific_object['sections'], 1):
                # if sec == 1:
                section_name = '{} {}'.format(section['number'], section['name'])
                section_dir  = os.path.join(course_dir, section_name)
                if not os.path.exists(section_dir):
                    os.mkdir(section_dir)
                logger.info(f' ==================== Processing section {sec:02d} of {thinkific_object["len_sections"]:02d}  ====================')
                for chap, chapter in enumerate(section['chapters'], 1):
                    logger.info(f'> Procesing chapter {chapter["number"]} of {section["len_chapters"]:02d}')
                    type = chapter['contentable_type']
                    if type == 'HtmlItem':
                        self._extract_html(chapter, section_dir)
                    elif type == 'Lesson':
                        self._extract_lesson(chapter, section_dir)
                    elif type == 'Download':
                        self._extract_download(chapter, section_dir)
        except KeyboardInterrupt as e:
            logger.warning('> Program interrupted by user')


def main():
    logger.info('> Starting Thinkific Downloader...')
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