import unittest

from fastapi import HTTPException

from backend.app.overseas import US_NAME_KO, US_STOCKS, _analysis_from_quote, _clean_symbol, _parse_nasdaq_directory


class OverseasMarketContractTests(unittest.TestCase):
    def test_normalizes_valid_us_ticker(self):
        self.assertEqual(_clean_symbol(" brk-b "), "BRK-B")
        self.assertEqual(_clean_symbol("aapl"), "AAPL")

    def test_rejects_unsafe_or_non_ticker_input(self):
        for value in ("", "005930", "AAPL/../../", "AAPL US", "한글"):
            with self.subTest(value=value), self.assertRaises(HTTPException):
                _clean_symbol(value)

    def test_curated_fallback_is_unique_and_us_only(self):
        symbols = [row["symbol"] for row in US_STOCKS]
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertTrue(all(row["exchange"] in {"NASDAQ", "NYSE"} for row in US_STOCKS))

    def test_parses_official_nasdaq_directories_and_excludes_test_issue(self):
        listed=(
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
            "TEST|Test Security|Q|Y|N|100|N|N\n"
            "QQQ|Invesco QQQ Trust ETF|Q|N|N|100|Y|N\n"
            "File Creation Time: 0901202618:01|||||||\n"
        )
        rows=_parse_nasdaq_directory(listed,"nasdaq")
        self.assertEqual([row["symbol"] for row in rows],["AAPL","QQQ"])
        self.assertEqual(rows[0]["exchange"],"NASDAQ")
        self.assertEqual(rows[1]["asset_type"],"etf")

    def test_parses_nyse_directory_exchange_code(self):
        other=(
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
            "A|Agilent Technologies, Inc. Common Stock|N|A|N|100|N|A\n"
        )
        rows=_parse_nasdaq_directory(other,"other")
        self.assertEqual(rows[0]["exchange"],"NYSE")
        self.assertEqual(rows[0]["mic"],"XNYS")

    def test_quote_analysis_is_bounded_and_explainable(self):
        strong=_analysis_from_quote({"available":True,"price":110,"change_percent":5,"open":104,"high":111,"low":100,"previous_close":103})
        weak=_analysis_from_quote({"available":True,"price":91,"change_percent":-6,"open":98,"high":100,"low":90,"previous_close":97})
        self.assertGreater(strong["score"],weak["score"])
        self.assertGreaterEqual(strong["score"],0)
        self.assertLessEqual(strong["score"],100)
        self.assertIn("무료 시세",strong["reason"])
        self.assertGreater(strong["coverage"],0)
        self.assertTrue(any(item.get("key")=="momentum" for item in strong["components"]))

    def test_core_korean_aliases_support_ticker_parenthesis_display(self):
        self.assertEqual(US_NAME_KO["TSLA"],"테슬라")
        self.assertEqual(f"TSLA({US_NAME_KO['TSLA']})","TSLA(테슬라)")


if __name__ == "__main__":
    unittest.main()
