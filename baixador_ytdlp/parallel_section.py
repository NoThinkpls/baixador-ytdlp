"""Trecho longo do YouTube baixado em partes paralelas.

Medido em 29/09/2026: cada FFmpeg lê o trecho numa conexão só, a ~5 MB/s (HLS) ou
~2x o tempo real (DASH). Quatro FFmpeg lado a lado levam o mesmo tempo que um para
quatro vezes mais vídeo. Aqui o intervalo é dividido em partes de ~5 min, cada uma
baixada por um yt-dlp próprio (com ``--download-sections``) e emendada com
``ffmpeg -f concat -c copy``. As emendas caem no quadro-chave: cada parte tem a
duração pedida e a junção só repete um quadro (33 ms) por emenda.

Se qualquer parte falhar, o download volta ao caminho normal de um processo só.
"""
from __future__ import annotations

import dataclasses
import shutil
import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from .config import Settings
from .diagnostics import log_event
from .downloader import (
    DownloadError, DownloadOptions, DownloadRunner, Progress, _is_youtube_url, _time_seconds,
)
from .tools import Toolchain, run_hidden

MIN_PARALLEL_SECONDS = 600   # abaixo disso o ganho não paga a emenda
PIECE_SECONDS = 300          # tamanho-alvo de cada parte
MAX_PIECES = 6               # conexões simultâneas ao servidor


def plan_pieces(opts: DownloadOptions, cfg: Settings) -> list[tuple[int, int]]:
    """Divide o trecho em partes ``(início, fim)`` em segundos, ou ``[]`` se não vale."""
    if opts.audio_only or opts.playlist or not _is_youtube_url(opts.url):
        return []
    # SponsorBlock e legendas mexem no arquivo inteiro; não dá para aplicar por parte.
    if cfg.sponsorblock or cfg.write_subs:
        return []
    start = _time_seconds(opts.section_start) if opts.section_start.strip() else 0.0
    if opts.section_end.strip():
        end = _time_seconds(opts.section_end)
    elif opts.media_duration > 0:
        end = opts.media_duration
    else:
        return []
    total = end - start
    if total < MIN_PARALLEL_SECONDS:
        return []
    count = min(MAX_PIECES, int(total // PIECE_SECONDS))
    if count < 2:
        return []
    bounds = [round(start + total * index / count) for index in range(count + 1)]
    return list(zip(bounds[:-1], bounds[1:]))


def create_runner(opts: DownloadOptions, cfg: Settings, tc: Toolchain):
    """Runner paralelo quando o trecho é longo; o normal nos demais casos."""
    pieces = plan_pieces(opts, cfg)
    if pieces:
        return ParallelSectionRunner(opts, cfg, tc, pieces)
    return DownloadRunner(opts, cfg, tc)


def _free_destination(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise DownloadError("Há arquivos demais com o mesmo nome na pasta de destino.")


class ParallelSectionRunner:
    """Mesma interface do ``DownloadRunner``, com as partes em paralelo."""

    def __init__(self, opts: DownloadOptions, cfg: Settings, tc: Toolchain,
                 pieces: list[tuple[int, int]]):
        self.opts, self.cfg, self.tc = opts, cfg, tc
        self.pieces = pieces
        self.files: list[Path] = []
        self.log: deque[str] = deque(maxlen=300)
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._subs: list[DownloadRunner] = []
        self._fallback: DownloadRunner | None = None
        self._percents = [0.0] * len(pieces)

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            runners = list(self._subs) + ([self._fallback] if self._fallback else [])
        for runner in runners:
            runner.cancel()

    def tail(self, lines: int = 40) -> str:
        if self._fallback:
            return self._fallback.tail(lines)
        return "\n".join(list(self.log)[-lines:])

    def run(self, on_progress: Callable[[Progress], None]) -> list[Path]:
        if self._cancelled.is_set():
            return []
        try:
            files = self._run_parallel(on_progress)
        except Exception as exc:  # noqa: BLE001 - qualquer falha volta ao caminho simples
            if self._cancelled.is_set():
                return []
            log_event("Trecho em partes falhou (%s); baixando em um processo só", exc)
            self.log.append(f"Trecho em partes falhou: {exc}")
            return self._run_single(on_progress)
        self.files = files
        return files

    def _run_single(self, on_progress: Callable[[Progress], None]) -> list[Path]:
        runner = DownloadRunner(self.opts, self.cfg, self.tc)
        with self._lock:
            self._fallback = runner
        if self._cancelled.is_set():
            return []
        files = runner.run(on_progress)
        self.files = runner.files
        return files

    def _run_parallel(self, on_progress: Callable[[Progress], None]) -> list[Path]:
        base = Path(self.opts.output_dir)
        work = base / f".baixador-partes-{uuid.uuid4().hex[:8]}"
        # Cada parte só recorta; capa, metadados e capítulos por parte sumiriam na emenda.
        cfg = dataclasses.replace(
            self.cfg, embed_metadata=False, embed_thumbnail=False, embed_chapters=False,
            write_subs=False, embed_subs=False, sponsorblock=False)
        count = len(self.pieces)
        log_event("Trecho longo dividido em %s partes paralelas: %s", count, self.pieces)
        bounds = self._aligned_bounds(cfg, work)
        subs = []
        for index in range(count):
            # O corte inclui o quadro do instante final: 20 ms a menos (menos de um quadro
            # a 30 fps) evitam repetir, no fim de cada parte, o quadro-chave com que a
            # seguinte começa.
            end = bounds[index + 1] - (0.02 if index < count - 1 else 0.0)
            piece_opts = dataclasses.replace(
                self.opts, output_dir=str(work / str(index)), repeat_index=0,
                section_start=f"{bounds[index]:.3f}", section_end=f"{end:.3f}")
            subs.append(DownloadRunner(piece_opts, cfg, self.tc))
        with self._lock:
            self._subs = subs
        try:
            self._emit(on_progress, "Baixando %d partes em paralelo…" % count)
            results: dict[int, list[Path]] = {}
            with ThreadPoolExecutor(max_workers=count) as pool:
                futures = {
                    pool.submit(sub.run, self._piece_callback(index, on_progress)): index
                    for index, sub in enumerate(subs)
                }
                try:
                    for future in as_completed(futures):
                        results[futures[future]] = future.result()
                except BaseException:
                    self.cancel_subs()
                    raise
            if self._cancelled.is_set():
                return []
            ordered: list[Path] = []
            for index in range(count):
                found = [path for path in results.get(index, []) if path.exists()]
                if len(found) != 1:
                    raise DownloadError(f"A parte {index + 1} não gerou um arquivo único.")
                ordered.append(found[0])
            return [self._join(ordered, work, base, on_progress)]
        finally:
            with self._lock:
                self._subs = []
            shutil.rmtree(work, ignore_errors=True)

    def _first_pts(self, path: Path) -> float:
        """Timestamp do primeiro pacote de vídeo (negativo quando há sobra antes do corte)."""
        ffprobe = getattr(self.tc, "ffprobe", None) or Path(self.tc.ffmpeg).with_name("ffprobe")
        result = run_hidden([str(ffprobe), "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "packet=pts_time", "-read_intervals", "%+#1",
                             "-of", "csv=p=0", str(path)], timeout=120)
        return float(result.stdout.strip().splitlines()[0].strip(","))

    def _aligned_bounds(self, cfg: Settings, work: Path) -> list[float]:
        """Fronteiras das partes ajustadas aos quadros-chave.

        Com ``-ss`` e cópia, o FFmpeg começa no quadro-chave anterior ao pedido e o
        MP4 esconde a sobra numa lista de edição; ao emendar com ``-c copy`` a sobra
        reaparece e repete ~2 s da parte anterior. Um corte de 1 s em cada emenda mostra
        onde está o quadro-chave (o primeiro timestamp fica negativo); as partes passam
        a começar e terminar exatamente nele.
        """
        starts = [float(start) for start, _ in self.pieces]
        bounds = starts + [float(self.pieces[-1][1])]
        seams = range(1, len(self.pieces))

        def probe(index: int) -> float:
            seam = starts[index]
            probe_opts = dataclasses.replace(
                self.opts, output_dir=str(work / f"k{index}"), repeat_index=0,
                section_start=f"{seam:.3f}", section_end=f"{seam + 1:.3f}")
            sub = DownloadRunner(probe_opts, cfg, self.tc)
            with self._lock:
                self._subs.append(sub)
            files = sub.run(lambda progress: None)
            if self._cancelled.is_set():
                raise DownloadError("Cancelado")
            if len(files) != 1:
                raise DownloadError("A sonda do quadro-chave não gerou um arquivo.")
            offset = self._first_pts(files[0])
            if not -30.0 <= offset <= 0.0:
                raise DownloadError(f"Quadro-chave fora do esperado ({offset}).")
            return round(seam + offset, 3)

        self._emit_stage("Localizando os quadros-chave das emendas…")
        with ThreadPoolExecutor(max_workers=max(1, len(self.pieces) - 1)) as pool:
            for index, value in zip(seams, pool.map(probe, seams)):
                bounds[index] = value
        with self._lock:
            self._subs = []
        return bounds

    def cancel_subs(self) -> None:
        with self._lock:
            runners = list(self._subs)
        for runner in runners:
            runner.cancel()

    def _piece_callback(self, index: int, on_progress: Callable[[Progress], None]):
        def callback(prog: Progress) -> None:
            if prog.status == "cancelled":
                return
            with self._lock:
                self._percents[index] = 100.0 if prog.status == "finished" else prog.percent
                percent = sum(self._percents) / len(self._percents)
            self._emit(on_progress, "Baixando %d partes em paralelo…" % len(self.pieces),
                       min(98.0, percent))
        return callback

    def _emit_stage(self, stage: str) -> None:
        log_event(stage)

    @staticmethod
    def _emit(on_progress: Callable[[Progress], None], stage: str, percent: float = 0.0) -> None:
        on_progress(Progress(status="processing", percent=percent, stage=stage))

    def _join(self, pieces: list[Path], work: Path, base: Path,
              on_progress: Callable[[Progress], None]) -> Path:
        self._emit(on_progress, "Juntando as partes…", 99.0)
        listing = work / "partes.txt"
        lines = []
        for path in pieces:
            quoted = str(path).replace("\\", "/").replace("'", "'\\''")
            lines.append(f"file '{quoted}'\n")
        listing.write_text("".join(lines), encoding="utf-8")
        final = _free_destination(base / pieces[0].name)
        result = run_hidden([
            str(self.tc.ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(final),
        ], timeout=3600)
        if result.returncode != 0 or not final.exists():
            final.unlink(missing_ok=True)
            raise DownloadError("O FFmpeg não conseguiu juntar as partes: "
                                + (result.stderr or "").strip()[-300:])
        on_progress(Progress(status="finished", percent=100.0))
        return final
