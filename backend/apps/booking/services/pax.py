from datetime import date

from apps.pricing.constants import ADULT_MIN_AGE, CHILD_MIN_AGE, PassengerType


def age_at(dob: date, reference: date) -> int:
    years = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        years -= 1
    return years


def pax_type_for(dob: date, reference: date) -> str:
    """Passenger type is a fact about the date of birth, not a choice the booker makes.

    Evaluated at the *return* date: a child who turns 12 mid-journey is an adult for the whole
    booking, because the return coupon must be ticketed at the adult fare.
    """
    age = age_at(dob, reference)
    if age >= ADULT_MIN_AGE:
        return PassengerType.ADULT
    if age >= CHILD_MIN_AGE:
        return PassengerType.CHILD
    return PassengerType.INFANT
