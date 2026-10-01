"""
Builds the synthetic population for the breach corpus (Design Section 3).
Deterministic (seeded) so the whole corpus is reproducible.
"""
import csv
import random
from pathlib import Path

from pii_utils import (
    gen_ssn, gen_card_number, gen_phone, gen_dob, gen_driver_license,
    gen_passport, gen_email, gen_login_credential,
)

RNG = random.Random(2026)

FIRST_NAMES = [
    "James","Mary","Robert","Patricia","John","Jennifer","Michael","Linda","William","Elizabeth",
    "David","Barbara","Richard","Susan","Joseph","Jessica","Thomas","Sarah","Charles","Karen",
    "Christopher","Nancy","Daniel","Lisa","Matthew","Betty","Anthony","Margaret","Mark","Sandra",
    "Donald","Ashley","Steven","Kimberly","Andrew","Emily","Paul","Donna","Joshua","Michelle",
    "Kenneth","Dorothy","Kevin","Carol","Brian","Amanda","George","Melissa","Edward","Deborah",
    "Ronald","Stephanie","Timothy","Rebecca","Jason","Sharon","Jeffrey","Laura","Ryan","Cynthia",
    "Jacob","Kathleen","Gary","Amy","Nicholas","Shirley","Eric","Angela","Jonathan","Helen",
    "Stephen","Anna","Larry","Brenda","Justin","Pamela","Scott","Nicole","Brandon","Emma",
    "Benjamin","Samantha","Samuel","Katherine","Frank","Christine","Gregory","Debra","Raymond","Rachel",
    "Alexander","Catherine","Patrick","Carolyn","Jack","Janet","Dennis","Ruth","Jerry","Maria",
]

LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez",
    "Hernandez","Lopez","Gonzalez","Wilson","Anderson","Thomas","Taylor","Moore","Jackson","Martin",
    "Lee","Perez","Thompson","White","Harris","Sanchez","Clark","Ramirez","Lewis","Robinson",
    "Walker","Young","Allen","King","Wright","Scott","Torres","Nguyen","Hill","Flores",
    "Green","Adams","Nelson","Baker","Hall","Rivera","Campbell","Mitchell","Carter","Roberts",
]

STREETS = ["Maple St","Oak Ave","Cedar Ln","Elm St","Park Rd","Sunset Blvd","River Dr","Hillcrest Ave","Birch Ct","Lakeview Dr"]
CITIES = [("Springfield","IL"),("Columbus","OH"),("Franklin","TN"),("Georgetown","TX"),("Salem","OR"),
          ("Madison","WI"),("Arlington","VA"),("Bristol","CT"),("Riverside","CA"),("Fairview","NJ")]

NICKNAME_MAP = {
    "Robert":"Bob","Richard":"Rick","William":"Bill","Michael":"Mike","James":"Jim",
    "Patricia":"Pat","Elizabeth":"Liz","Jennifer":"Jen","Margaret":"Peggy","Susan":"Sue",
    "Kenneth":"Ken","Anthony":"Tony","Christopher":"Chris","Matthew":"Matt","Jonathan":"Jon",
    "Timothy":"Tim","Deborah":"Debbie","Katherine":"Kathy","Stephanie":"Steph","Nicholas":"Nick",
}

MEDICAL_NOTES = [
    "history of hypertension, managed with medication",
    "seasonal allergy treatment on file",
    "physical therapy follow-up scheduled",
    "annual wellness screening completed",
    "prescription refill for maintenance medication",
]


def make_person(pid: int, force_first=None, force_last=None):
    first = force_first or RNG.choice(FIRST_NAMES)
    last = force_last or RNG.choice(LAST_NAMES)
    street_num = RNG.randint(100, 9999)
    street = RNG.choice(STREETS)
    city, state = RNG.choice(CITIES)
    zip_code = RNG.randint(10000, 99999)
    dob = gen_dob(RNG)
    email = gen_email(first, last, RNG)

    has_dl = RNG.random() < 0.55
    has_passport = RNG.random() < 0.25
    has_financial = RNG.random() < 0.45
    has_medical = RNG.random() < 0.3
    has_login = RNG.random() < 0.35

    person = {
        "person_id": f"P{pid:04d}",
        "first_name": first,
        "last_name": last,
        "canonical_name": f"{first} {last}",
        "dob": dob.isoformat(),
        "ssn": gen_ssn(RNG),
        "address": f"{street_num} {street}, {city}, {state} {zip_code}",
        "phone": gen_phone(RNG),
        "email": email,
        "has_driver_license": has_dl,
        "driver_license": gen_driver_license(RNG, state) if has_dl else "",
        "has_passport": has_passport,
        "passport": gen_passport(RNG) if has_passport else "",
        "has_financial": has_financial,
        "card_number": gen_card_number(RNG) if has_financial else "",
        "has_medical": has_medical,
        "medical_note": RNG.choice(MEDICAL_NOTES) if has_medical else "",
        "has_login": has_login,
    }
    person["login_credential"] = gen_login_credential(email, RNG) if person["has_login"] else ""
    return person


def build_population(n_people=155, n_with_variants=30, n_collision_pairs=8):
    people = [make_person(i) for i in range(1, n_people + 1)]

    # --- Name variants: pick a subset, generate 1-2 alternate forms each ---
    variant_rows = []
    variant_candidates = RNG.sample(people, n_with_variants)
    for person in variant_candidates:
        first, last = person["first_name"], person["last_name"]
        variants = []

        if first in NICKNAME_MAP:
            variants.append((NICKNAME_MAP[first] + " " + last, "nickname"))
        variants.append((f"{first[0]}. {last}", "initials"))
        if RNG.random() < 0.4:
            # simple transposition typo — retry with a different position
            # if the swap happens to hit two identical letters (no-op)
            chars = list(last)
            if len(chars) > 3:
                for _ in range(5):
                    i = RNG.randint(1, len(chars) - 2)
                    if chars[i] != chars[i+1]:
                        chars[i], chars[i+1] = chars[i+1], chars[i]
                        break
            misspelled = "".join(chars)
            if misspelled != last:
                variants.append((f"{first} {misspelled}", "misspelling"))
        if RNG.random() < 0.5:
            variants.append((f"{last}, {first}", "name_order"))

        for text, vtype in variants[:2]:  # cap at 2 per person to keep it manageable
            variant_rows.append({"person_id": person["person_id"], "canonical_name": person["canonical_name"],
                                  "variant_text": text, "variant_type": vtype})

    # --- Shared-name collisions: separate people, identical full names ---
    collision_rows = []
    next_pid = n_people + 1
    for _ in range(n_collision_pairs):
        first = RNG.choice(FIRST_NAMES)
        last = RNG.choice(LAST_NAMES)
        p_a = make_person(next_pid, force_first=first, force_last=last)
        next_pid += 1
        p_b = make_person(next_pid, force_first=first, force_last=last)
        next_pid += 1
        people.append(p_a)
        people.append(p_b)
        collision_rows.append({
            "shared_name": f"{first} {last}", "person_id_a": p_a["person_id"], "person_id_b": p_b["person_id"],
            "should_merge": False, "distinguishing_fields": "dob, ssn, address all differ",
        })

    return people, variant_rows, collision_rows


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    people, variants, collisions = build_population()

    out = Path(__file__).parent.parent / "manifest"
    out.mkdir(exist_ok=True)

    write_csv(out / "individuals.csv", people, list(people[0].keys()))
    write_csv(out / "name_variants.csv", variants, list(variants[0].keys()))
    write_csv(out / "name_collisions.csv", collisions, list(collisions[0].keys()))

    print(f"Generated {len(people)} people ({len(people) - 2*8} unique + {2*8} in collision pairs)")
    print(f"Generated {len(variants)} name variants across 30 people")
    print(f"Generated {len(collisions)} shared-name collision pairs")
