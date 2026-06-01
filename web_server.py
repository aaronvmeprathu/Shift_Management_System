#!/usr/bin/env python3
"""Serve a local web UI for the worker shift scheduler."""

from __future__ import annotations

import argparse
import json
import mimetypes
from collections import Counter
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from shift_scheduler import (
    SHIFTS,
    build_schedule,
    load_employees,
    load_history,
    names_for,
    save_history,
    write_employee_summary,
    write_schedule_csv,
)


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "output" / "ui"
EMPLOYEES_PATH = ROOT / "data" / "employees.csv"
HISTORY_PATH = ROOT / "data" / "shift_history.csv"


def employee_summary(
    schedule: dict[int, dict[str, list[str]]],
    employees: list,
    fixed_shifts: dict[str, str],
) -> list[dict]:
    counts = {employee.employee_id: Counter() for employee in employees}
    for roster in schedule.values():
        for shift, employee_ids in roster.items():
            for employee_id in employee_ids:
                counts[employee_id][shift] += 1
    return [
        {
            "employeeId": employee.employee_id,
            "name": employee.name,
            "level": employee.level,
            "gender": employee.gender,
            "fixedShift": fixed_shifts[employee.employee_id],
            "workdays": sum(counts[employee.employee_id].values()),
            "daysOff": len(schedule) - sum(counts[employee.employee_id].values()),
        }
        for employee in employees
    ]


def schedule_rows(
    schedule: dict[int, dict[str, list[str]]], employees: list, year: int, month: int
) -> list[dict]:
    rows = []
    for day, roster in schedule.items():
        roster_date = date(year, month, day)
        rows.append(
            {
                "date": roster_date.isoformat(),
                "day": roster_date.strftime("%A"),
                "shifts": [
                    {
                        "name": shift,
                        "employees": names_for(roster[shift], employees),
                        "count": len(roster[shift]),
                    }
                    for shift in SHIFTS
                ],
            }
        )
    return rows


def int_setting(payload: dict, name: str, default: int, minimum: int, maximum: int) -> int:
    value = int(payload.get(name, default))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name.capitalize()} must be between {minimum} and {maximum}.")
    return value


def generate_roster(payload: dict) -> dict:
    current_year = date.today().year
    year = int_setting(payload, "year", current_year, 2000, 2100)
    month = int_setting(payload, "month", date.today().month, 1, 12)
    seed = int_setting(payload, "seed", 42, 0, 1_000_000)

    employees = load_employees(EMPLOYEES_PATH)
    history = load_history(HISTORY_PATH)
    schedule, fixed_shifts = build_schedule(employees, history, year, month, seed)
    save_history(history, employees, fixed_shifts, year, month, HISTORY_PATH)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    schedule_name = f"shift_schedule_{year}_{month:02d}.csv"
    summary_name = f"employee_summary_{year}_{month:02d}.csv"
    write_schedule_csv(OUTPUT_DIR / schedule_name, schedule, employees, year, month)
    write_employee_summary(OUTPUT_DIR / summary_name, schedule, employees, fixed_shifts)

    assignments = sum(
        len(names) for roster in schedule.values() for names in roster.values()
    )
    seniors = sum(employee.level == "Senior" for employee in employees)
    juniors = sum(employee.level == "Junior" for employee in employees)
    return {
        "monthLabel": date(year, month, 1).strftime("%B %Y"),
        "metrics": {
            "employees": len(employees),
            "seniors": seniors,
            "juniors": juniors,
            "weeklyOffs": 2,
            "operatingDays": len(schedule),
            "assignments": assignments,
        },
        "schedule": schedule_rows(schedule, employees, year, month),
        "employees": employee_summary(schedule, employees, fixed_shifts),
        "downloads": {
            "schedule": f"/downloads/{schedule_name}",
            "summary": f"/downloads/{summary_name}",
            "employees": "/employees.csv",
        },
    }


class ShiftManagementHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/":
            self.send_file(WEB_DIR / "index.html")
            return
        if path.startswith("/static/"):
            self.send_file(WEB_DIR / Path(path).name)
            return
        if path.startswith("/downloads/"):
            self.send_file(OUTPUT_DIR / Path(path).name, download=True)
            return
        if path == "/employees.csv":
            self.send_file(EMPLOYEES_PATH, download=True)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Page not found")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length) or b"{}")
            self.send_json(generate_roster(payload))
        except (ValueError, RuntimeError) as error:
            self.send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            self.send_json({"error": "Request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)

    def send_file(self, path: Path, download: bool = False) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ShiftManagementHandler)
    print(f"Shift Management UI: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
