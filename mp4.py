import browser_cookie3
import json
import re
import subprocess


from bs4 import BeautifulSoup
from constants import LESSON_URL, DOWNLOAD_URL, VIDEOPROXY_URL
from pathvalidate import sanitize_filename
from thinkific import Thinkific, MethodsRequests


cookies = browser_cookie3.chrome()
quality = None


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
    ret_code = process.wait()
    if ret_code != 0:
        raise Exception('Return code from the downloader was non-0 (error)')
    return ret_code


def _get_video_proxy(resp: dict):
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
            raise Exception(f'Error in get_video_proxy: {e}')
    return None


def _get_jsonp_data(url_jsonp: str):
    try:
        resp  = MethodsRequests._get(url_jsonp).text
        jsonp = re.search(r'window\[\'wistiajsonp-[^\'\]]+\'] = (.+?);', resp)
        if jsonp:
            jsonp_str = jsonp.group(1)
            json_data = json.loads(jsonp_str)
            return json_data
    except Exception as e:
        raise Exception(f'Error in get_jsonp_data: {e}')


def _get_qualities(jsonp: list):
    selected_assets = []
    unique_heights  = set()

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


def _processing_download(resp: dict):
    try:
        proxy = _get_video_proxy(resp)
        if not proxy:
            return

        jsonp = _get_jsonp_data(proxy)
        if not jsonp:
            return
        qualities = _get_qualities(jsonp)
        if not qualities:
            return

        return qualities
    except Exception as e:
        print (f'{e}')


def extract_lesson(uid: int):
    _url = LESSON_URL.format('cursos.devtalles.com', uid)
    try:
        resp = MethodsRequests._get(_url, cookies).json()
        assets = _processing_download(resp)
        assets = sorted(assets, key=lambda x: int(x.get('height')), reverse=True)
        if assets:
            asset = assets[0]
            if isinstance(quality, int):
                asset = min(assets, key=lambda x: abs(int(x.get('height')) - quality))
            print(assets)
        else:
            print ('No se encontraron assets')
    except Exception as e:
        print (f'{e}')


uids = [
    14535329
]


for uid in uids:
    extract_lesson(uid)