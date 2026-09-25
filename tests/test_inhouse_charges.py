import unittest


class InhouseMemoTests(unittest.TestCase):
    def test_end_of_day_memo_trims_and_uppercases_initials(self):
        from app.inhouse_charges import compose_inhouse_memo

        self.assertEqual(compose_inhouse_memo("End of Day", " bs "), "End of Day - BS")

    def test_end_of_day_memo_does_not_require_initials(self):
        from app.inhouse_charges import compose_inhouse_memo

        self.assertEqual(compose_inhouse_memo("End of Day", " "), "End of Day")

    def test_custom_memo_trims_without_changing_case(self):
        from app.inhouse_charges import compose_inhouse_memo

        self.assertEqual(compose_inhouse_memo("Custom", "  Board lunch  "), "Board lunch")

    def test_blank_custom_or_unknown_memo_input_is_rejected(self):
        from app.inhouse_charges import compose_inhouse_memo

        for mode, value in (("Custom", ""), ("Other", "BS")):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                compose_inhouse_memo(mode, value)

    def test_saved_memos_split_back_into_widget_values(self):
        from app.inhouse_charges import split_inhouse_memo

        self.assertEqual(split_inhouse_memo("End of Day - BS"), ("End of Day", "BS"))
        self.assertEqual(split_inhouse_memo("End of Day"), ("End of Day", ""))
        self.assertEqual(split_inhouse_memo("Board lunch"), ("Custom", "Board lunch"))


class InhousePayloadTests(unittest.TestCase):
    def test_step_payload_calculates_actual_from_charge_rows(self):
        from app.inhouse_charges import normalize_inhouse_step_payload

        payload = normalize_inhouse_step_payload({
            "actual": "999.99",
            "rows": [
                {"account": "8320000 · Store Supplies", "memo": "End of Day - BS", "amount": "100.82"},
                {"account": "8504000 · Education", "memo": "Class materials", "amount": "40"},
            ],
        })
        self.assertEqual(payload["actual"], 140.82)
        self.assertEqual(sum(row["amount"] for row in payload["rows"]), 140.82)

    def test_step_payload_requires_at_least_one_charge(self):
        from app.inhouse_charges import normalize_inhouse_step_payload

        with self.assertRaisesRegex(ValueError, "at least one InHouse charge"):
            normalize_inhouse_step_payload({"actual": 140.82, "rows": []})


if __name__ == "__main__":
    unittest.main()
