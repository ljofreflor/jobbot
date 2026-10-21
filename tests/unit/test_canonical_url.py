"""Dedup keys fold the cases a URL parser already solves."""

from jobbot.companies.urls import canonical_key, public_url


def test_equivalent_career_urls_share_one_key() -> None:
    base = "https://empresa.cl/consultoría-senior"
    variants = [
        "https://empresa.cl:443/consultor%C3%ADa-senior",
        "http://www.empresa.cl/a/../consultoría-senior/",
        "https://www.empresa.cl//consultoría-senior//?utm_source=x#top",
        "https://user:secret@empresa.cl/consultoría-senior",
    ]
    key = canonical_key(base)
    assert "secret" not in public_url(variants[-1])
    for url in variants:
        assert canonical_key(url) == key

    assert canonical_key("https://bücher.example/jobs") == canonical_key(
        "https://xn--bcher-kva.example/jobs"
    )
    assert canonical_key("https://host.example/a%20b") == canonical_key("https://host.example/a b")
    assert canonical_key("https://empresa.cl:8443/jobs") != canonical_key("https://empresa.cl/jobs")
