"""Прототип блоку «Мій розклад» для Moodle УУ — на розкладі групи ЗІПЗ-26-1.

Ідея для університету: розклад зберігається як дані (таблиця / YAML), а не як
Word-файл, і Moodle показує кожному студенту його пари за його групою.
Тут джерело — uni-ipz/timetable/schedule.yaml (переведений з офіційного docx
«1_курс_ІПЗ-26-1, КН-26-1 ЗІПЗ-26-1 Розклад»), курси Moodle — з uni-ipz/data/uni.db.

    python build.py   →   rozklad.html (поруч)

Zoom-посилання й коди доступу в сторінку НЕ потрапляють: прототип показують
стороннім людям, а це посилання реальних пар.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
UNI = HERE.parent / "uni-ipz"
SCHEDULE = UNI / "timetable" / "schedule.yaml"
DB = UNI / "data" / "uni.db"
TEMPLATE = HERE / "template.html"
OUT = HERE / "rozklad.html"

GROUP = "ЗІПЗ-26-1"
MOODLE = "https://vo.uu.edu.ua"


def _iso(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def main() -> None:
    cfg = yaml.safe_load(SCHEDULE.read_text(encoding="utf-8"))

    with sqlite3.connect(DB) as con:
        courses = {
            name: int(cid)
            for name, cid in con.execute(
                "select name, moodle_course_id from disciplines where moodle_course_id is not null"
            )
        }
        # Найближче незакрите завдання з реальним терміном — лише такі показуємо.
        due = {}
        for name, title, due_at in con.execute(
            "select d.name, a.title, a.due_at from assignments a "
            "join disciplines d on d.id = a.discipline_id "
            "where a.due_at is not null and a.status not in ('submitted', 'graded', 'done') "
            "order by a.due_at"
        ):
            due.setdefault(name, {"title": title, "due": due_at})

    lessons = []
    for day, items in (cfg.get("weekly") or {}).items():
        for item in items or []:
            name = item["discipline"]
            lessons.append({
                "day": day,
                "pair": int(item["pair"]),
                "week": item.get("week"),            # None — щотижня
                "discipline": name,
                "kind": item.get("kind", ""),
                "teacher": item.get("teacher") or "",
                "online": bool(item.get("zoom") or item.get("access")),
                "course": courses.get(name),
                "task": due.get(name),
            })

    data = {
        "group": GROUP,
        "moodle": MOODLE,
        "semester": {k: _iso(v) for k, v in cfg["semester"].items()},
        "bells": {str(k): v for k, v in cfg["bells"].items()},
        "weeks": [
            {"start": _iso(p["start"]), "end": _iso(p["end"]), "week": p["week"]}
            for p in cfg.get("week_periods") or []
        ],
        "lessons": lessons,
        "source": "1_курс_ІПЗ-26-1, КН-26-1 ЗІПЗ-26-1 Розклад.docx",
    }

    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False)
    )
    OUT.write_text(html, encoding="utf-8")
    # GitHub Pages віддає index.html як є — йому потрібен повний документ із кодуванням.
    # rozklad.html лишається фрагментом для артефакту claude.ai (той сам додає каркас).
    (HERE / "index.html").write_text(
        '<!doctype html>\n<html lang="uk">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "</head>\n<body>\n" + html + "\n</body>\n</html>\n",
        encoding="utf-8",
    )
    print(f"{OUT.name}: {len(lessons)} пар у сітці, курсів з посиланням {sum(1 for l in lessons if l['course'])}")


if __name__ == "__main__":
    main()
