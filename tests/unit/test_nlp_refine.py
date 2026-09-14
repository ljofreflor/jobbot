"""Cumulative profile refine tests — previous text is computational capital."""

from jobbot.adapters.getonboard.draft import PermanentProfileFields
from jobbot.models.candidate import Candidate
from jobbot.nlp.refine import CumulativeProfileRefiner, refine_permanent_profile
from tests.fixtures.profile import sample_profile_dict


def _previous_obsolete() -> PermanentProfileFields:
    return PermanentProfileFields(
        experiencia_y_perfil=(
            "Me he dedicado a Matlab, VTK y Mayavi en Ceamos www.ceamos.cl.\n\n"
            "También trabajé modelos en Python en Mercado Libre con share of wallet."
        ),
        formacion_academica="Magíster en Estadística — PUC.",
        headline="Old headline",
        skills=["Matlab"],
    )


def test_cumulative_drops_obsolete_keeps_supported() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    result = CumulativeProfileRefiner().refine_with_stats(candidate, _previous_obsolete())
    assert result.mode == "cumulative"
    assert result.dropped_paragraphs >= 1
    text = result.fields.experiencia_y_perfil.casefold()
    assert "ceamos" not in text
    assert "matlab" not in text
    assert "mercado libre" in text or "data scientist" in text


def test_cold_start_when_no_previous() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    result = refine_permanent_profile(candidate, None)
    assert result.mode == "cold"
    assert result.fields.experiencia_y_perfil


def test_refine_does_not_invent_kubernetes() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    result = refine_permanent_profile(candidate, _previous_obsolete())
    assert "kubernetes" not in result.fields.experiencia_y_perfil.casefold()
