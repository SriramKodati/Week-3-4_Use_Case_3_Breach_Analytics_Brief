"""
Renders a person's PII into realistic "messy" text — the way it actually
appears in real documents: buried in a sentence, in a signature block, in
a table row — never neatly labeled "SSN: ...".
"""
import random

RNG = random.Random(7)

PROSE_TEMPLATES = [
    "Per our records, {name} (DOB {dob}) contacted the office regarding an account update. "
    "The address on file is {address}, and the best contact number is {phone}.",
    "{name} submitted a request on behalf of the household. We verified identity using the "
    "information provided, including a callback to {phone} and confirmation of the mailing "
    "address at {address}.",
    "Following up on the case for {name}: date of birth {dob}, current address {address}. "
    "Please reach out at {phone} or {email} if additional documentation is required.",
    "Enclosed please find the requested update for {name}. Our system shows a residential "
    "address of {address} and a primary phone number of {phone}.",
]

SIGNATURE_TEMPLATES = [
    "Best regards,\n{name}\n{phone}\n{email}",
    "Thank you,\n{name}\nDirect: {phone}\n{email}",
    "{name}\n{email} | {phone}",
]

FALSE_POSITIVE_ORDER_NOTE = "Order confirmation #{fake_ssn_shaped} has shipped to the address on file."

TEMPLATE_PLACEHOLDER_LINE = "SSN: XXX-XX-XXXX  |  DOB: MM/DD/YYYY  |  Account #: [ACCOUNT NUMBER]"

TEST_RECORD_LINE = "TEST RECORD — John Doe, 000-00-0000, DO NOT USE IN PRODUCTION"


def prose_paragraph(person: dict) -> str:
    t = RNG.choice(PROSE_TEMPLATES)
    return t.format(name=person["canonical_name"], dob=person["dob"],
                     address=person["address"], phone=person["phone"], email=person["email"])


def signature_block(person: dict) -> str:
    t = RNG.choice(SIGNATURE_TEMPLATES)
    return t.format(name=person["canonical_name"], phone=person["phone"], email=person["email"])


def medical_note_line(person: dict) -> str:
    return f"Clinical note for {person['canonical_name']} (DOB {person['dob']}): {person['medical_note']}."


def financial_note_line(person: dict) -> str:
    return (f"Payment method on file for {person['canonical_name']}: card ending "
            f"{person['card_number'][-4:]} (full: {person['card_number']}).")


def login_note_line(person: dict) -> str:
    return f"Support ticket — user {person['canonical_name']} requested a credential reset. On file: {person['login_credential']}"


def partial_identifier_ssn_only(person: dict) -> str:
    """Plants just the SSN with no name nearby — the 'partial identifier' edge case."""
    return f"Case reference SSN {person['ssn']} flagged for review. Assigned case worker: intake team."


def partial_identifier_name_only(person: dict) -> str:
    """The matching document: same person, name only, no SSN — must be linked to the above."""
    return f"{person['canonical_name']} called to check on the status of their case."


def last4_reference(person: dict) -> str:
    return f"Verification on file for account holder: last four of SSN {person['ssn'][-4:]}, name {person['canonical_name']}."


def employee_signature_negative(fake_employee_name: str, fake_employee_phone: str, fake_employee_email: str) -> str:
    """An internal staff signature — should NOT be flagged as a breach subject."""
    return f"Regards,\n{fake_employee_name}\nDataFactZ Client Services\n{fake_employee_phone} | {fake_employee_email}"


def driver_license_note_line(person: dict) -> str:
    return f"ID verification for {person['canonical_name']}: driver's license {person['driver_license']} on file."


def passport_note_line(person: dict) -> str:
    return f"Travel authorization request from {person['canonical_name']}, passport {person['passport']}."
