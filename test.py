import os


def file_already_downloaded(file_path):
    aria2_file = file_path + '.aria2'
    return os.path.exists(file_path) and not os.path.exists(aria2_file)


file = 'videos/test.mp4'


if not file_already_downloaded(file):
    print('Empezando descarga...')
else:
    print('El video ya está descargado, omitiendo...')