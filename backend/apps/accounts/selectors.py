from django.db.models import QuerySet

from .models import Traveller, User


def travellers_for(actor: User) -> QuerySet[Traveller]:
    """Every read is ownership-filtered here, never in the view (CLAUDE.md invariant 8)."""
    return Traveller.objects.filter(user=actor).order_by("-is_primary", "last_name")


def traveller_or_404(actor: User, public_id) -> Traveller:
    return travellers_for(actor).get(public_id=public_id)
