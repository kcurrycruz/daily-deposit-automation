import unittest


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


if __name__ == "__main__":
    unittest.main()
