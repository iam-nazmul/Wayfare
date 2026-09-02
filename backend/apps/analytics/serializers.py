from rest_framework import serializers

EVENT_NAMES = [
    "page_view", "search_submitted", "search_results_rendered", "filter_applied",
    "sort_changed", "offer_viewed", "offer_selected", "pax_details_started",
    "pax_details_completed", "ancillary_added", "ancillary_removed", "seat_selected",
    "payment_started", "payment_failed", "booking_confirmed", "checkin_started",
    "checkin_completed", "error_shown", "api_latency",
]


class CollectEventSerializer(serializers.Serializer):
    event_name = serializers.ChoiceField(choices=EVENT_NAMES)
    event_time = serializers.DateTimeField(required=False)
    session_id = serializers.CharField(max_length=64)
    anon_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    page_path = serializers.CharField(max_length=512, required=False, allow_blank=True)
    referrer = serializers.CharField(max_length=512, required=False, allow_blank=True)
    props = serializers.DictField(required=False, default=dict)


class CollectBatchSerializer(serializers.Serializer):
    events = serializers.ListField(child=CollectEventSerializer(), max_length=100, min_length=1)


#: A wider window than this is a data export, not a report, and will time out on ClickHouse.
MAX_REPORT_SPAN_DAYS = 400
DEFAULT_REPORT_SPAN_DAYS = 30


class ReportWindowSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs: dict) -> dict:
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.now().date()
        attrs["date_to"] = attrs.get("date_to") or today
        attrs["date_from"] = attrs.get("date_from") or attrs["date_to"] - timedelta(
            days=DEFAULT_REPORT_SPAN_DAYS
        )

        if attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError(
                {"date_from": "date_from cannot be after date_to."}
            )
        if (attrs["date_to"] - attrs["date_from"]).days > MAX_REPORT_SPAN_DAYS:
            raise serializers.ValidationError(
                {"date_from": f"A report spans at most {MAX_REPORT_SPAN_DAYS} days."}
            )
        return attrs


class ReportResponseSerializer(serializers.Serializer):
    """Schema-only: reports are shaped by their query, so rows stay untyped."""

    report = serializers.CharField()
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    columns = serializers.ListField(child=serializers.CharField())
    rows = serializers.ListField(child=serializers.ListField())
    row_count = serializers.IntegerField()
