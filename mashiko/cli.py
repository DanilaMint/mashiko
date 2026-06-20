import argparse

# 1. Создаем парсер
arguments = argparse.ArgumentParser(
    description="Компилятор / Анализатор исходного кода"
)
# 2. Позиционный аргумент: путь к файлу (обязательный, идет первым)
# Если вы хотите сделать его необязательным, добавьте nargs='?'
arguments.add_argument("file_path", type=str, help="Путь к исходному файлу")
# 3. Флаг --version (выводит версию и сразу завершает работу скрипта)
arguments.add_argument(
    "--version",
    action="version",
    version="%(prog)s 1.0.0",
    help="Вывести версию программы и выйти",
)
# 4. Флаг --log с ограниченным выбором значений (choices)
arguments.add_argument(
    "--log",
    type=str,
    choices=["quiet", "standart", "detail"],
    default="standart",
    help="Уровень вывода информации в консоль (по умолчанию: standart)",
)
# 5. Флаг -t / --tree (обычный переключатель True/False)
arguments.add_argument(
    "-t",
    "--tree",
    action="store_true",
    help="Нарисовать AST (дерево абстрактного синтаксиса) в консоли",
)
# 6. Флаг -o / --output со значением по умолчанию
arguments.add_argument(
    "-o",
    "--output",
    type=str,
    default="result.c",
    help="Путь к файлу для сохранения результата (по умолчанию: result.c)",
)
# 7. Флаг -m / --mangle (переключатель True/False)
arguments.add_argument(
    "-m",
    "--mangle",
    action="store_true",
    help="Сохранять оригинальные имена структур, функций и т.д.",
)
