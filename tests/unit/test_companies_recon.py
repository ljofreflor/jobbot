"""Inside recon: learn ATS and form questions from a page the human is on."""

from pathlib import Path

from jobbot.companies.recon import make_observation, recon_from_html
from jobbot.portals.detect import AtsKind

GREENHOUSE_EMBED = """
<!DOCTYPE html>
<html>
<head><title>Careers at Acme</title></head>
<body>
<h1>Join our team</h1>
<div id="grnhse_app"></div>
<script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>
<form>
  <label for="name">Full name *</label>
  <input type="text" id="name" name="name" required />
  
  <label for="email">Email *</label>
  <input type="email" id="email" name="email" required />
  
  <label for="resume">Resume/CV *</label>
  <input type="file" id="resume" name="resume" accept=".pdf,.doc,.docx" required />
  
  <label for="start">When could you start?</label>
  <select id="start" name="start">
    <option value="">Select...</option>
    <option value="immediately">Immediately</option>
    <option value="2weeks">2 weeks</option>
    <option value="1month">1 month</option>
  </select>
  
  <label for="visa">Do you require visa sponsorship?</label>
  <input type="radio" name="visa" value="yes" /> Yes
  <input type="radio" name="visa" value="no" /> No
</form>
</body>
</html>
"""

NO_MARKERS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Careers</title></head>
<body>
<h1>Work with us</h1>
<p>Send your CV to jobs@empresa.cl</p>
<form>
  <label for="name">Name</label>
  <input type="text" id="name" name="name" />
  
  <label for="email">Email</label>
  <input type="email" id="email" name="email" />
</form>
</body>
</html>
"""


def test_fixture_with_greenhouse_embed_detects_ats_with_evidence() -> None:
    """Fixture HTML with a Greenhouse embed → ats=greenhouse with evidence."""
    result = recon_from_html(
        GREENHOUSE_EMBED,
        url="https://acme.example.com/careers",
        company="Acme Corp",
        company_id="acme",
    )

    assert result.ats == AtsKind.GREENHOUSE
    assert "greenhouse" in result.ats_evidence.lower()
    assert result.company_id == "acme"


def test_page_without_markers_stays_unknown() -> None:
    """Page without markers → ats stays unknown (never guess from hostname)."""
    result = recon_from_html(
        NO_MARKERS_HTML,
        url="https://empresa.cl/trabaja-con-nosotros",
        company="Empresa",
        company_id="empresa",
    )

    assert result.ats == AtsKind.UNKNOWN
    assert result.ats_evidence == ""


def test_form_fixture_stores_labels_types_required_options_only() -> None:
    """Form fixture → form knowledge stores labels/types/required/options/accept only."""
    result = recon_from_html(
        GREENHOUSE_EMBED,
        url="https://acme.example.com/careers/apply",
        company="Acme Corp",
        company_id="acme",
    )

    assert result.form.readable
    assert len(result.form.fields) > 0

    field_by_label = {f.label: f for f in result.form.fields}

    # Check required fields
    assert "Full name" in field_by_label
    name_field = field_by_label["Full name"]
    assert name_field.required
    assert name_field.kind.value in ("text", "TEXT")

    # Check email field
    assert "Email" in field_by_label
    email_field = field_by_label["Email"]
    assert email_field.required
    assert email_field.kind.value in ("email", "EMAIL")

    # Check file field with accept attribute
    assert "Resume/CV" in field_by_label
    cv_field = field_by_label["Resume/CV"]
    assert cv_field.required
    assert cv_field.kind.value in ("file", "FILE")
    assert ".pdf" in cv_field.accepts or ".pdf" in str(cv_field.accepts)

    # Check select field with options
    assert "When could you start?" in field_by_label
    start_field = field_by_label["When could you start?"]
    assert start_field.kind.value in ("select", "SELECT")
    assert not start_field.required
    assert len(start_field.options) > 0
    assert any("Immediately" in opt for opt in start_field.options)


def test_form_knowledge_does_not_store_typed_values() -> None:
    """Form knowledge never stores typed values, tokens, or example emails."""
    html_with_placeholder = """
    <form>
      <label for="email">Email</label>
      <input type="email" id="email" name="email" placeholder="john@example.com" value="" />
      <input type="hidden" name="csrf" value="secret-token-123" />
    </form>
    """
    result = recon_from_html(
        html_with_placeholder,
        url="https://example.com/apply",
        company="Example",
    )

    if result.form.readable:
        # No hidden fields should be captured
        assert not any(f.kind.value in ("hidden", "HIDDEN") for f in result.form.fields)

        # Email field should exist but without the placeholder value
        email_fields = [f for f in result.form.fields if f.label == "Email"]
        if email_fields:
            # The label is captured, but not the placeholder email
            assert "john@example.com" not in str(email_fields[0].model_dump())


def test_observation_has_user_source_and_timestamp() -> None:
    """Observations from recon are marked as USER_OBSERVATION."""
    result = recon_from_html(
        GREENHOUSE_EMBED,
        url="https://acme.example.com/careers",
        company="Acme",
    )
    observation = make_observation(result)

    assert observation.source.value == "user_observation"
    assert observation.ats == result.ats
    assert observation.evidence == result.ats_evidence
    assert observation.checked_at is not None


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Without --apply, recon shows results but writes nothing."""
    # This is tested implicitly by the CLI tests, but we verify the function
    # itself doesn't have side effects
    result = recon_from_html(
        GREENHOUSE_EMBED,
        url="https://acme.example.com/careers",
        company="Acme",
    )

    # The result contains observations, but nothing is written
    assert result.observation_written is False
    assert result.form_written is False


def test_empty_html_returns_unreadable_form() -> None:
    """Empty or invalid HTML results in an unreadable form."""
    result = recon_from_html(
        "",
        url="https://example.com/careers",
        company="Example",
    )

    assert not result.form.readable
    assert "unknown" in result.form.evidence.lower()


def test_company_id_defaults_to_slugified_name() -> None:
    """When company_id is not provided, it defaults to a slug of the name."""
    result = recon_from_html(
        NO_MARKERS_HTML,
        url="https://example.com/careers",
        company="Example Corp",
    )

    assert result.company_id == "example-corp"


def test_multiple_forms_picks_application_form() -> None:
    """When multiple forms exist, picks the one that looks like an application."""
    html_multiple = """
    <form id="search">
      <input type="text" name="q" />
    </form>
    <form id="apply">
      <label for="name">Full name</label>
      <input type="text" id="name" name="name" required />
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required />
      <label for="cv">Resume</label>
      <input type="file" id="cv" name="cv" required />
    </form>
    """
    result = recon_from_html(
        html_multiple,
        url="https://example.com/careers",
        company="Example",
    )

    assert result.form.readable
    # Should have found the application form, not the search form
    assert any("Resume" in f.label for f in result.form.fields)
