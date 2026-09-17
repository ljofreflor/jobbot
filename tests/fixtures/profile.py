"""Minimal valid profile fixture as dict."""

from __future__ import annotations

from typing import Any


def non_data_profile_dict() -> dict[str, Any]:
    """A profile outside data science: JobBot must serve this candidate too."""
    return {
        "personal": {
            "name": "Marta Soto Vera",
            "headline": "Ingeniera Geofísica | Coordinadora de Proyectos",
            "city": "Santiago",
            "country": "Chile",
            "email": "marta.soto@example.com",
        },
        "summary": "Ingeniera de proyectos en minería, con equipos en terreno.",
        "specialties": ["Gestión de Proyectos", "Geofísica"],
        "experience": [
            {
                "id": "geodetec-coord",
                "company": "Geodetec Ingeniería",
                "title": "Coordinadora de Proyectos",
                "location": "Santiago, Chile",
                "start_date": "2022-07",
                "end_date": "2023-11",
                "current": False,
                "description": "Proyectos multidisciplinarios para clientes mineros.",
                "achievements": [
                    {
                        "id": "geodetec-scrum",
                        "text": "Implementé metodologías ágiles en equipos de siete personas.",
                        "tags": ["scrum"],
                        "metrics": {},
                    }
                ],
            }
        ],
        "education": [
            {
                "id": "ucv-geofisica",
                "institution": "Universidad del Litoral",
                "degree": "Ingeniera Geofísica",
                "start_date": "2000-09",
                "end_date": "2007-10",
            }
        ],
        "skills": {
            "engineering": [
                "Scrum",
                "Gestión de Proyectos",
                "Liderazgo",
                "AutoCAD",
                "Comunicación Efectiva",
            ]
        },
        "publications": [],
    }


def nurse_profile_dict() -> dict[str, Any]:
    """Clinical profile: no technology stack, no English-language vocabulary."""
    return {
        "personal": {
            "name": "Rocío Paredes Lagos",
            "headline": "Enfermera Clínica | Unidad de Paciente Crítico",
            "city": "Valparaíso",
            "country": "Chile",
            "email": "rocio.paredes@example.com",
        },
        "summary": "Enfermera con ocho años en unidades de paciente crítico adulto.",
        "specialties": ["Paciente Crítico", "Educación al Paciente"],
        "experience": [
            {
                "id": "hospital-uci",
                "company": "Hospital del Puerto",
                "title": "Enfermera Clínica UCI",
                "location": "Valparaíso, Chile",
                "start_date": "2019-03",
                "current": True,
                "description": "Cuidado de pacientes conectados a ventilación mecánica.",
                "achievements": [
                    {
                        "id": "uci-protocolo",
                        "text": "Implementé el protocolo de prevención de neumonía asociada "
                        "a ventilación mecánica en doce camas.",
                        "tags": ["ventilación mecánica"],
                        "metrics": {"camas": 12},
                    },
                    {
                        "id": "uci-induccion",
                        "text": "Capacité a seis enfermeras nuevas en registro clínico "
                        "y administración de fármacos vasoactivos.",
                        "tags": ["registro clínico"],
                        "metrics": {},
                    },
                ],
            }
        ],
        "education": [
            {
                "id": "upv-enfermeria",
                "institution": "Universidad de Valparaíso",
                "degree": "Enfermera Universitaria",
                "start_date": "2011-03",
                "end_date": "2015-12",
            }
        ],
        "skills": {
            "clinical": [
                "Ventilación Mecánica",
                "Reanimación Cardiopulmonar",
                "Registro Clínico",
                "Fármacos Vasoactivos",
                "Educación al Paciente",
            ]
        },
        "publications": [],
    }


def journalist_profile_dict() -> dict[str, Any]:
    """Newsroom profile: its tools are not the tools of a data stack."""
    return {
        "personal": {
            "name": "Tomás Riquelme Soto",
            "headline": "Periodista | Editor de Contenidos",
            "city": "Concepción",
            "country": "Chile",
            "email": "tomas.riquelme@example.com",
        },
        "summary": "Periodista con seis años en prensa regional y edición digital.",
        "specialties": ["Periodismo de Investigación", "Edición Digital"],
        "experience": [
            {
                "id": "diario-editor",
                "company": "Diario del Biobío",
                "title": "Editor de Contenidos Digitales",
                "location": "Concepción, Chile",
                "start_date": "2021-01",
                "current": True,
                "description": "Edición de portada digital y coordinación de corresponsales.",
                "achievements": [
                    {
                        "id": "diario-seo",
                        "text": "Reescribí titulares con criterios de SEO y subí el tráfico "
                        "orgánico de la portada.",
                        "tags": ["SEO"],
                        "metrics": {},
                    }
                ],
            }
        ],
        "education": [
            {
                "id": "udec-periodismo",
                "institution": "Universidad de Concepción",
                "degree": "Periodista",
                "start_date": "2012-03",
                "end_date": "2016-12",
            }
        ],
        "skills": {
            "editorial": [
                "Redacción Periodística",
                "Edición Digital",
                "SEO",
                "WordPress",
                "Entrevista en Terreno",
            ]
        },
        "publications": [],
    }


def sample_profile_dict() -> dict[str, Any]:
    return {
        "personal": {
            "name": "Ana Ejemplo",
            "headline": "Senior Data Scientist",
            "city": "Santiago",
            "country": "Chile",
            "email": "ana@example.com",
            "linkedin": "https://www.linkedin.com/in/ana",
            "github": "https://github.com/ana",
        },
        "summary": "Data scientist focused on causal inference.",
        "specialties": ["Machine Learning", "Causal Inference"],
        "experience": [
            {
                "id": "meli-ds",
                "company": "Mercado Libre",
                "title": "Senior Data Scientist",
                "location": "Remote",
                "start_date": "2022-04",
                "end_date": "2025-05",
                "current": False,
                "description": "Customer analytics & credit risk.",
                "achievements": [
                    {
                        "id": "meli-share-of-wallet",
                        "text": "Share of Wallet for 6M sellers.",
                        "tags": ["machine-learning", "fintech"],
                        "metrics": {"sellers": 6000000, "potential_usd": 460000000},
                    }
                ],
            }
        ],
        "education": [
            {
                "id": "uchile-ms",
                "institution": "Universidad de Chile",
                "degree": "Magíster en Estadística",
                "start_date": "2017-03",
                "end_date": "2019-12",
            }
        ],
        "skills": {
            "programming": ["Python", "SQL"],
            "machine_learning": ["XGBoost"],
            "cloud": ["GCP"],
            "statistics": ["Causal Inference"],
            "engineering": ["MLOps"],
        },
        "publications": [
            {
                "id": "pub-1",
                "title": "Marketplace interference",
                "journal": "Working paper",
                "year": 2021,
                "status": "preprint",
            }
        ],
    }
