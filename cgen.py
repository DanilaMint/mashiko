"""Скрипт генерации кода на C"""

_CODE_HEADER = """
#pragma once
"""


class CGenerator:
    code: str

    def __init__(self):
        self.code = ""
