"""Regression locks on real LinkedIn posts the candidate actually asked JobBot to apply to.

Synthetic fixtures under ``tests/fixtures/linkedin_*.txt`` isolate one mechanism each.
These ones are the posts themselves: adding support for a new shape must not break an
older one. Short links are resolved from the sibling ``.urls.json`` captured at the
same time, so the suite stays offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import jobbot.adapters.linkedin.sweep as sweep_mod
from jobbot.adapters.linkedin.sweep import (
    parse_posts_fixture,
    post_offers_wanted_country,
    post_to_job,
    post_to_jobs,
)
from jobbot.jobs.geo import detect_country
from jobbot.portals.detect import AtsKind
from jobbot.portals.email_apply import first_apply_email

_REAL = Path("tests/fixtures/linkedin_real")


def _load_real_post(name: str, monkeypatch: object) -> object:
    text = (_REAL / f"{name}.txt").read_text(encoding="utf-8")
    url_map_path = _REAL / f"{name}.urls.json"
    if url_map_path.exists():
        captured = json.loads(url_map_path.read_text(encoding="utf-8"))

        def fake_expand(urls: list[str]) -> dict[str, str]:
            return {url: captured.get(url, url) for url in urls}

        monkeypatch.setattr(sweep_mod, "expand_url_map", fake_expand)

    # Offline stand-in for sniff_ats: read a sibling .html when the host alone is mute.
    html_path = _REAL / f"{name}.html"
    if html_path.exists():
        from jobbot.portals.detect import detect_ats, detect_ats_in_html

        page = html_path.read_text(encoding="utf-8")

        def fake_sniff(url: str, *, timeout: float = 10.0) -> AtsKind:
            kind = detect_ats(url)
            if kind != AtsKind.UNKNOWN:
                return kind
            kind, _ = detect_ats_in_html(page)
            return kind

        monkeypatch.setattr(sweep_mod, "sniff_ats", fake_sniff)
    return parse_posts_fixture(text)[0]


def test_real_softserve_post_splits_into_five_appliable_jobs(monkeypatch: object) -> None:
    """https://lnkd.in/p/dRgw4_BS — five labelled SoftServe roles + a CV mailbox."""
    post = _load_real_post("softserve_ai_ml_hiring", monkeypatch)

    assert [v.title for v in post.vacancies] == [  # type: ignore[attr-defined]
        "Lead Agentic AI Consultant",
        "Lead Data Scientist",
        "Senior Data Scientist – Generative AI",
        "Lead ML Engineer",
        "Senior Computer Vision Engineer",
    ]
    assert {v.ats_kind for v in post.vacancies} == {AtsKind.UNKNOWN}  # type: ignore[attr-defined]
    assert all("softserveinc.com" in v.url for v in post.vacancies)  # type: ignore[attr-defined]
    assert first_apply_email(post.text) == "lmore@softserveinc.com"  # type: ignore[attr-defined]
    assert post_offers_wanted_country(post.text, wanted=["CL"]) is True  # type: ignore[attr-defined]

    jobs = post_to_jobs(post, countries=["CL"])  # type: ignore[arg-type]
    assert len(jobs) == 5
    assert {j.company for j in jobs} == {"SoftServe"}
    assert all(j.ats_url and "softserveinc.com" in j.ats_url for j in jobs)
    assert all(j.url == j.ats_url for j in jobs)


def test_real_latam_roundup_keeps_only_the_chile_role(monkeypatch: object) -> None:
    """https://lnkd.in/p/dgRU3YAM — weekly roundup; country belongs to each role."""
    post = _load_real_post("latam_ai_roundup", monkeypatch)

    assert [v.country for v in post.vacancies] == ["CO", "PE", "AR", "CL"]  # type: ignore[attr-defined]
    assert [v.ats_kind for v in post.vacancies] == [  # type: ignore[attr-defined]
        AtsKind.REMOSHIFT,
        AtsKind.GREENHOUSE,
        AtsKind.BREEZY,
        AtsKind.JOBTOME,
    ]
    assert post_offers_wanted_country(post.text, wanted=["CL"]) is True  # type: ignore[attr-defined]

    chile = post_to_jobs(post, countries=["CL"])  # type: ignore[arg-type]
    assert [j.title for j in chile] == ["GenAI & Agentic AI Full-Stack Engineer – Chile"]
    assert chile[0].ats_kind == "jobtome"
    assert "jobtome.com" in (chile[0].ats_url or "")

    every = post_to_jobs(post)  # type: ignore[arg-type]
    assert len(every) == 4


def test_real_nttdata_madrid_post_is_named_and_kept_out_of_chile(
    monkeypatch: object,
) -> None:
    """https://lnkd.in/p/duEeE6yu — single employer, apply link in the comments, Madrid."""
    post = _load_real_post("nttdata_ml_madrid", monkeypatch)

    assert post.vacancies == ()  # type: ignore[attr-defined]
    assert post.ats_url is None  # type: ignore[attr-defined]
    assert detect_country(post.text) == "ES"  # type: ignore[attr-defined]
    assert post_offers_wanted_country(post.text, wanted=["CL"]) is False  # type: ignore[attr-defined]

    job = post_to_job(post)  # type: ignore[arg-type]
    assert job.company == "NTT DATA"
    assert job.title == "Machine Learning & Customer Analytics"
    assert "talento" not in job.title.casefold()


def test_real_neuralworks_applied_scientist_is_named_and_teamtailor(
    monkeypatch: object,
) -> None:
    """https://lnkd.in/p/dXzvuKkn — Chilean Teamtailor career page behind a custom host."""
    post = _load_real_post("neuralworks_applied_scientist", monkeypatch)

    assert post.ats_kind == AtsKind.TEAMTAILOR  # type: ignore[attr-defined]
    assert post.ats_url == (  # type: ignore[attr-defined]
        "https://careers.neuralworks.cl/jobs/568945-applied-scientist"
    )
    assert post_offers_wanted_country(post.text, wanted=["CL"]) is True  # type: ignore[attr-defined]

    job = post_to_job(post)  # type: ignore[arg-type]
    assert job.company == "NeuralWorks"
    assert job.title.startswith("Applied Scientist")
    assert not job.title.lower().startswith("pplied")
    assert job.ats_kind == "teamtailor"


def test_real_fst_negocios_coinvestigador_is_named_and_kept_out_of_chile(
    monkeypatch: object,
) -> None:
    """https://lnkd.in/p/dtbAdT2k — Prociencia Perú; apply by LinkedIn DM, no ATS URL."""
    post = _load_real_post("fst_negocios_coinvestigador_ia", monkeypatch)

    assert post.vacancies == ()  # type: ignore[attr-defined]
    assert post.ats_url is None  # type: ignore[attr-defined]
    assert detect_country(post.text) == "PE"  # type: ignore[attr-defined]
    assert post_offers_wanted_country(post.text, wanted=["CL"]) is False  # type: ignore[attr-defined]
    assert post_offers_wanted_country(post.text, wanted=["PE"]) is True  # type: ignore[attr-defined]

    job = post_to_job(post)  # type: ignore[arg-type]
    assert job.company == "FST NEGOCIOS"
    assert "coinvestigador" in job.title.casefold()
    assert "inteligencia artificial" in job.title.casefold()
    # Title field must not win over the employer line ("En FST NEGOCIOS – Centro…").
    assert job.company != "INTELIGENCIA ARTIFICIAL"
    assert job.ats_url is None
    assert "mensaje interno" in job.description.casefold()


def test_real_peopletrust_cddo_is_named_from_mailbox_and_kept_for_chile(
    monkeypatch: object,
) -> None:
    """https://lnkd.in/p/ducvMAwj — Chilean Fintech CDDO; apply by email, Ley 21719."""
    post = _load_real_post("peopletrust_cddo", monkeypatch)

    assert post.vacancies == ()  # type: ignore[attr-defined]
    assert post.ats_url == "mailto:postulaciones@peopletrust.cl"  # type: ignore[attr-defined]
    assert post.ats_kind == AtsKind.EMAIL  # type: ignore[attr-defined]
    assert first_apply_email(post.text) == "postulaciones@peopletrust.cl"  # type: ignore[attr-defined]
    assert detect_country(post.text) == "CL"  # type: ignore[attr-defined]
    assert post_offers_wanted_country(post.text, wanted=["CL"]) is True  # type: ignore[attr-defined]

    job = post_to_job(post)  # type: ignore[arg-type]
    assert job.company == "Peopletrust"
    # Recruiter authored the post; the mailbox domain is the employer.
    assert job.company != "Rodolfo Amenabar"
    assert "gerente de tecnología" in job.title.casefold()
    assert "cddo" in job.title.casefold()
    assert "fintech" not in job.title.casefold()
    assert not job.title.casefold().endswith("para emp")
    assert "para empresa" not in job.title.casefold()
    assert job.ats_url == "mailto:postulaciones@peopletrust.cl"
    assert job.ats_kind == "email"


def test_real_macal_data_governance_architect_is_named_from_mailbox(
    monkeypatch: object,
) -> None:
    """https://lnkd.in/p/dYGD3B6J — Macal BizOps; apply by email, .cl mailbox."""
    post = _load_real_post("macal_data_governance_architect", monkeypatch)

    assert post.vacancies == ()  # type: ignore[attr-defined]
    assert post.ats_url == "mailto:talento@macal.cl"  # type: ignore[attr-defined]
    assert post.ats_kind == AtsKind.EMAIL  # type: ignore[attr-defined]
    assert first_apply_email(post.text) == "talento@macal.cl"  # type: ignore[attr-defined]
    assert detect_country(post.text) == "CL"  # type: ignore[attr-defined]
    assert post_offers_wanted_country(post.text, wanted=["CL"]) is True  # type: ignore[attr-defined]

    job = post_to_job(post)  # type: ignore[arg-type]
    assert job.company == "Macal"
    assert job.title == "Data Governance Architect"
    assert "diseñar" not in job.title.casefold()
    assert job.ats_url == "mailto:talento@macal.cl"
    assert job.ats_kind == "email"
