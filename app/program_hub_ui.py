"""Program registry and safe navigation state for the finance operations hub."""

from dataclasses import dataclass
from html import escape
from typing import MutableMapping


ACTIVE_PROGRAM_KEY = "active_finance_program"
DAILY_DEPOSITS = "daily_deposits"


@dataclass(frozen=True)
class ProgramDefinition:
    key: str
    title: str
    description: str
    enabled: bool


PROGRAMS: tuple[ProgramDefinition, ...] = (
    ProgramDefinition(
        DAILY_DEPOSITS,
        "Daily Deposits",
        "Reconcile daily reports and prepare the QuickBooks import.",
        True,
    ),
    ProgramDefinition(
        "credit_card_process",
        "Credit Card Process",
        "Process and verify credit-card activity.",
        False,
    ),
    ProgramDefinition(
        "ap_statements",
        "AP Statements",
        "Review and reconcile accounts-payable statements.",
        False,
    ),
)


def program_card_html(program: ProgramDefinition) -> str:
    """Return safe, state-aware card markup for a finance program."""
    state_class = "is-available" if program.enabled else "is-coming-soon"
    return (
        f'<section class="hwfc-program-card {state_class}">'
        f'<h2 class="hwfc-program-card-title">{escape(program.title)}</h2>'
        f'<p class="hwfc-program-card-copy">{escape(program.description)}</p>'
        "</section>"
    )


def render_program_hub(ui) -> str | None:
    """Render program choices and return an enabled selected program key."""
    title_column, help_column = ui.columns([3, 1])
    with title_column:
        title_column.markdown(
            """
            <div class="hwfc-hub-hero">
              <div class="hwfc-hub-kicker">Honest Weight Food Co-op</div>
              <div class="hwfc-hub-title">Finance Operations</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with help_column:
        help_popover = help_column.popover("❔ Need Help")
        with help_popover:
            help_popover.markdown(
                "Visit Daily Deposits for the SOP, tips, and run history."
            )

    ui.markdown(
        """
        <section class="hwfc-hub-prompt">
          <h2>What are you working on?</h2>
          <p>Choose a program to begin.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    selected_key = None
    for column, program in zip(ui.columns(len(PROGRAMS)), PROGRAMS):
        with column:
            column.markdown(program_card_html(program), unsafe_allow_html=True)
            if column.button(
                "Open program →" if program.enabled else "Coming Soon",
                key=f"open_program_{program.key}",
                disabled=not program.enabled,
                use_container_width=True,
            ) and program.enabled:
                selected_key = program.key
    return selected_key


def render_all_programs_action(ui) -> bool:
    """Render the hub-return control without changing navigation state."""
    return ui.button(
        "← All Programs",
        key="return_to_program_hub",
        use_container_width=True,
    )


def normalize_program_selection(value: object) -> str | None:
    """Return an enabled program key, or ``None`` for invalid selections."""
    if not isinstance(value, str):
        return None
    for program in PROGRAMS:
        if program.key == value and program.enabled:
            return program.key
    return None


def activate_program(
    state: MutableMapping[str, object], program_key: str
) -> bool:
    """Activate an enabled program without changing unrelated state."""
    normalized_key = normalize_program_selection(program_key)
    if normalized_key is None:
        return False
    state[ACTIVE_PROGRAM_KEY] = normalized_key
    return True


def return_to_program_hub(state: MutableMapping[str, object]) -> None:
    """Clear the active program while preserving all other state."""
    state.pop(ACTIVE_PROGRAM_KEY, None)
