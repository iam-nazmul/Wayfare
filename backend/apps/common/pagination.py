from collections import OrderedDict

from rest_framework.pagination import CursorPagination
from rest_framework.response import Response


class WayfareCursorPagination(CursorPagination):
    """Cursor pagination everywhere — offsets skip rows when the table takes concurrent inserts."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    cursor_query_param = "cursor"
    ordering = "-created_at"

    def get_paginated_response(self, data) -> Response:
        return Response(
            OrderedDict(
                [
                    ("results", data),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                ]
            )
        )

    def get_paginated_response_schema(self, schema: dict) -> dict:
        return {
            "type": "object",
            "required": ["results"],
            "properties": {
                "results": schema,
                "next": {"type": "string", "nullable": True, "format": "uri"},
                "previous": {"type": "string", "nullable": True, "format": "uri"},
            },
        }
