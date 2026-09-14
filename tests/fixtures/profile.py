"""Minimal valid profile fixture as dict."""

from __future__ import annotations

from typing import Any


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
