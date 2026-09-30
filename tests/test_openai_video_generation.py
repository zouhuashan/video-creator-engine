from pathlib import Path
import unittest
from unittest.mock import Mock

from adapters.video_generation import OpenAISoraVideo, VideoGenerationError, VideoGenerationRequest


class OpenAISoraVideoTests(unittest.TestCase):
    def test_retired_provider_never_uploads_or_charges_even_with_a_key(self):
        opener = Mock()
        request = VideoGenerationRequest((Path('not-needed.png'),), Path('out.mp4'), model='sora-2')
        for key in ('', 'test-key'):
            with self.assertRaisesRegex(VideoGenerationError, '2026-09-24'):
                OpenAISoraVideo(api_key=key, opener=opener).generate(request)
        opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
