"""
Generates synthetic PII values that are format-realistic but never
collide with real-world identifier ranges where a known-safe range exists
(e.g., SSN area numbers reserved by SSA for testing).

CRITICAL: everything here is fabricated. Nothing in this module reads,
scrapes, or derives from any real individual's data.
"""
import random


def gen_ssn(rng: random.Random) -> str:
    # SSA reserves area numbers 900-999 as invalid/unassignable — using
    # this range guarantees no collision with any real SSN ever issued.
    area = rng.randint(900, 999)
    group = rng.randint(1, 99)
    serial = rng.randint(1, 9999)
    return f"{area:03d}-{group:02d}-{serial:04d}"


def _luhn_checksum(digits: list[int]) -> int:
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10


def gen_card_number(rng: random.Random) -> str:
    # Uses the 4111... test-BIN prefix pattern (widely recognized as a
    # non-real test range), then computes a genuine Luhn check digit so
    # deterministic-detector testing (Section 4's Luhn requirement) works.
    prefix = [4, 1, 1, 1] + [rng.randint(0, 9) for _ in range(11)]
    check = (10 - _luhn_checksum(prefix + [0])) % 10
    digits = prefix + [check]
    s = "".join(map(str, digits))
    return f"{s[0:4]}-{s[4:8]}-{s[8:12]}-{s[12:16]}"


def gen_phone(rng: random.Random) -> str:
    # Area code 555 is reserved for fictional use in North America.
    return f"555-{rng.randint(200,999):03d}-{rng.randint(1000,9999):04d}"


def gen_dob(rng: random.Random):
    from datetime import date
    year = rng.randint(1945, 2005)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return date(year, month, day)


def gen_driver_license(rng: random.Random, state_abbr: str) -> str:
    return f"{state_abbr}{rng.randint(1000000, 9999999)}"


def gen_passport(rng: random.Random) -> str:
    letter = rng.choice("ABCDEFGH")
    return f"{letter}{rng.randint(10000000, 99999999)}"


def gen_email(first: str, last: str, rng: random.Random) -> str:
    domain = rng.choice(["mailbox.example", "webmail.example", "inboxnet.example"])
    style = rng.choice([f"{first}.{last}", f"{first[0]}{last}", f"{first}{last[0]}"])
    return f"{style.lower()}@{domain}"


def gen_login_credential(email: str, rng: random.Random) -> str:
    return f"{email}:pw_hash_{rng.randint(100000,999999)}"
