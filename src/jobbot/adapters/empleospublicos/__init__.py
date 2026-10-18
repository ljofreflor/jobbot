"""Empleos Públicos (Chile) — search via Servicio Civil open data; ficha fixture-first."""

from jobbot.adapters.empleospublicos.jobs import (
    EmpleosPublicosJobSource,
    canonical_ficha_url,
    job_from_ficha_html,
    jobs_from_search_payload,
)
from jobbot.adapters.empleospublicos.open_data import (
    OpenDataError,
    job_from_convocatoria,
    parse_open_data_csv,
    search_convocatorias,
)

__all__ = [
    "EmpleosPublicosJobSource",
    "OpenDataError",
    "canonical_ficha_url",
    "job_from_ficha_html",
    "job_from_convocatoria",
    "jobs_from_search_payload",
    "parse_open_data_csv",
    "search_convocatorias",
]
