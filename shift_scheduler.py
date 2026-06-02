#!/usr/bin/env python3
"""Generate a gender-aware fixed-shift roster using persisted month history."""

from __future__ import annotations

import argparse
import calendar
import csv
import itertools
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


SHIFTS = ("Morning", "Evening", "Night")
OFF_PATTERNS = (
    (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 0),
)
ROOT = Path(__file__).resolve().parent
DEFAULT_EMPLOYEES_PATH = ROOT / "data" / "employees.csv"
DEFAULT_HISTORY_PATH = ROOT / "data" / "shift_history.csv"


@dataclass(frozen=True)
class Employee:
    employee_id: str
    name: str
    level: str
    gender: str
    weekly_offs: tuple[int, int]


def load_employees(path: Path = DEFAULT_EMPLOYEES_PATH) -> list[Employee]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    employees = [
        Employee(
            row["Employee ID"],
            row["Name"],
            row["Level"],
            row["Gender"],
            (
                list(calendar.day_name).index(row["Off Day 1"]),
                list(calendar.day_name).index(row["Off Day 2"]),
            ),
        )
        for row in rows
    ]
    if not employees:
        raise ValueError("Employee dataset is empty.")
    return employees


def load_history(path: Path = DEFAULT_HISTORY_PATH) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def save_history(
    history: list[dict[str, str]],
    employees: list[Employee],
    fixed_shifts: dict[str, str],
    year: int,
    month: int,
    path: Path = DEFAULT_HISTORY_PATH,
) -> None:
    month_key = f"{year:04d}-{month:02d}"
    retained = [row for row in history if row["Month"] != month_key]
    retained.extend(
        {
            "Month": month_key,
            "Employee ID": employee.employee_id,
            "Name": employee.name,
            "Shift": fixed_shifts[employee.employee_id],
        }
        for employee in employees
    )
    retained.sort(key=lambda row: (row["Month"], row["Employee ID"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=["Month", "Employee ID", "Name", "Shift"]
        )
        writer.writeheader()
        writer.writerows(retained)


def previous_months(year: int, month: int, count: int = 2) -> set[str]:
    result = set()
    for _ in range(count):
        month -= 1
        if month == 0:
            year -= 1
            month = 12
        result.add(f"{year:04d}-{month:02d}")
    return result


def night_cooldown_ids(
    history: list[dict[str, str]], year: int, month: int
) -> set[str]:
    blocked_months = previous_months(year, month)
    return {
        row["Employee ID"]
        for row in history
        if row["Month"] in blocked_months and row["Shift"] == "Night"
    }


def calendar_weeks(year: int, month: int) -> list[list[int]]:
    weeks: list[list[int]] = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        if not weeks or date(year, month, day).weekday() == 0:
            weeks.append([])
        weeks[-1].append(day)
    return weeks


def choose_fixed_shifts(
    employees: list[Employee],
    history: list[dict[str, str]],
    year: int,
    month: int,
    rng: random.Random,
) -> dict[str, str]:
    if len(employees) < 9:
        raise ValueError("At least 9 employees are required for 3 members per shift.")
    if sum(employee.level == "Senior" for employee in employees) < 3:
        raise ValueError("At least 3 senior developers are required.")

    blocked = night_cooldown_ids(history, year, month)
    eligible_night = [employee for employee in employees if employee.employee_id not in blocked]
    night_size = max(3, len(employees) // 3)
    night_options = []
    for option in itertools.combinations(eligible_night, night_size):
        seniors = sum(employee.level == "Senior" for employee in option)
        females = sum(employee.gender == "Female" for employee in option)
        if seniors >= 3 and (females == 0 or females >= 4):
            night_options.append(option)
    if not night_options:
        raise ValueError(
            "Night cooldown leaves no valid Night team. A Night team needs at least "
            "3 members, 3 seniors, and either 0 or at least 4 female employees."
        )
    rng.shuffle(night_options)
    night_team = min(
        night_options,
        key=lambda option: (
            sum(employee.gender == "Female" for employee in option),
            abs(sum(employee.level == "Senior" for employee in option) - 3),
        ),
    )
    assignments = {employee.employee_id: "Night" for employee in night_team}
    remaining = [employee for employee in employees if employee.employee_id not in assignments]
    rng.shuffle(remaining)
    remaining.sort(key=lambda employee: employee.level != "Senior")
    shift_counts = Counter({"Morning": 0, "Evening": 0})
    senior_counts = Counter({"Morning": 0, "Evening": 0})
    for employee in remaining:
        shift = min(
            ("Morning", "Evening"),
            key=lambda item: (
                senior_counts[item] if employee.level == "Senior" else shift_counts[item],
                shift_counts[item],
            ),
        )
        assignments[employee.employee_id] = shift
        shift_counts[shift] += 1
        if employee.level == "Senior":
            senior_counts[shift] += 1
    return assignments


def choose_weekly_offs(
    employees: list[Employee],
    fixed_shifts: dict[str, str],
    rng: random.Random,
) -> dict[str, tuple[int, int]]:
    return {employee.employee_id: employee.weekly_offs for employee in employees}


def build_schedule(
    employees: list[Employee],
    history: list[dict[str, str]],
    year: int,
    month: int,
    seed: int = 42,
    attempts: int = 3000,
    leave: dict | None = None,
    leaves: list[dict] | None = None,
) -> tuple[dict[int, dict[str, list[str]]], dict[str, str]]:
    leave_days = set()
    all_leaves = []
    if leaves:
        all_leaves.extend(leaves)
    if leave:
        all_leaves.append(leave)

    for lv in all_leaves:
        if lv and lv.get("employee_id"):
            emp_id = lv["employee_id"]
            start_val = lv.get("start_date")
            end_val = lv.get("end_date")
            if isinstance(start_val, str):
                start_val = date.fromisoformat(start_val)
            if isinstance(end_val, str):
                end_val = date.fromisoformat(end_val)
            for day in range(1, calendar.monthrange(year, month)[1] + 1):
                d = date(year, month, day)
                if start_val <= d <= end_val:
                    leave_days.add((emp_id, day))

    for attempt in range(attempts):
        rng = random.Random(seed + attempt)
        fixed_shifts = choose_fixed_shifts(employees, history, year, month, rng)
        weekly_offs = choose_weekly_offs(employees, fixed_shifts, rng)
        schedule = {
            day: {
                shift: [
                    employee.employee_id
                    for employee in employees
                    if fixed_shifts[employee.employee_id] == shift
                    and date(year, month, day).weekday() not in weekly_offs[employee.employee_id]
                    and (employee.employee_id, day) not in leave_days
                ]
                for shift in SHIFTS
            }
            for day in range(1, calendar.monthrange(year, month)[1] + 1)
        }
        if not validate_schedule(schedule, employees, history, year, month, fixed_shifts, leave_days):
            return schedule, fixed_shifts
    raise RuntimeError(
        f"Could not create a valid schedule after {attempts} attempts. "
        "The current dataset and recent Night history may be too restrictive."
    )


def validate_schedule(
    schedule: dict[int, dict[str, list[str]]],
    employees: list[Employee],
    history: list[dict[str, str]],
    year: int,
    month: int,
    fixed_shifts: dict[str, str],
    leave_days: set[tuple[str, int]] | None = None,
) -> list[str]:
    errors: list[str] = []
    by_id = {employee.employee_id: employee for employee in employees}
    worked_days: dict[str, set[int]] = defaultdict(set)
    blocked_nights = night_cooldown_ids(history, year, month)

    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        roster = schedule.get(day)
        if roster is None:
            errors.append(f"Day {day}: missing roster.")
            continue
        assigned_today: set[str] = set()
        for shift in SHIFTS:
            ids = roster.get(shift, [])
            if len(ids) < 3:
                errors.append(f"Day {day}: {shift} shift has fewer than 3 members.")
            if not any(by_id[employee_id].level == "Senior" for employee_id in ids):
                errors.append(f"Day {day}: {shift} shift has no senior developer.")
            if shift == "Night":
                females = sum(by_id[employee_id].gender == "Female" for employee_id in ids)
                if females == 1:
                    errors.append(f"Day {day}: a female Night worker must have female company.")
            for employee_id in ids:
                if employee_id in assigned_today:
                    errors.append(f"Day {day}: {employee_id} is assigned more than once.")
                if fixed_shifts[employee_id] != shift:
                    errors.append(f"{employee_id}: monthly fixed shift changed.")
                assigned_today.add(employee_id)
                worked_days[employee_id].add(day)

    for employee in employees:
        employee_id = employee.employee_id
        if fixed_shifts[employee_id] == "Night" and employee_id in blocked_nights:
            errors.append(f"{employee.name}: Night shift cooldown is still active.")
        streak = 0
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            streak = streak + 1 if day in worked_days[employee_id] else 0
            if streak > 5:
                errors.append(f"Day {day}: {employee.name} worked more than 5 consecutive days.")
        for week in calendar_weeks(year, month):
            # Check if this employee has leave on any day in this week
            has_leave_this_week = False
            if leave_days:
                for day in week:
                    if (employee_id, day) in leave_days:
                        has_leave_this_week = True
                        break

            expected = sum(
                day not in worked_days[employee_id] for day in week
            )
            if len(week) == 7:
                if has_leave_this_week:
                    if expected < 2:
                        errors.append(f"{employee.name}: expected at least 2 off-days in week of day {week[0]}.")
                else:
                    if expected != 2:
                        errors.append(f"{employee.name}: expected 2 off-days in week of day {week[0]}.")
    return errors


def names_for(ids: list[str], employees: Iterable[Employee]) -> list[str]:
    by_id = {employee.employee_id: employee.name for employee in employees}
    return [by_id[employee_id] for employee_id in ids]


def write_schedule_csv(
    output: Path,
    schedule: dict[int, dict[str, list[str]]],
    employees: list[Employee],
    year: int,
    month: int,
) -> None:
    with output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Date", "Day", "Shift", "Employees", "Staff count"])
        for day, roster in schedule.items():
            roster_date = date(year, month, day)
            for shift in SHIFTS:
                names = names_for(roster[shift], employees)
                writer.writerow(
                    [roster_date.isoformat(), roster_date.strftime("%A"), shift, ", ".join(names), len(names)]
                )


def write_employee_summary(
    output: Path,
    schedule: dict[int, dict[str, list[str]]],
    employees: list[Employee],
    fixed_shifts: dict[str, str],
) -> None:
    worked = Counter(
        employee_id for roster in schedule.values() for ids in roster.values() for employee_id in ids
    )
    with output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Employee ID", "Employee", "Level", "Gender", "Fixed shift", "Workdays", "Days off"])
        for employee in employees:
            writer.writerow(
                [
                    employee.employee_id, employee.name, employee.level, employee.gender,
                    fixed_shifts[employee.employee_id], worked[employee.employee_id],
                    len(schedule) - worked[employee.employee_id],
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--month", type=int, default=date.today().month)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--employees-data", type=Path, default=DEFAULT_EMPLOYEES_PATH)
    parser.add_argument("--history-data", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--leave-employee", type=str, default=None, help="Employee ID on leave")
    parser.add_argument("--leave-start", type=str, default=None, help="Leave start date (YYYY-MM-DD)")
    parser.add_argument("--leave-end", type=str, default=None, help="Leave end date (YYYY-MM-DD)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    employees = load_employees(args.employees_data)
    history = load_history(args.history_data)
    
    leave = None
    if args.leave_employee:
        leave = {
            "employee_id": args.leave_employee,
            "start_date": args.leave_start,
            "end_date": args.leave_end,
        }

    schedule, fixed_shifts = build_schedule(
        employees, history, args.year, args.month, args.seed, leave=leave
    )
    save_history(history, employees, fixed_shifts, args.year, args.month, args.history_data)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = args.output_dir / f"shift_schedule_{args.year}_{args.month:02d}.csv"
    summary_path = args.output_dir / f"employee_summary_{args.year}_{args.month:02d}.csv"
    write_schedule_csv(schedule_path, schedule, employees, args.year, args.month)
    write_employee_summary(summary_path, schedule, employees, fixed_shifts)
    print(f"Created a valid {len(schedule)}-day fixed-shift schedule.")
    print(f"Schedule: {schedule_path}")
    print(f"Employee summary: {summary_path}")


if __name__ == "__main__":
    main()
