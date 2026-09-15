import unittest

from adapters.tts import ChineseSpeechError, optimize_chinese_speech
from adapters.tts.zh_speech import integer_to_chinese, load_zh_voice_config


class ChineseSpeechTests(unittest.TestCase):
    def test_normalizes_numbers_percent_year_currency_and_network(self):
        plan = optimize_chinese_speech("2026年，¥40，增长3.5%，支持5G。")

        self.assertEqual(plan.text, "二零二六年，四十元，增长百分之三点五，支持五 G。")

    def test_handles_products_acronyms_and_mixed_language(self):
        plan = optimize_chinese_speech("用ChatGPT分析AI和CPU，再连接Wi-Fi。")

        self.assertEqual(plan.text, "用 Chat G P T 分析 A I 和 C P U，再连接 Wi Fi。")

    def test_maps_pause_emphasis_and_emotion_for_fish_audio(self):
        plan = optimize_chinese_speech(
            "先看结论{pause:short}这点**非常重要**{pause:long}记住。",
            emotion="confident",
        )

        self.assertEqual(plan.text, "先看结论[pause]这点[emphasis]非常重要[long pause]记住。")
        self.assertEqual(plan.emotion, "confident")

    def test_uses_generic_markup_for_other_providers(self):
        plan = optimize_chinese_speech(
            "第一步{pause:short}点击**设置**。", provider="edge_tts"
        )

        self.assertEqual(plan.text, "第一步，点击“设置”。")

    def test_chinese_integer_units_and_zeroes(self):
        self.assertEqual(integer_to_chinese(10), "十")
        self.assertEqual(integer_to_chinese(101), "一百零一")
        self.assertEqual(integer_to_chinese(10_005), "一万零五")
        self.assertEqual(integer_to_chinese(120_030_004), "一亿二千零三万零四")

    def test_rejects_invalid_markup(self):
        with self.assertRaisesRegex(ChineseSpeechError, "unclosed"):
            optimize_chinese_speech("这是**重点")
        with self.assertRaisesRegex(ChineseSpeechError, "unsupported pause"):
            optimize_chinese_speech("稍等{pause:medium}")

    def test_config_defines_required_language_mappings(self):
        config = load_zh_voice_config()

        self.assertIn("ChatGPT", config["products"])
        self.assertIn("AI", config["acronyms"])
        self.assertEqual(config["locale"], "zh-CN")


if __name__ == "__main__":
    unittest.main()
