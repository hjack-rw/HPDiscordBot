"""CLI to convert human-readable birthday/binary values to the base-10 ints the DB stores, and back.

Usage:
    python scripts/convert_db_values.py date <day> <month> [year]      -> birthday int (+ birth_year int if year given)
    python scripts/convert_db_values.py date-int <int> [birth_year]    -> dd.mm[.yyyy]
    python scripts/convert_db_values.py bin <binary_string>            -> int
    python scripts/convert_db_values.py bin-int <int> [width]          -> binary string (width defaults to 16, portkeys.multiple_choice)
"""

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.engine.conversions import convert_date_to_int, convert_int_to_date, is_binary, convert_int_to_binary, convert_binary_to_int, convert_year_to_db, convert_db_to_year


def date_to_db(day: int, month: int, year: int | None = None):
    birthday_int = convert_date_to_int(datetime(year=2000, month=month, day=day))
    birth_year_int = convert_year_to_db(year) if year is not None else None
    return birthday_int, birth_year_int


def db_to_date(birthday_int: int, birth_year_int: int | None = None):
    date = convert_int_to_date(birthday_int)
    if birth_year_int is not None:
        # date.replace(year=...) would raise on Feb 29 (birthday_int is always anchored to the
        # leap year 2000) paired with a non-leap birth_year_int - format the parts directly instead
        return f"{date.day:02d}.{date.month:02d}.{convert_db_to_year(birth_year_int)}"
    return date.strftime("%d.%m")


def binary_to_db(binary_string: str):
    if not is_binary(binary_string):
        raise ValueError(f"'{binary_string}' is not a binary string!")
    return convert_binary_to_int(binary_string)


def db_to_binary(value: int, width: int = 16):
    return convert_int_to_binary(value, width)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_date = sub.add_parser("date", help="day month [year] -> db int(s)")
    p_date.add_argument("day", type=int)
    p_date.add_argument("month", type=int)
    p_date.add_argument("year", type=int, nargs="?")

    p_date_int = sub.add_parser("date-int", help="db int [birth_year int] -> dd.mm[.yyyy]")
    p_date_int.add_argument("birthday_int", type=int)
    p_date_int.add_argument("birth_year_int", type=int, nargs="?")

    p_bin = sub.add_parser("bin", help="binary string -> db int")
    p_bin.add_argument("binary_string")

    p_bin_int = sub.add_parser("bin-int", help="db int [width] -> binary string")
    p_bin_int.add_argument("value", type=int)
    p_bin_int.add_argument("width", type=int, nargs="?", default=16)

    args = parser.parse_args()

    try:
        if args.mode == "date":
            birthday_int, birth_year_int = date_to_db(args.day, args.month, args.year)
            print(f"birthday={birthday_int}" + (f"  year={birth_year_int}" if birth_year_int is not None else ""))

        elif args.mode == "date-int":
            print(db_to_date(args.birthday_int, args.birth_year_int))

        elif args.mode == "bin":
            print(binary_to_db(args.binary_string))

        elif args.mode == "bin-int":
            print(db_to_binary(args.value, args.width))

    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
