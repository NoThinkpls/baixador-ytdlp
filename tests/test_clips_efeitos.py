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

from baixador_ytdlp import effects, sfx
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
        self.assertAlmostEqual(plan[0].time, 2.0)   # o instante da emenda; ``schedule`` adianta

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

    def test_sem_zoom_na_enfase_nao_ha_pop(self) -> None:
        # Pop sem o zoom junto é um som solto, sem nada na tela: fica de fora.
        intervals = [(0.0, 3.0), (4.5, 20.0)]
        emphasis = [_word("agora", 10.0)]
        self.assertEqual([e.kind for e in effects.plan_effects(intervals, emphasis, 18.5)],
                         ["whoosh", "pop"])
        self.assertEqual([e.kind for e in effects.plan_effects(intervals, emphasis, 18.5,
                                                               pops=False)], ["whoosh"])

    def test_remap_mantem_o_volume_da_palavra(self) -> None:
        moved = remap_words([_word("oi", 3.0, level=-7.0)], [(0.0, 1.0), (2.5, 4.0)])
        self.assertEqual(moved[0]["level"], -7.0)
        self.assertAlmostEqual(moved[0]["start"], 1.5)


class SonsTests(unittest.TestCase):
    def test_cinco_sons_estereo_e_sem_estourar(self) -> None:
        for kind in sfx.SOUNDS:
            sound = sfx.MAKERS[kind]()
            self.assertEqual(sound.shape[1], 2, kind)
            self.assertGreater(len(sound), 0.08 * sfx.SAMPLE_RATE, kind)
            self.assertGreater(float(np.abs(sound).max()), 0.5, kind)
            self.assertLessEqual(float(np.abs(sound).max()), 0.9, kind)

    def test_impacto_se_ouve_no_celular_sem_ronco(self) -> None:
        # O impacto antigo era quase só grave abaixo de 120 Hz, que o celular não toca e
        # que no fone vira ronco; o corpo do som precisa estar na faixa audível.
        sound = sfx.impacto().mean(axis=1)
        spectrum = np.abs(np.fft.rfft(sound)) ** 2
        freqs = np.fft.rfftfreq(sound.size, 1 / sfx.SAMPLE_RATE)
        self.assertGreater(spectrum[freqs >= 120].sum() / spectrum.sum(), 0.35)
        self.assertLess(spectrum[freqs < 35].sum() / spectrum.sum(), 0.02)

    def test_subida_e_chiado_sem_tom_de_ficcao(self) -> None:
        # Nada de senoide subindo com vibrato: nenhuma frequência isolada domina o som.
        sound = sfx.subida().mean(axis=1)
        spectrum = np.abs(np.fft.rfft(sound)) ** 2
        band = spectrum[(np.fft.rfftfreq(sound.size, 1 / sfx.SAMPLE_RATE) > 100)]
        self.assertLess(float(band.max() / band.sum()), 0.002)

    def test_volume_do_som_acompanha_a_voz(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = {kind: path for kind, (path, _lead) in
                     sfx.prepare(Path(tmp), {"whoosh", "impacto"}).items()}
            quiet = sfx.matched_gains(files, -30.0)
            loud = sfx.matched_gains(files, -18.0)
            fixed = sfx.matched_gains(files, None)
        for kind in files:
            # 12 dB a mais na voz = som 4x mais forte, sempre abaixo de -6 dBFS no pico.
            self.assertAlmostEqual(loud[kind] / quiet[kind], 10 ** (12 / 20), delta=0.05)
            self.assertLessEqual(loud[kind] * 0.89, sfx.PEAK_LIMIT + 1e-3)
            self.assertEqual(fixed[kind], sfx.GAIN[kind])
        voice = sfx.voice_level(np.sin(np.arange(48000) / 48000 * 2 * np.pi * 300) * 0.1,
                                48000)
        self.assertAlmostEqual(voice, 20 * np.log10(0.1 / np.sqrt(2)), delta=0.5)
        self.assertIsNone(sfx.voice_level(np.zeros(48000), 48000))

    @unittest.skipUnless(FFMPEG, "FFmpeg não instalado")
    def test_som_da_pessoa_em_mp3_tambem_e_medido(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            own = Path(tmp) / "pop.mp3"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "sine=f=800:d=0.3:sample_rate=48000", "-af", "volume=0.9",
                            str(own)], check=True)
            gains = sfx.matched_gains({"pop": own}, -24.0)
        self.assertNotEqual(gains["pop"], sfx.GAIN["pop"])
        self.assertLess(gains["pop"], 0.5)

    def test_pico_do_whoosh_na_antecedencia(self) -> None:
        sound = sfx.whoosh()
        energy = (sound ** 2).sum(axis=1)
        window = int(0.02 * sfx.SAMPLE_RATE)
        smooth = np.convolve(energy, np.ones(window) / window, mode="same")
        peak = int(np.argmax(smooth)) / sfx.SAMPLE_RATE
        self.assertAlmostEqual(peak, sfx.lead_seconds("whoosh"), delta=0.06)

    def test_grava_so_os_sons_usados(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            files = sfx.prepare(Path(tmp), {"pop", "impacto"})
            self.assertEqual(sorted(files), ["impacto", "pop"])
            samples, rate = effects.read_wav(files["pop"][0])
            self.assertEqual(rate, sfx.SAMPLE_RATE)
            self.assertGreater(len(samples), 0)

    def test_som_da_pessoa_tem_prioridade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            own = Path(tmp) / "meus"
            own.mkdir()
            (own / "Impacto.MP3").write_bytes(b"x")
            (own / "leiame.txt").write_text("x")
            files = sfx.prepare(Path(tmp), {"impacto", "ding"}, own, duration_of=lambda _p: 2.0)
            self.assertEqual(files["impacto"], (own / "Impacto.MP3", 0.01))
            self.assertEqual(files["ding"][0].name, "efeito-ding.wav")
            # Subida da pessoa termina no ponto; whoosh tem o pico no meio.
            self.assertEqual(sfx.lead_seconds("subida", 2.0), 2.0)
            self.assertEqual(sfx.lead_seconds("whoosh", 2.0), 1.0)

    def test_arquivo_da_pessoa_ilegivel_volta_ao_padrao(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pop.wav").write_bytes(b"x")
            out = Path(tmp) / "saida"
            out.mkdir()
            files = sfx.prepare(out, {"pop"}, Path(tmp), duration_of=lambda _p: 0.0)
            self.assertEqual(files["pop"][0].name, "efeito-pop.wav")


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
    def _render(self, clip: ClipRange) -> tuple[dict, str, list[str]]:
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
            options = ClipOptions(source=str(source), ranges=(clip,),
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
            self.assertTrue(Path(results["ok"][0]).is_file())
        render = next(command for command in commands if "-filter_complex" in command)
        return results, render[render.index("-filter_complex") + 1], render

    def test_corte_real_com_sons_e_zoom(self) -> None:
        _results, graph, render = self._render(ClipRange(0.0, 12.0, ""))
        self.assertIn("amix", graph)          # whoosh na pausa de 2 s e pop na palavra alta
        self.assertIn("efeito-whoosh.wav", " ".join(render))
        self.assertIn("efeito-pop.wav", " ".join(render))
        self.assertIn("[vpm]", graph)          # zoom na ênfase

    def test_plano_da_ia_manda_nos_sons(self) -> None:
        from baixador_ytdlp.effects import Marker
        clip = ClipRange(0.0, 12.0, "", (Marker(10.5, "impacto", "fala21", True),
                                         Marker(5.0, "subida")))
        _results, graph, render = self._render(clip)
        joined = " ".join(render)
        self.assertIn("efeito-impacto.wav", joined)
        self.assertIn("efeito-subida.wav", joined)
        self.assertNotIn("efeito-pop.wav", joined)      # a regra automática não entra
        # fala21 começa em 10,5 s; com 1,70 s de pausa cortada, cai em 8,80 s (o fim da
        # fala antes da pausa ganha a folga maior de TAIL_PAD).
        self.assertIn("between(t,8.800,", graph)
        # Subida termina na emenda (4,18 s), que ganha o zoom: o som tem algo na tela.
        start = round((4.18 - sfx.SUBIDA_SECONDS) * 1000)
        self.assertIn(f"adelay=delays={start}:all=1", graph)
        self.assertIn("between(t,4.180,", graph)


if __name__ == "__main__":
    unittest.main()
