import browser_cookie3
import subprocess
import m3u8
import re


from bs4 import BeautifulSoup
from constants import LESSON_URL, DOWNLOAD_URL, VIDEOPROXY_URL
from pathvalidate import sanitize_filename
from thinkific import Thinkific, MethodsRequests
from pathlib import Path


cookies = browser_cookie3.chrome()
quality = 1080
concurrent_downloads = 10


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


def _extract_media_id(resp: dict):
    if 'videos' in resp and resp['videos'] is not None:
        identifier = resp['videos'][0]['identifier']
        videoproxy = VIDEOPROXY_URL.format(identifier)
        try:
            resp = MethodsRequests._get(videoproxy)
            soup = BeautifulSoup(resp.text, 'html.parser')
            pattern = re.compile(r'embed/medias/(.*?)(\.jsonp|$)')
            for script_tag in soup.find_all('script', src=True):
                url_jsonp = script_tag['src']
                match = pattern.search(url_jsonp)
                if match:
                    media_id = match.group(1)
                    return media_id
        except Exception as e:
            print(f'Error: {e}')
            return None
    return None


def _extract_m3u8(contentable_id: int, media_id: str):
    _temp = []
    try:
        _url = f'https://fast.wistia.com/embed/medias/{media_id}.m3u8'
        resp = MethodsRequests._get(_url).text
        seen = set()


        base_url = f'https://embed-cloudfront.wistia.com'

        m3u8_object = m3u8.loads(resp)
        playlist = m3u8_object.playlists
        for item in playlist:
            resolution = item.stream_info.resolution
            width, height = resolution

            if height in seen:
                continue

            playlist_path = Path('m3u8', f'{contentable_id}_{width}x{height}.m3u8')

            with open(playlist_path, 'w') as f:
                resp = MethodsRequests._get(item.uri).text
                resp = resp.replace('/deliveries/', f'{base_url}/deliveries/')
                f.write(resp)

            seen.add(height)
            _temp.append(
                {
                    'height': height,
                    'width': width,
                    'download_url': playlist_path.resolve().as_uri(),
                }
            )
    except Exception as e:
        print(f'Error extract_m3u8: {e}')
    return _temp


def extract_lesson(contentable_id: int):
    _url = LESSON_URL.format('cursos.devtalles.com', contentable_id)
    print(f'Fetchin video from: {_url}')
    resp = MethodsRequests._get(_url, cookies).json()

    print(f'Extracting media id')
    media_id = _extract_media_id(resp)
    if media_id is None: return

    print(f'Extracting m3u8')
    sources = _extract_m3u8(contentable_id, media_id)
    sources = sorted(sources, key=lambda x: int(x.get('height')), reverse=True)

    if sources:
        source = sources[0]
        if isinstance(quality, int):
            source = min(sources, key=lambda x: abs(int(x.get('height')) - quality))
            url = source.get('download_url')
            print("      ====== Selected quality: ", source.get("height"))
            out = Path('m3u8', f'{contentable_id}_{source.get("width")}x{source.get("height")}.mp4')
            cmd = [
                'yt-dlp',
                '--enable-file-urls',
                '--force-generic-extractor',
                '--concurrent-fragments',
                f'{concurrent_downloads}',
                '--downloader',
                'aria2c',
                '-o',
                f'{out}',
                f'{url}'
            ]
            process = subprocess.Popen(cmd)
            ret_code = process.wait()
            if ret_code == 0:
                print(f'[{contentable_id}] Downloaded successfully')


uids = [
    18644077,
    18644079,
    18644082,
    18644115,
    18644118
]


for number, uid in enumerate(uids, 1):
    extract_lesson(uid)