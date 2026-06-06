"""
TeleCRM Backend — apps/core/pagination.py

Standard pagination classes for DRF API responses.
All list endpoints return:

  {
    "count": 150,
    "total_pages": 6,
    "current_page": 1,
    "page_size": 25,
    "next": "https://..../api/v1/leads/?page=2",
    "previous": null,
    "results": [...]
  }
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Default pagination for all list API endpoints.
    Supports ?page= and ?page_size= query params.
    """

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "total_pages": {"type": "integer"},
                "current_page": {"type": "integer"},
                "page_size": {"type": "integer"},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results": schema,
            },
        }


class LargeResultsSetPagination(PageNumberPagination):
    """
    For endpoints that need larger page sizes (e.g., lead export preview).
    """

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


class SmallResultsSetPagination(PageNumberPagination):
    """
    For endpoints with small result sets (e.g., dropdown lists).
    """

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50
    page_query_param = "page"

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
