from django.db import models


class DisruptionType(models.TextChoices):
    CANCELLATION = "CANCELLATION", "Cancellation"
    DELAY = "DELAY", "Significant delay"
    DIVERSION = "DIVERSION", "Diversion"
    SCHEDULE_CHANGE = "SCHEDULE_CHANGE", "Schedule change"


class RebookOptionStatus(models.TextChoices):
    OFFERED = "OFFERED", "Offered"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"
    EXPIRED = "EXPIRED", "Expired"


#: A delay only becomes a disruption past this — anything shorter is ordinary operations and
#: would flood passengers with notices they cannot act on (SPEC.md §6.5).
DELAY_THRESHOLD_MINUTES = 120

#: Three is what a passenger can choose between without a wall of options.
MAX_REBOOK_OPTIONS = 3

#: How long a rebooking offer stands. It holds no seats, so it is re-checked on acceptance.
REBOOK_OPTION_TTL_HOURS = 72

#: Search order for alternatives: same day first, then either side of it.
REBOOK_DAY_OFFSETS = (0, 1, -1)
