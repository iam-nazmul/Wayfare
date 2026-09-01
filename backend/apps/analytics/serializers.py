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
