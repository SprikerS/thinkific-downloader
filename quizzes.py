import base64
import browser_cookie3
import json
import re
import requests

from bs4 import BeautifulSoup
from constants import QUIZ_URL
from thinkific import MethodsRequests


cookies = browser_cookie3.firefox()


def decode_base64(base64_str: str):
    message_bytes   = base64.b64decode(base64_str)
    message_decoded = message_bytes.decode('utf-8')
    message_string  = re.sub(r'\d', '', message_decoded)
    return message_string


class ChoiceIterator:
    def __init__(self, choices, question_id):
        self.choices = choices
        self.question_id = question_id
        self.index = 0

    def __iter__(self):
        return self

    def __next__(self):
        while self.index < len(self.choices):
            choice = self.choices[self.index]
            self.index += 1
            if choice['question_id'] == self.question_id:
                ans = decode_base64(choice['credited'])
                txt = BeautifulSoup(choice['text'], 'html.parser').text
                return ans, txt
        raise StopIteration


def extract_quizzes(number:int, uid: int):
    _url = QUIZ_URL.format('cursos.devtalles.com', uid)
    resp = MethodsRequests._get(_url, cookies).json()

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

        # choices_iterator = ChoiceIterator(resp['choices'], question['id'])
        # for ans, txt in choices_iterator:
        #     file_contents += f"<br>{'[•]' if ans == 'true' else '[ ]'} {txt}"

        for choice in resp['choices']:
            if choice['question_id'] == question['id']:
                answer = decode_base64(choice['credited'])
                string = BeautifulSoup(choice['text'], 'html.parser').text
                file_contents += f"<br>{'[•]' if answer == 'true' else '[ ]'} {string}"

        file_contents += '<br><br>'

    with open(f'{number:02d} quizzes.html', 'w', encoding='utf8') as file:
        file.write(file_contents)

uids = [
    2434861,
    2434864,
    2434874
]


for number, uid in enumerate(uids, 1):
    # extract_lesson(number, uid)
    extract_quizzes(number, uid)