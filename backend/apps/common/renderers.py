from rest_framework.renderers import BaseRenderer


class CSVRenderer(BaseRenderer):
    """Satisfies content negotiation for ``Accept: text/csv``.

    It renders nothing: the views that offer CSV return a ``StreamingHttpResponse`` so a large
    export is never assembled in memory. Without a renderer advertising the media type, DRF
    refuses the request with 406 before the view is ever called.
    """

    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data if isinstance(data, bytes | str) else ""
