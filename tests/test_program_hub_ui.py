import unittest
from pathlib import Path


class RecordingColumn:
    """A context-capable column that records renderer calls in order."""

    def __init__(self, ui, location):
        self.ui = ui
        self.location = location

    def __enter__(self):
        self.ui.flow.append(self.location)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.ui.flow.pop()

    def markdown(self, body, **kwargs):
        self.ui.markdown_calls.append((self.location, body, kwargs))

    def button(self, label, **kwargs):
        self.ui.button_calls.append((self.location, label, kwargs))
        return kwargs.get("key") in self.ui.clicked_keys

    def popover(self, label, **kwargs):
        self.ui.popover_calls.append((self.location, label, kwargs))
        return RecordingColumn(self.ui, f"{self.location}:popover")


class RecordingProgramHubUi(RecordingColumn):
    def __init__(self, clicked_keys=()):
        self.clicked_keys = set(clicked_keys)
        self.flow = []
        self.markdown_calls = []
        self.button_calls = []
        self.popover_calls = []
        self.columns_calls = []
        super().__init__(self, "root")

    def columns(self, widths, **kwargs):
        self.columns_calls.append((tuple(widths) if not isinstance(widths, int) else widths, kwargs))
        count = widths if isinstance(widths, int) else len(widths)
        return [RecordingColumn(self, f"columns-{len(self.columns_calls)}-{index}") for index in range(count)]


class ProgramHubStateTests(unittest.TestCase):
    def test_daily_deposits_is_only_enabled_program_in_required_order(self):
        from app.program_hub_ui import PROGRAMS

        self.assertEqual(
            [program.title for program in PROGRAMS],
            ["Daily Deposits", "Credit Card Process", "AP Statements"],
        )
        self.assertEqual(
            [program.enabled for program in PROGRAMS],
            [True, False, False],
        )

    def test_normalize_selection_rejects_missing_disabled_and_unknown_keys(self):
        from app.program_hub_ui import normalize_program_selection

        self.assertIsNone(normalize_program_selection(None))
        self.assertIsNone(normalize_program_selection("credit_card_process"))
        self.assertIsNone(normalize_program_selection("unknown_program"))

    def test_activate_daily_deposits_sets_active_key_and_preserves_state(self):
        from app.program_hub_ui import ACTIVE_PROGRAM_KEY, DAILY_DEPOSITS, activate_program

        state = {"membership_payments": {"status": "ready"}}

        self.assertTrue(activate_program(state, DAILY_DEPOSITS))
        self.assertEqual(state[ACTIVE_PROGRAM_KEY], DAILY_DEPOSITS)
        self.assertEqual(state["membership_payments"], {"status": "ready"})

    def test_activate_disabled_program_does_not_mutate_existing_active_state(self):
        from app.program_hub_ui import ACTIVE_PROGRAM_KEY, activate_program

        state = {
            ACTIVE_PROGRAM_KEY: "daily_deposits",
            "membership_payments": {"status": "ready"},
        }

        self.assertFalse(activate_program(state, "ap_statements"))
        self.assertEqual(state[ACTIVE_PROGRAM_KEY], "daily_deposits")
        self.assertEqual(state["membership_payments"], {"status": "ready"})

    def test_return_to_program_hub_removes_only_active_key(self):
        from app.program_hub_ui import ACTIVE_PROGRAM_KEY, return_to_program_hub

        state = {
            ACTIVE_PROGRAM_KEY: "daily_deposits",
            "membership_payments": {"status": "ready"},
            "run_result": {"rows": 3},
        }

        return_to_program_hub(state)

        self.assertNotIn(ACTIVE_PROGRAM_KEY, state)
        self.assertEqual(state["membership_payments"], {"status": "ready"})
        self.assertEqual(state["run_result"], {"rows": 3})


class ProgramHubRendererTests(unittest.TestCase):
    def test_renders_header_prompt_titles_and_program_action_states(self):
        from app.program_hub_ui import render_program_hub

        ui = RecordingProgramHubUi()

        self.assertIsNone(render_program_hub(ui))

        rendered_copy = "\n".join(body for _, body, _ in ui.markdown_calls)
        self.assertIn("Honest Weight Food Co-op", rendered_copy)
        self.assertIn("Finance Operations", rendered_copy)
        self.assertIn("What are you working on?", rendered_copy)
        self.assertIn("Choose a program to begin.", rendered_copy)
        self.assertIn("Daily Deposits", rendered_copy)
        self.assertIn("Credit Card Process", rendered_copy)
        self.assertIn("AP Statements", rendered_copy)
        self.assertEqual(len(ui.button_calls), 3)
        self.assertEqual(sum(call[2].get("disabled", False) for call in ui.button_calls), 2)

    def test_uses_open_and_coming_soon_action_labels(self):
        from app.program_hub_ui import render_program_hub

        ui = RecordingProgramHubUi()
        render_program_hub(ui)

        self.assertEqual(
            [label for _, label, _ in ui.button_calls],
            ["Open program →", "Coming Soon", "Coming Soon"],
        )

    def test_clicking_daily_deposits_returns_its_key(self):
        from app.program_hub_ui import DAILY_DEPOSITS, render_program_hub

        ui = RecordingProgramHubUi({"open_program_daily_deposits"})

        self.assertEqual(render_program_hub(ui), DAILY_DEPOSITS)

    def test_card_markup_escapes_html_content(self):
        from app.program_hub_ui import ProgramDefinition, program_card_html

        markup = program_card_html(
            ProgramDefinition("unsafe", "<script>", "Salt & <pepper>", True)
        )

        self.assertIn("&lt;script&gt;", markup)
        self.assertIn("Salt &amp; &lt;pepper&gt;", markup)
        self.assertNotIn("<script>", markup)

    def test_need_help_is_in_right_hand_header_popover(self):
        from app.program_hub_ui import render_program_hub

        ui = RecordingProgramHubUi()
        render_program_hub(ui)

        self.assertEqual(ui.columns_calls[0][0], (3, 1))
        location, label, _ = ui.popover_calls[0]
        self.assertEqual(location, "columns-1-1")
        self.assertEqual(label, "❔ Need Help")
        self.assertIn(
            "Daily Deposits for the SOP, tips, and run history.",
            next(
                body
                for markdown_location, body, _ in ui.markdown_calls
                if markdown_location == "columns-1-1:popover"
            ),
        )

    def test_disabled_cards_show_coming_soon_only_in_the_action(self):
        from app.program_hub_ui import PROGRAMS, program_card_html, render_program_hub

        ui = RecordingProgramHubUi()
        render_program_hub(ui)

        for program in (program for program in PROGRAMS if not program.enabled):
            combined_markup = program_card_html(program) + "\n" + next(
                label
                for _, label, kwargs in ui.button_calls
                if kwargs["key"] == f"open_program_{program.key}"
            )
            self.assertEqual(combined_markup.count("Coming Soon"), 1)

    def test_all_programs_action_returns_click_without_mutating_state(self):
        from app.program_hub_ui import render_all_programs_action

        ui = RecordingProgramHubUi({"return_to_program_hub"})
        state_before = dict(ui.__dict__)

        self.assertTrue(render_all_programs_action(ui))
        self.assertEqual(ui.clicked_keys, state_before["clicked_keys"])
        self.assertEqual(ui.button_calls[0][1], "← All Programs")
        self.assertEqual(ui.button_calls[0][2]["key"], "return_to_program_hub")


class ProgramHubEntryPointTests(unittest.TestCase):
    @staticmethod
    def app_source():
        return (
            Path(__file__).resolve().parents[1] / "streamlit_app.py"
        ).read_text(encoding="utf-8")

    def route_position(self, app_source):
        marker = "selected_program = normalize_program_selection("
        self.assertIn(marker, app_source)
        return app_source.index(marker)

    def test_hub_route_precedes_the_daily_deposit_hero_markup(self):
        app_source = self.app_source()

        route_position = self.route_position(app_source)
        hero_position = app_source.index(
            '<div class="hwfc-title">Daily Deposit Reconciliation</div>'
        )

        self.assertLess(route_position, hero_position)

    def test_hub_stops_before_the_daily_deposit_hero_renders(self):
        app_source = self.app_source()
        route_position = self.route_position(app_source)
        hero_position = app_source.index(
            '<div class="hwfc-title">Daily Deposit Reconciliation</div>'
        )
        hub_route = app_source[route_position:hero_position]

        self.assertLess(
            hub_route.index("render_program_hub(st)"),
            hub_route.index("st.stop()"),
        )

    def test_all_programs_returns_to_hub_without_resetting_deposit_work(self):
        app_source = self.app_source()
        action_marker = "if render_all_programs_action(st):"
        self.assertIn(action_marker, app_source)
        action_position = app_source.index(action_marker)
        header_position = app_source.index("# Header")
        action_block = app_source[action_position:header_position]

        self.assertIn("return_to_program_hub(st.session_state)", action_block)
        self.assertIn("st.rerun()", action_block)
        self.assertNotIn("reset_current_work()", action_block)

    def test_existing_sidebar_stays_after_the_hub_stop_boundary(self):
        app_source = self.app_source()
        route_position = self.route_position(app_source)
        hero_position = app_source.index(
            '<div class="hwfc-title">Daily Deposit Reconciliation</div>'
        )
        hub_route = app_source[route_position:hero_position]
        sidebar_position = app_source.index("with st.sidebar:")

        self.assertLess(route_position + hub_route.index("st.stop()"), sidebar_position)


if __name__ == "__main__":
    unittest.main()
