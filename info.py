import browser_cookie3
import subprocess

from bs4 import BeautifulSoup
from constants import LESSON_URL, DOWNLOAD_URL
from pathvalidate import sanitize_filename
from thinkific import Thinkific, MethodsRequests


cookies = browser_cookie3.chrome()


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


# Esta funcion extrae los external links de cada leccion no importa si es un video o un html
def extract_lesson(number: int, contentable_id: int):
    number = str(number).zfill(2)
    _url = LESSON_URL.format('cursos.devtalles.com', contentable_id)
    resp = MethodsRequests._get(_url, cookies).json()

    # Verificamos si la lesson tiene external links
    html_text = resp['lesson']['html_text']
    if html_text is not None:
        soup = BeautifulSoup(html_text, 'html.parser')
        for a in soup.find_all('a', href=True):
            name = a.text.strip() if a.text else 'No name'
            href = a['href']

            url_name = '{} {}.url'.format(number, sanitize_filename(name))
            url_body = f'[InternetShortcut]\nURL={href}'
            with open(f'downloads/{url_name}', 'w') as f:
                f.write(url_body)

    # Verificamos si la lesson tiene material descargable
    download_files = resp['download_files']
    if len(download_files) > 0:
        for file in download_files:
            name = '{} {}'.format(number, sanitize_filename(file['file_name']))
            link = file['download_url']
            download_aria(link, name, 'downloads')


def extract_downloads(number: int, contentable_id: int):
    number = str(number).zfill(2)
    _url = DOWNLOAD_URL.format('cursos.devtalles.com', contentable_id)
    resp = MethodsRequests._get(_url, cookies).json()

    html_description = resp['download']['html_description']
    if html_description is not None:
        name = '{} {}.html'.format(number, 'test-download')
        with open(f'downloads/{name}', 'w', encoding='utf8') as file:
            file.write(html_description)

    download_files = resp['download_files']
    if len(download_files) > 0:
        for file in download_files:
            name = sanitize_filename(file['file_name'])
            link = file['download_url']
            download_aria(link, name, 'downloads')


uids = [
    1082834,
    1089819,
    1091011,
    1090960
]


for number, uid in enumerate(uids, 1):
    # extract_lesson(number, uid)
    extract_downloads(number, uid)