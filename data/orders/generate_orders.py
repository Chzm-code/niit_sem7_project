"""Generate synthetic laundry order lifecycle events for LuckyCode (CSV, local time UTC+8)."""
import argparse
import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
import random
import tempfile


FIELDS = (
    "event_id", "order_id", "site_id", "machine_id", "event_type",
    "event_time", "queued_at", "program", "paid_amount",
)
# Weights correspond to the twelve one-hour intervals starting at 08:00.
ARRIVAL_WEIGHTS = (5, 5, 6, 8, 10, 7, 5, 5, 7, 11, 15, 16)
PROGRAMS = {
    "QUICK": (20, 25, "3.00"),
    "STANDARD": (28, 36, "5.00"),
    "DEEP": (37, 45, "7.50"),
}
EVENT_ORDER = {"COMPLETED": 0, "QUEUED": 1, "CANCELLED": 2, "STARTED": 3}


def timestamp(value):
    return value.isoformat(sep=" ", timespec="milliseconds")


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return number


def generate(start_date, days, orders_per_day, seed):
    rng = random.Random(seed)
    sites = ("S01", "S02")
    first_open = datetime.combine(start_date, time(8))
    free_at = {site: [first_open] * 4 for site in sites}
    events = []

    for day_index in range(days):
        opening = first_open + timedelta(days=day_index)
        hours = rng.choices(range(12), weights=ARRIVAL_WEIGHTS, k=orders_per_day)
        arrivals = sorted(opening + timedelta(hours=h, seconds=rng.randrange(3600))
                          for h in hours)
        for index, queued in enumerate(arrivals, start=1):
            site = rng.choices(sites, weights=(6, 4))[0]
            program = rng.choices(list(PROGRAMS), weights=(4, 5, 1))[0]
            order = f"O{queued:%Y%m%d}-{index:05d}"
            base = dict(order_id=order, site_id=site, queued_at=timestamp(queued),
                        program=program)

            def add_event(kind, when, machine="", amount="0.00"):
                events.append(dict(base, event_id=f"{order}-{kind}", event_type=kind,
                                   event_time=timestamp(when), machine_id=machine,
                                   paid_amount=amount))

            add_event("QUEUED", queued)
            availability = free_at[site]
            slot = min(range(len(availability)), key=availability.__getitem__)
            start = max(availability[slot], queued)
            deadline = queued + timedelta(minutes=rng.randint(3, 24))
            if start > deadline:
                add_event("CANCELLED", deadline)
                continue

            minimum, maximum, price = PROGRAMS[program]
            finish = start + timedelta(minutes=rng.randint(minimum, maximum))
            machine = f"{site}-M{slot + 1:02d}"
            add_event("STARTED", start, machine)
            add_event("COMPLETED", finish, machine, price)
            availability[slot] = finish

    events.sort(key=lambda e: (e["event_time"], EVENT_ORDER[e["event_type"]], e["order_id"]))
    return events


def save_csv(events, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after the whole file has been written and closed (also on Windows).
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(events)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 11, 16))
    parser.add_argument("--days", type=positive_int, default=7)
    parser.add_argument("--orders-per-day", type=positive_int, default=144)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("orders.csv"))
    args = parser.parse_args()
    events = generate(args.start_date, args.days, args.orders_per_day, args.seed)
    save_csv(events, args.output)
    total = args.days * args.orders_per_day
    completed = sum(e["event_type"] == "COMPLETED" for e in events)
    print(f"start={args.start_date} days={args.days} seed={args.seed} orders={total} "
          f"completed={completed} cancelled={total - completed} events={len(events)}")
    print(args.output.resolve())


if __name__ == "__main__":
    main()

