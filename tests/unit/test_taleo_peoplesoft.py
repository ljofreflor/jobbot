"""Taleo on its own host is not Oracle Recruiting Cloud. PeopleSoft is the HRMS path."""

from jobbot.portals.detect import AtsKind, detect_ats, detect_ats_in_html


def test_taleo_is_not_oracle_and_peoplesoft_is_the_hrms_path() -> None:
    taleo = "https://carreras.servicio-neutro.test/careersection/ex/jobsearch.ftl"
    peoplesoft = "https://hr.servicio-neutro.test/psc/ps/EMPLOYEE/HRMS/c/HRS_CE.GBL"
    oracle = "https://acme.fa.oraclecloud.com/hcmUI/CandidateExperience/es/sites/CX_1/job/1"

    assert detect_ats("https://empresa.taleo.net/careersection/x") is AtsKind.TALEO
    assert detect_ats(taleo) is AtsKind.TALEO
    assert detect_ats(peoplesoft) is AtsKind.PEOPLESOFT
    assert detect_ats(oracle) is AtsKind.ORACLE

    kind, evidence = detect_ats_in_html(
        '<a href="https://carreras.servicio-neutro.test/careersection/ex/jobsearch.ftl">'
    )
    assert kind is AtsKind.TALEO
    assert "taleo" in evidence

    kind, evidence = detect_ats_in_html(
        '<a href="/psc/ps/EMPLOYEE/HRMS/c/HRS_CE.GBL">vacantes</a>'
    )
    assert kind is AtsKind.PEOPLESOFT
    assert "peoplesoft" in evidence

    kind, _evidence = detect_ats_in_html(
        '<a href="https://acme.fa.oraclecloud.com/hcmUI/CandidateExperience/">'
    )
    assert kind is AtsKind.ORACLE
