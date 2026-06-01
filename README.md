# Worker Shift Management

This command-line program generates a seven-day monthly roster for 13 senior
developers and 7 junior developers by default.

It enforces these rules:

- The company operates every calendar day, including Saturdays and Sundays.
- Every employee receives 2 off-days in each full Monday-to-Sunday week.
- Partial calendar weeks receive up to 2 off-days while retaining one workday.
- Every employee remains on one fixed shift throughout the month.
- There are three staffed shifts every day: Morning, Evening, and Night.
- Every shift includes at least 3 employees and at least one senior developer.
- An employee can work at most one shift per day.
- Fixed shifts prevent Night-to-Morning transitions between workdays.
- If female employees work the Night shift, at least 2 female employees are
  present together.
- An employee works at most 5 consecutive days before an off-day.
- After working the Night shift for a month, an employee cannot receive Night
  shift again for the next 2 months.

The scheduler maximizes useful coverage by scheduling every available employee
workday and distributing staff across the three shifts as evenly as the rules
allow. It also writes an employee summary so the allocation is easy to review.

## Run

```powershell
python .\shift_scheduler.py --year 2026 --month 6
```

The generated CSV files are written to `output\`.

Employee identity, level, gender, and recurring weekly off-days are loaded from
`data\employees.csv`.
Generated monthly fixed shifts are persisted in `data\shift_history.csv` and
used when planning future months:

```powershell
python .\shift_scheduler.py --year 2026 --month 7 --seed 42
```

The `--seed` value makes a roster reproducible. Change it to generate another
valid variation.

## Web UI

Start the local dashboard:

```powershell
python .\web_server.py
```

Open `http://127.0.0.1:8000` in a browser. The UI can generate seven-day rosters,
preview the calendar and fixed-shift team summary, and download the roster,
summary, and employee dataset CSV files.
