import browser_cookie3
import json
import logging
import os
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


browser = 'chrome'
cookies = None
course  = 'react-cero-experto'
logger: logging.Logger = None
quality = 1080


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


def pre_run():
    global logger

    Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(LOG_DIR_PATH).mkdir(parents=True, exist_ok=True)
    Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(__name__)
    logging.root.setLevel(LOG_LEVEL)
    console_formatter = ColoredFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    stream = logging.StreamHandler()
    stream.setLevel(LOG_LEVEL)
    stream.setFormatter(console_formatter)
    file_handler = logging.FileHandler(LOG_FILE_PATH)
    file_handler.setFormatter(file_formatter)
    logger = logging.getLogger('thinkific-downloader')
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(stream)
    logger.addHandler(file_handler)


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
        raise Exception('Error fetching url: {}'.format(url) + str(e))

    @staticmethod
    def _post(url: str, data: dict):
        try:
            resp = requests.post(url, cookies=cookies, data=data, timeout=10)
            resp.raise_for_status()
            return resp
        except Exception as e:
            raise Exception('Error fetching url: {}'.format(url) + str(e))


class Thinkific:
    def __init__(self, url: str) -> None:
        global cookies

        self.url = url
        self.domain, self.course = self._extract_domain_course()

        if browser == None:
            logger.error('No browser for cookie extraction was specified')
            sys.exit(1)

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
        match = re.search(pattern, self.url)
        if match:
            return match.group('domain'), match.group('course')
        else:
            logger.error('Invalid URL format')
            sys.exit(1)


    def _fetch_course(self):
        _url = COURSE_URL.format(self.domain, self.course)
        resp = MethodsRequests._get(_url, cookies).json()
        if 'error' in resp:
            logger.error('Error: {}'.format(resp['error']))
            sys.exit(1)
        return resp


    def _thinkific_object(self, json_resp: dict):

        pattern_section = r'(?:Sección \d+: |Sección \d+ - )(.+)'
        pattern_chapter = r'^\d+\s*-\s*(.+)'

        try:
            _types = set()
            thinkific_object = {}
            thinkific_object['id'] = json_resp['course']['id']
            thinkific_object['name'] = sanitize_filename(json_resp['course']['name'])
            thinkific_object['slug'] = json_resp['course']['slug']
            thinkific_object['len_sections'] = len(json_resp['chapters'])
            thinkific_object['len_chapters'] = len(json_resp['contents'])
            thinkific_object['sections'] = []
            for sec, chapter in enumerate(json_resp['chapters'], 1):
                section_info = {}
                section_name = re.sub(pattern_section, r'\1', chapter['name'])
                section_info['name'] = '{}'.format(sanitize_filename(section_name))
                section_info['number'] = str(sec).zfill(2)
                section_info['len_chapters'] = len(chapter['content_ids'])
                section_info['chapters'] = []
                for chap, content_id in enumerate(chapter['content_ids'], 1):
                    for index, content in enumerate(json_resp['contents'], 1):
                        _types.add(content['contentable_type'])
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
            with open(os.path.join('tmp', f"{json_resp['course']['slug']}.json"), 'w', encoding='utf-8') as file:
                json.dump(thinkific_object, file, indent=4, ensure_ascii=False)
            return thinkific_object, _types
        except Exception as e:
            logger.exception('Error generating thinkific object: {}'.format(e))


    def _extract_html(self, chapter: list, section_dir: str):
        try:
            _url = HTML_URL.format(self.domain, chapter['contentable_id'])
            resp = MethodsRequests._get(_url, cookies).json()
            file_name = '{} {}.html'.format(chapter['number'], chapter['name'])
            file_path = os.path.join(section_dir, file_name)
            with open(file_path, 'w', encoding='utf8' ) as file:
                file.write(resp['html_item']['html_text'])
            logger.info(f'> Successfully downloaded {file_name}')
        except Exception as e:
            logger.exception('Failed to write html file: {}'.format(e))


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


    def _processing_download(self, resp: dict):
        try:
            proxy = self._get_video_proxy(resp)
            if not proxy:
                return

            jsonp = self._get_jsonp_data(proxy)
            if not jsonp:
                return
            qualities = self._get_qualities(jsonp)
            if not qualities:
                return

            return qualities
        except Exception as e:
            logger.exception(f'Error in Processing Download: {e}')


    def _extract_lesson(self, chapter: list, section_dir: str):
        try:
            chapter_name = chapter['name']
            number_chapter = chapter['number']
            logger.info('> Fetching video {}...'.format(chapter_name))
            _url = LESSON_URL.format(self.domain, chapter['contentable_id'])
            resp = MethodsRequests._get(_url, cookies).json()
            logger.info('> Fetching video terminated')

            # Verificamos si la lesson tiene external links
            html_text = resp['lesson']['html_text']
            if html_text is not None:
                logger.info('> External links found')
                soup = BeautifulSoup(html_text, 'html.parser')
                for a in soup.find_all('a', href=True):
                    name = a.text.strip() if a.text else 'No name'
                    href = a['href']

                    url_name = '{} {}.url'.format(number_chapter, sanitize_filename(name))
                    url_body = f'[InternetShortcut]\nURL={href}'
                    with open(os.path.join(section_dir, url_name), 'w', encoding='utf-8') as f:
                        f.write(url_body)

            # Verificamos si la lesson tiene material descargable
            if 'download_files' in resp and len(resp['download_files']) > 0:
                logger.info('> Material download found')
                for file in resp['download_files']:
                    name = '{} {}'.format(number_chapter, sanitize_filename(file['file_name']))
                    link = file['download_url']
                    download_aria(link, name, section_dir)

            # Extraemos el video
            sources = self._processing_download(resp)
            sources = sorted(sources, key=lambda x: int(x.get('height')), reverse=True)
            if sources:
                source = sources[0]
                if isinstance(quality, int):
                    source = min(sources, key=lambda x: abs(int(x.get('height')) - quality))
                video_url = source['url']


                logger.info('> Successfully fetched video')
                video_name = '{} {}{}'.format(number_chapter, chapter_name, '.mp4')
                download_aria(video_url, video_name, section_dir)
            else:
                logger.info('> No video sources found')
        except Exception as e:
            logger.exception('> Failed to download video: {}'.format(e))


    def _extract_video_proxy(self, identifier: int):
        try:
            _url = VIDEOPROXY_URL.format(identifier)
            resp = MethodsRequests._get(_url)
            soup = BeautifulSoup(resp.text, 'html.parser')
            pattern = re.compile(r'embed/medias/.*\.jsonp')
            for script_tag in soup.find_all('script', src=True):
                url_jsonp = script_tag['src']
                if pattern.search(url_jsonp):
                    return url_jsonp
        except Exception as e:
            logger.exception('> Error VideoProxy: {}'.format(e))


    def _extract_jsonp_data(self, url_jsonp: str):
        try:
            resp  = MethodsRequests._get(url_jsonp)
            jsonp = re.search(r'window\[\'wistiajsonp-[^\'\]]+\'] = (.+?);', resp.text)
            if jsonp:
                jsonp_str = jsonp.group(1)
                json_data = json.loads(jsonp_str)
                return json_data
        except Exception as e:
            logger.exception('> Error JSONP: {}'.format(e))


    def _extract_quality(self, json_data: dict):
        global quality
        try:
            _values = {
                2160 : (3840, 2160),
                1440 : (2560, 1440),
                1080 : (1920, 1080),
                720  : (1280, 720),
                480  : (854, 480),
            }
            _temp = {}
            _, _ext = os.path.splitext(json_data['media']['name'])
            for asset in json_data['media']['assets']:
                if ((asset['type'].endswith('_video') or asset['type'] == 'original') and (asset['width'], asset['height']) in _values.values()):
                    _temp[asset['height']] = asset['url']
            if quality is not None and quality in _temp:
                return _temp[quality], _ext
            return _temp[max(_temp.keys())], _ext
        except Exception as e:
            logger.exception('> Error Quality: {}'.format(e))


    def _extract_download(self, chapter: list, section_dir: str):
        try:
            _url = DOWNLOAD_URL.format(self.domain, chapter['contentable_id'])
            resp = MethodsRequests._get(_url, cookies).json()

            # Save download files if exists
            if 'download_files' in resp and len(resp['download_files']) > 0:
                for file in resp['download_files']:
                    name = '{} {}'.format(chapter['number'], sanitize_filename(file['file_name']))
                    link = file['download_url']
                    download_aria(link, name, section_dir)

            # Save content html is exists
            html_description = resp['download'].get('html_description')
            if html_description is not None:
                name = '{} {}.html'.format(chapter['number'], chapter['name'])
                with open(os.path.join(section_dir, name), 'w', encoding='utf8') as file:
                    file.write(html_description)

        except Exception as e:
            logger.exception('Could not get download type: {}'.format(e))


    def parse_sections(self, thinkific_object: dict):
        course_dir = os.path.join(DOWNLOAD_DIR, thinkific_object['name'])
        if not os.path.exists(course_dir):
            os.mkdir(course_dir)

        for index, section in enumerate(thinkific_object['sections']):
            if index >= 0:
                section_name = '{} {}'.format(section['number'], section['name'])
                section_dir = os.path.join(course_dir, section_name)
                if not os.path.exists(section_dir):
                    os.mkdir(section_dir)
                logger.info('============== Processing section {} of {:02d} =============='.format(section['number'], thinkific_object['len_sections']))

                for chapter in section['chapters']:
                    logger.info('> Processing chapter {} of {:02d}...'.format(chapter['number'], section['len_chapters']))
                    if chapter['contentable_type'] == 'HtmlItem':
                        self._extract_html(chapter, section_dir)
                    elif chapter['contentable_type'] == 'Lesson':
                        self._extract_lesson(chapter, section_dir)
                    elif chapter['contentable_type'] == 'Download':
                        self._extract_download(chapter, section_dir)


def main():

    url = 'https://cursos.devtalles.com/courses/PWA'
    # url = 'https://academia.holamundo.io/courses/ultimate-python'

    logger.info('> Starting...')
    thinkific = Thinkific(url)

    logger.info('> Fetching course info...')
    course = thinkific._fetch_course()

    logger.info('> Generating thinkific object...')
    thinkific_object, types = thinkific._thinkific_object(course)
    logger.info('> Types: {}'.format(types))

    course_title  = thinkific_object.get('name')
    section_count = thinkific_object.get('len_sections')
    chapter_count = thinkific_object.get('len_chapters')
    logger.info('> Course   : {}'.format(course_title))
    logger.info('> Sections : {}'.format(section_count))
    logger.info('> Lectures : {}'.format(chapter_count))

    logger.info('> Starting download...')
    thinkific.parse_sections(thinkific_object)


if __name__ == '__main__':
    pre_run()
    main()
