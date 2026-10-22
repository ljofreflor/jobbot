"""Public career portals whose profile jobbot can project from the source of truth.

Writing into the live site is a later adapter. These records say which sections
the form asks, which facts the source of truth does not have, and which portals
are bound to a state identity so jobbot must not attach to the browser.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobbot.portals.profile_state import AccountState, PortalProfileState, Priority

_INTL = (
    "identity",
    "headline",
    "summary",
    "experience",
    "education",
    "languages",
    "skills",
    "cv",
)
_BOARD = (
    "identity",
    "headline",
    "summary",
    "experience",
    "education",
    "skills",
    "cv",
)
_CIVIL = ("identity", "experience", "education", "cv")
_UN_GAPS = ("date_of_birth", "gender", "nationality", "disability")
_ID_GAPS = ("national_id",)


@dataclass(frozen=True)
class FillPortal:
    portal: str
    name: str
    adapter: str
    priority: Priority
    account: AccountState
    signup_url: str
    profile_url: str | None
    sections: tuple[str, ...]
    gaps: tuple[str, ...]
    maintenance_days: int
    cv_variant: str


def _row(
    portal: str,
    name: str,
    adapter: str,
    priority: Priority,
    signup_url: str,
    *,
    profile_url: str | None = None,
    sections: tuple[str, ...] = _INTL,
    gaps: tuple[str, ...] = (),
    account: AccountState = AccountState.unknown,
    days: int = 60,
    cv_variant: str = "base_en",
) -> FillPortal:
    return FillPortal(
        portal=portal,
        name=name,
        adapter=adapter,
        priority=priority,
        account=account,
        signup_url=signup_url,
        profile_url=profile_url,
        sections=sections,
        gaps=gaps,
        maintenance_days=days,
        cv_variant=cv_variant,
    )


# URLs are the public registration pages. No candidate data.
FILL_PORTALS: tuple[FillPortal, ...] = (
    _row(
        "un_careers",
        "UN Careers / Inspira",
        "inspira",
        Priority.high,
        "https://careers.un.org/",
        profile_url="https://careers.un.org/",
        gaps=_UN_GAPS,
    ),
    _row(
        "unicef",
        "UNICEF Careers (PageUp)",
        "pageup",
        Priority.high,
        "https://jobs.unicef.org/",
    ),
    _row(
        "fao",
        "FAO Jobs (Taleo)",
        "taleo",
        Priority.medium,
        "https://jobs.fao.org/careersection/fao_external/accesscontrol.ftl?lang=es",
        profile_url="https://jobs.fao.org/",
        cv_variant="base_es",
    ),
    _row(
        "adp",
        "Alta Dirección Pública",
        "identity_bound",
        Priority.high,
        "https://adp.serviciocivil.cl/concursos-spl/opencms/registro.html",
        profile_url="https://adp.serviciocivil.cl/concursos-spl/opencms/login.html",
        sections=_CIVIL,
        gaps=_ID_GAPS,
        account=AccountState.identity_bound,
        cv_variant="base_es",
    ),
    _row(
        "devex",
        "Devex",
        "devex",
        Priority.high,
        "https://www.devex.com/login",
        profile_url="https://www.devex.com/profile/upload_cv",
    ),
    _row(
        "impactpool",
        "Impactpool",
        "impactpool",
        Priority.high,
        "https://www.impactpool.org/signup",
    ),
    _row(
        "oms_who",
        "WHO Careers (Taleo)",
        "taleo",
        Priority.high,
        "https://careers.who.int/careersection/ex/accesscontrol.ftl?lang=en",
        profile_url="https://careers.who.int/",
    ),
    _row(
        "empleos_publicos",
        "Empleos Públicos",
        "identity_bound",
        Priority.high,
        "https://www.empleospublicos.cl/",
        sections=_CIVIL,
        gaps=_ID_GAPS,
        account=AccountState.identity_bound,
        cv_variant="base_es",
    ),
    _row(
        "ops_paho",
        "PAHO Careers (Workday)",
        "workday",
        Priority.high,
        "https://paho.wd5.myworkdayjobs.com/en-US/pahocareers",
    ),
    _row(
        "bid_idb",
        "IDB Jobs",
        "generic",
        Priority.medium,
        "https://jobs.iadb.org/",
    ),
    _row(
        "banco_mundial",
        "World Bank Group (Cornerstone)",
        "cornerstone",
        Priority.medium,
        "https://www.worldbank.org/en/about/careers",
    ),
    _row(
        "pnud_undp",
        "UNDP Careers",
        "oracle_orc",
        Priority.medium,
        "https://www.undp.org/careers",
    ),
    _row(
        "unops",
        "UNOPS Talent Community",
        "generic",
        Priority.medium,
        "https://careers.unops.org/",
    ),
    _row(
        "oim_iom",
        "IOM Careers",
        "oracle_orc",
        Priority.medium,
        "https://www.iom.int/careers",
    ),
    _row(
        "ifrc",
        "IFRC Careers",
        "lumesse",
        Priority.medium,
        "https://careers.ifrc.org/",
    ),
    _row(
        "iica",
        "IICA consultant roster",
        "generic",
        Priority.low,
        "https://apps.iica.int/SICO/pages/public/login",
        cv_variant="base_es",
    ),
    _row(
        "michael_page",
        "Michael Page",
        "generic",
        Priority.high,
        "https://www.michaelpage.cl/",
        sections=("identity", "cv"),
        cv_variant="base_es",
        days=60,
    ),
    _row(
        "trabajando",
        "Trabajando.cl",
        "trabajando",
        Priority.medium,
        "https://www.trabajando.cl/crea-tu-curriculum",
        profile_url="https://www.trabajando.cl/ingresa-a-tu-cuenta",
        sections=_BOARD,
        gaps=("national_id", "salary_expectation"),
        cv_variant="base_es",
        days=14,
    ),
    _row(
        "laborum",
        "Laborum",
        "generic",
        Priority.medium,
        "https://www.laborum.cl/signin",
        sections=_BOARD,
        cv_variant="base_es",
        days=14,
    ),
    _row(
        "indeed",
        "Indeed",
        "indeed",
        Priority.medium,
        "https://profile.indeed.com/",
        sections=_BOARD,
        cv_variant="base_es",
        days=30,
    ),
    _row(
        "linkedin",
        "LinkedIn",
        "linkedin",
        Priority.high,
        "https://www.linkedin.com/signup",
        sections=_BOARD,
        cv_variant="base_es",
        days=30,
    ),
    _row(
        "getonboard",
        "Get on Board",
        "getonboard",
        Priority.low,
        "https://www.getonbrd.com/webpros/login",
        profile_url="https://www.getonbrd.com/webpros/edit",
        sections=_BOARD,
        cv_variant="base_es",
        days=90,
    ),
    _row(
        "korn_ferry",
        "Korn Ferry",
        "generic",
        Priority.medium,
        "https://account.candidate.kornferry.com/register",
        sections=_BOARD,
        cv_variant="base_es",
    ),
    _row(
        "robert_walters",
        "Robert Walters",
        "generic",
        Priority.medium,
        "https://www.robertwalters.cl/",
        sections=("identity", "cv"),
        cv_variant="base_es",
    ),
    _row(
        "computrabajo",
        "Computrabajo",
        "generic",
        Priority.low,
        "https://www.computrabajo.cl/",
        sections=_BOARD,
        cv_variant="base_es",
        days=14,
    ),
    _row(
        "chiletrabajos",
        "Chiletrabajos",
        "generic",
        Priority.low,
        "https://www.chiletrabajos.cl/chtregister",
        sections=_BOARD,
        cv_variant="base_es",
        days=14,
    ),
    _row(
        "randstad",
        "Randstad",
        "generic",
        Priority.low,
        "https://www.randstad.cl/",
        sections=_BOARD,
        cv_variant="base_es",
    ),
    _row(
        "adecco",
        "Adecco",
        "generic",
        Priority.low,
        "https://candidate.adecco.com/",
        sections=_BOARD,
        cv_variant="base_es",
    ),
    _row(
        "hays",
        "Hays",
        "generic",
        Priority.low,
        "https://www.hays.com/",
        sections=_BOARD,
        cv_variant="base_es",
    ),
    _row(
        "mercado_publico",
        "Mercado Público",
        "identity_bound",
        Priority.medium,
        "https://www.mercadopublico.cl/",
        sections=_CIVIL,
        gaps=_ID_GAPS,
        account=AccountState.identity_bound,
        cv_variant="base_es",
    ),
    _row(
        "bne",
        "Bolsa Nacional de Empleo",
        "identity_bound",
        Priority.low,
        "https://www.bne.cl/",
        sections=_CIVIL,
        gaps=_ID_GAPS,
        account=AccountState.identity_bound,
        cv_variant="base_es",
    ),
)

_BY_ID = {item.portal: item for item in FILL_PORTALS}


def fill_portal(portal_id: str) -> FillPortal | None:
    return _BY_ID.get(portal_id)


def catalog_state(portal: FillPortal) -> PortalProfileState:
    """A tracker row with no sync evidence. Seeding does not claim the account exists."""
    return PortalProfileState(
        portal=portal.portal,
        adapter=portal.adapter,
        priority=portal.priority,
        account=portal.account,
        login_method="identity_bound" if portal.account is AccountState.identity_bound else "email",
        signup_url=portal.signup_url,
        profile_url=portal.profile_url,
        cv_variant=portal.cv_variant,
        sections=list(portal.sections),
        gaps=list(portal.gaps),
        maintenance_days=portal.maintenance_days,
    )
