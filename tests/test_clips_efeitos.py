"""Efeitos automáticos dos cortes: whoosh nas trocas de assunto, pop e zoom na ênfase."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp import effects
from baixador_ytdlp.clips import ClipOptions, ClipRange, filter_graph, remap_words, render_command
from baixador_ytdlp.effects import Effect
from baixador_ytdlp.tools import Toolchain

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


def _word(text: str, start: float, level: float = -20.0) -> dict:
    return {"text": text, "start": start, "end": start + 0.3, "level": level}


class PlanoTests(unittest.TestCase):
    def test_emendas_no_tempo_final_com_a_pausa_removida(self) -> None:
        self.assertEqual(effects.cut_points([(0.0, 2.0), (3.5, 5.0), (5.4, 9.0)]),
                         [(2.0, 1.5), (3.5, 0.40000000000000036)])

    def test_whoosh_so_em_pausa_longa_e_espacado(self) -> None:
        # Pausas de 1,5 s em 2 s e 4 s (perto demais) e uma curta em 8 s.
        intervals = [(0.0, 2.0), (3.5, 5.5), (7.0, 11.0), (11.3, 20.0)]
        plan = effects.plan_effects(intervals, [], 17.2)
        self.assertEqual([effect.kind for effect in plan], ["whoosh"])
        self.assertAlmostEqual(plan[0].time, 2.0 - effects.WHOOSH_SECONDS * effects.WHOOSH_PEAK)

    def test_nada_colado_no_comeco_ou_no_fim(self) -> None:
        plan = effects.plan_effects([(0.0, 0.5), (2.0, 5.0)], [], 3.5)
        self.assertEqual(plan, [])

    def test_enfase_e_a_palavra_bem_mais_alta(self) -> None:
        words = [_word(f"palavra{i}", i * 0.5) for i in range(30)]
        words[10] = _word("IMPORTANTE", 5.0, level=-8.0)
        words[11] = _word("é", 5.5, level=-5.0)            # alta, mas curta demais
        chosen = effects.emphasis_words(words, 15.0)
        self.assertEqual([word["text"] for word in chosen], ["IMPORTANTE"])

    def test_exclamacao_conta_como_enfase(self) -> None:
        words = [_word(f"palavra{i}", i * 0.5) for i in range(30)]
        words[6] = _word("incrível!", 3.0)
        self.assertEqual([w["text"] for w in effects.emphasis_words(words, 15.0)], ["incrível!"])

    def test_no_maximo_uma_enfase_a_cada_sete_segundos(self) -> None:
        words = [_word(f"forte{i}", i * 1.0, level=-5.0 if i % 2 else -25.0) for i in range(20)]
        chosen = effects.emphasis_words(words, 20.0)
        self.assertLessEqual(len(chosen), 2)
        starts = [word["start"] for word in chosen]
        self.assertTrue(all(b - a >= effects.EMPHASIS_EVERY for a, b in zip(starts, starts[1:], strict=False)))

    def test_sem_volume_medido_nao_ha_enfase(self) -> None:
        self.assertEqual(effects.emphasis_words([{"text": "oi!", "start": 2.0, "end": 2.3}],
                                                10.0), [])

    def test_pop_nao_encavala_com_whoosh(self) -> None:
        intervals = [(0.0, 3.0), (4.5, 12.0)]
        plan = effects.plan_effects(intervals, [_word("agora", 3.1)], 10.5)
        self.assertEqual([effect.kind for effect in plan], ["whoosh"])

    def test_remap_mantem_o_volume_da_palavra(self) -> None:
        moved = remap_words([_word("oi", 3.0, level=-7.0)], [(0.0, 1.0), (2.5, 4.0)])
        self.assertEqual(moved[0]["level"], -7.0)
        self.assertAlmostEqual(moved[0]["start"], 1.5)


class SonsTests(unittest.TestCase):
    def test_sons_curtos_e_audiveis(self) -> None:
        for sound, seconds in ((effects.whoosh_sound(), effects.WHOOSH_SECONDS),
                               (effects.pop_sound(), effects.POP_SECONDS)):
            self.assertEqual(len(sound), int(seconds * effects.SAMPLE_RATE))
            self.assertGreater(float(np.abs(sound).max()), 0.3)
            self.assertLessEqual(float(np.abs(sound).max()), 1.0)

    def test_grava_so_os_sons_usados(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = effects.write_sounds(Path(tmp), [Effect(1.0, "pop")])
            self.assertEqual(list(files), ["pop"])
            samples, rate = effects.read_wav(files["pop"])
            self.assertEqual(rate, effects.SAMPLE_RATE)
            self.assertGreater(len(samples), 0)


class GrafoTests(unittest.TestCase):
    def test_sons_somados_a_voz_antes_do_volume_equilibrado(self) -> None:
        graph = filter_graph([(0.0, 2.0), (3.5, 6.0)], "crop", None, normalize_audio=True,
                             effects=[Effect(1.73, "whoosh"), Effect(3.0, "pop")],
                             effect_inputs={"pop": 1, "whoosh": 2})
        self.assertIn("[2:a]asplit=outputs=1[sxwhoosh0]", graph)
        self.assertIn("adelay=delays=1730:all=1", graph)
        self.assertIn("[ac0][sdpop0][sdwhoosh0]amix=inputs=3:duration=first:normalize=0[ac1]",
                      graph)
        self.assertIn("[ac1]loudnorm", graph)

    def test_sem_efeitos_o_audio_continua_igual(self) -> None:
        graph = filter_graph([(0.0, 2.0)], "crop", None)
        self.assertNotIn("amix", graph)
        self.assertIn("[vc][ac]", graph)

    def test_zoom_na_enfase(self) -> None:
        graph = filter_graph([(0.0, 5.0)], "crop", None, punch=[(2.0, 2.6)])
        self.assertIn("between(t,2.000,2.599)", graph)
        self.assertIn("scale=1242:2208", graph)

    def test_sons_entram_como_entradas_extras(self) -> None:
        command = render_command(Path("ffmpeg"), Path("/a/origem.mp4"), 0, 5, [(0.0, 5.0)],
                                 "crop", None, Path("/b/saida.mp4"),
                                 sounds={"whoosh": Path("/t/w.wav"), "pop": Path("/t/p.wav")},
                                 effects=[Effect(1.0, "pop")])
        inputs = [command[i + 1] for i, arg in enumerate(command) if arg == "-i"]
        self.assertEqual(inputs, [str(Path(path)) for path in
                                  ("/a/origem.mp4", "/t/p.wav", "/t/w.wav")])


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg não instalado")
class WorkerComEfeitosTests(unittest.TestCase):
    def test_corte_real_com_sons_e_zoom(self) -> None:
        from PySide6.QtCore import QCoreApplication

        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.workers import ClipWorker, TranscriptionWorker

        QCoreApplication.instance() or QCoreApplication([])
        # Fala contínua; a palavra em 9 s é dita bem mais alto, e há uma pausa de 2 s.
        words = [{"text": f"fala{i}", "start": i * 0.5, "end": i * 0.5 + 0.4}
                 for i in range(24) if not 8 <= i <= 11]

        def fake_run(worker: TranscriptionWorker) -> None:
            worker.opts.output_path.write_text(json.dumps(
                {"segments": [{"start": 0, "end": 12, "text": "", "words": words}]}),
                encoding="utf-8")
            worker.finished_ok.emit(str(worker.opts.output_path))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "origem.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=25", "-f", "lavfi", "-i",
                            "sine=f=220:sample_rate=48000", "-filter_complex",
                            "[1:a]volume='if(between(t,9,9.4),1,0.1)':eval=frame[a]",
                            "-map", "0:v", "-map", "[a]", "-t", "12", "-c:v", "libx264",
                            "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True)
            tc = Toolchain(ytdlp=root / "yt-dlp", ffmpeg=Path(FFMPEG), ffprobe=Path(FFPROBE),
                           bin_dir=root)
            options = ClipOptions(source=str(source), ranges=(ClipRange(0.0, 12.0, ""),),
                                  output_dir=root / "saida", framing="crop",
                                  sound_effects=True, emphasis_zoom=True)
            worker = ClipWorker(options, tc, Settings())
            results: dict = {}
            worker.finished_ok.connect(lambda paths: results.update(ok=paths))
            worker.failed.connect(lambda message: results.update(error=message))
            commands: list[list[str]] = []
            real_ffmpeg = ClipWorker._ffmpeg

            def spy(self, command, *args):
                commands.append(command)
                return real_ffmpeg(self, command, *args)

            with patch.object(TranscriptionWorker, "run", fake_run), \
                    patch.object(ClipWorker, "_ffmpeg", spy), \
                    patch("baixador_ytdlp.workers.preferred_video_encoder", return_value=""):
                worker.run()
            self.assertNotIn("error", results, results.get("error"))
            render = next(command for command in commands if "-filter_complex" in command)
            graph = render[render.index("-filter_complex") + 1]
            self.assertIn("amix", graph)          # whoosh na pausa de 2 s e pop na palavra alta
            self.assertIn("efeito-whoosh.wav", " ".join(render))
            self.assertIn("efeito-pop.wav", " ".join(render))
            self.assertIn("[vpm]", graph)          # zoom na ênfase
            self.assertTrue(Path(results["ok"][0]).is_file())


if __name__ == "__main__":
    unittest.main()
