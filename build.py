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


def themed(path: Path) -> str:
    """Шаблон зі стилем vo.uu.edu.ua (theme.css) і набором іконок (icons.svg)."""
    return (
        path.read_text(encoding="utf-8")
        .replace("/*__THEME__*/", (HERE / "theme.css").read_text(encoding="utf-8"))
        .replace("<!--__ICONS__-->", (HERE / "icons.svg").read_text(encoding="utf-8"))
    )


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

    html = themed(TEMPLATE).replace(
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

    # Кабінет методиста. Офіційний документ один на три групи; у стартових даних
    # заповнена лише ЗІПЗ-26-1 — дві інші методист заповнює імпортом docx на показі.
    seed = {
        "config": {
            "semester": data["semester"],
            "bells": data["bells"],
            "weeks": data["weeks"],
            "courses": courses,
            "groups": [
                {"id": "ZIPZ-26-1", "name": "ЗІПЗ-26-1"},
                {"id": "IPZ-26-1", "name": "ІПЗ-26-1"},
                {"id": "KN-26-1", "name": "КН-26-1"},
            ],
        },
        "groups": {
            "ZIPZ-26-1": {
                "name": "ЗІПЗ-26-1",
                "lessons": [
                    {k: v for k, v in dict(l, id=f"s{i:02d}", changedAt=0).items() if k != "task"}
                    for i, l in enumerate(lessons)
                ],
                "updatedAt": 0,
            }
        },
        "changes": [],
    }
    (HERE / "seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
    admin = themed(HERE / "admin_template.html").replace(
        "/*__SEED__*/null", json.dumps(seed, ensure_ascii=False)
    )
    (HERE / "kabinet.html").write_text(admin, encoding="utf-8")
    (HERE / "admin.html").write_text(
        '<!doctype html>\n<html lang="uk">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "</head>\n<body>\n" + admin + "\n</body>\n</html>\n",
        encoding="utf-8",
    )
    print(f"kabinet.html / admin.html: {len(seed['groups']['ZIPZ-26-1']['lessons'])} пар у стартових даних")

    n = write_ics(data, HERE / ICS_NAME)
    print(f"{ICS_NAME}: {n} занять на семестр")


# --- iCal для штатного «Імпорт календаря» у Moodle -----------------------------
#
# Moodle 3.8 вміє підписатися на календар за URL і опитувати його щогодини
# (Календар → Управління підпискою). Підписка в службовому курсі — і пари
# з'являються в календарі та «Найближчих подіях» усієї групи без жодного плагіна.
# UID стабільний (група + дата + пара), тому при оновленні Moodle замінює подію,
# а не дублює. Час — у UTC: так його однаково читає і Moodle, і будь-який календар.
# Zoom-посилань і кодів тут теж немає — файл публічний.

ICS_NAME = "rozklad-ZIPZ-26-1.ics"
DAY_INDEX = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "нд": 6}


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def _fold(line: str) -> str:
    """RFC 5545: рядок не довший за 75 байтів, продовження — з пробілу."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > 74:
            out.append(cur.decode("utf-8"))
            cur = b" " + b
        else:
            cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def write_ics(data: dict, path: Path) -> int:
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    kyiv = ZoneInfo("Europe/Kyiv")
    week_of = {}
    for p in data["weeks"]:
        d, end = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        while d <= end:
            week_of[d] = p["week"]
            d += timedelta(days=1)

    def utc(d: date, hm: str) -> str:
        local = datetime.combine(d, datetime.strptime(hm, "%H:%M").time(), kyiv)
        return local.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//uu-rozklad prototype//UK",
        "CALSCALE:GREGORIAN", _fold(f"X-WR-CALNAME:Розклад {data['group']}"),
    ]
    count = 0
    for d in sorted(week_of):
        for l in data["lessons"]:
            if DAY_INDEX.get(l["day"]) != d.weekday() or (l["week"] and l["week"] != week_of[d]):
                continue
            start, end = data["bells"][str(l["pair"])].split("-")
            desc = [_ics_text(x) for x in (l["kind"], l["teacher"]) if x]
            if l["course"]:
                desc.append(f"Курс у Moodle: {data['moodle']}/course/view.php?id={l['course']}")
            lines += [
                "BEGIN:VEVENT",
                f"UID:{data['group']}-{d:%Y%m%d}-p{l['pair']}@uu-rozklad",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{utc(d, start)}",
                f"DTEND:{utc(d, end)}",
                _fold(f"SUMMARY:{l['pair']} пара — {_ics_text(l['discipline'])}"),
                _fold("DESCRIPTION:" + "\\n".join(desc)),
                "END:VEVENT",
            ]
            count += 1
    lines.append("END:VCALENDAR")
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return count


if __name__ == "__main__":
    main()
