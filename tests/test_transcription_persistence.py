from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.transcription import Transcriber, TranscriptionOptions
from baixador_ytdlp.ui.i18n import set_language, tr


class TranscriptionPersistenceTests(unittest.TestCase):
    def _transcriber(self) -> Transcriber:
        return Transcriber(SimpleNamespace(), lambda _message: None, lambda _progress: None,
                           force_cpu=True)

    @staticmethod
    def _options(model: str = "medium") -> TranscriptionOptions:
        return TranscriptionOptions(Path("input.mp4"), Path("output.srt"), model_size=model)

    def test_same_model_stays_loaded_for_next_queue_item(self) -> None:
        transcriber = self._transcriber()
        transcriber.model = object()
        transcriber._loaded_model_size = "medium"
        transcriber._loaded_model_profile = (
            transcriber.backend, transcriber.device, transcriber.compute_type,
        )
        with patch.object(transcriber, "_load_model") as load:
            transcriber._prepare_model_for(self._options())
        load.assert_not_called()

    def test_model_change_loads_only_the_new_model(self) -> None:
        transcriber = self._transcriber()
        transcriber.model = object()
        transcriber._loaded_model_size = "medium"
        transcriber._loaded_model_profile = (
            transcriber.backend, transcriber.device, transcriber.compute_type,
        )
        with patch.object(transcriber, "_load_model") as load:
            transcriber._prepare_model_for(self._options("small"))
        load.assert_called_once_with("small")

    def test_english_catalog_is_opt_in(self) -> None:
        try:
            set_language("en")
            self.assertEqual(tr("Baixar"), "Download")
        finally:
            set_language("pt-BR")


if __name__ == "__main__":
    unittest.main()

