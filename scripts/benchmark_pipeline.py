import argparse
import gzip
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]


ROOT_DIR = Path(__file__).resolve().parents[1]

ALL_METRICS: List[Dict[str, Any]] = []
ALL_RUN_SUMMARIES: List[Dict[str, Any]] = []
SESSION_DURATION_SEC: Optional[float] = None
QUIET: bool = False

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from settings import settings  # type: ignore  # noqa: E402
from utils.recording import (  # type: ignore  # noqa: E402
    chunk_video,
    ffmpeg_chunk_video,
    ffmpeg_get_video_duration,
    ffmpeg_slow_down_video,
    get_recording_duration,
    is_ffmpeg_available,
    slow_down_video,
)
from utils.rrweb import RRWebSessionUtils  # type: ignore  # noqa: E402


def _measure_step(name: str, func: Callable[[], Any]) -> Dict[str, Any]:
    """Measure wall time, CPU usage and (approximate) memory/IO for a step."""
    t0 = time.perf_counter()

    if resource is not None:
        ru_self_before = resource.getrusage(resource.RUSAGE_SELF)
        ru_child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    else:
        ru_self_before = None
        ru_child_before = None

    result = func()
    t1 = time.perf_counter()

    metrics: Dict[str, Any] = {
        "step": name,
        "wall_time_s": round(t1 - t0, 3),
    }

    if (
        resource is not None
        and ru_self_before is not None
        and ru_child_before is not None
    ):
        ru_self_after = resource.getrusage(resource.RUSAGE_SELF)
        ru_child_after = resource.getrusage(resource.RUSAGE_CHILDREN)

        user_cpu = (
            ru_self_after.ru_utime
            + ru_child_after.ru_utime
            - ru_self_before.ru_utime
            - ru_child_before.ru_utime
        )
        sys_cpu = (
            ru_self_after.ru_stime
            + ru_child_after.ru_stime
            - ru_self_before.ru_stime
            - ru_child_before.ru_stime
        )
        # Note: .ru_maxrss is in KB on Linux and bytes on macOS; scale for cross-compat
        maxrss_scale = 1024 if sys.platform == "darwin" else 1
        maxrss_before = ru_self_before.ru_maxrss / maxrss_scale
        maxrss_after = ru_self_after.ru_maxrss / maxrss_scale
        metrics["cpu_user_s"] = round(user_cpu, 3)
        metrics["cpu_system_s"] = round(sys_cpu, 3)
        metrics["max_rss_kb"] = maxrss_after
        metrics["inblock_delta"] = (
            ru_self_after.ru_inblock
            + ru_child_after.ru_inblock
            - ru_self_before.ru_inblock
            - ru_child_before.ru_inblock
        )
        metrics["oublock_delta"] = (
            ru_self_after.ru_oublock
            + ru_child_after.ru_oublock
            - ru_self_before.ru_oublock
            - ru_child_before.ru_oublock
        )
        metrics["delta_rss_kb"] = max(0, maxrss_after - maxrss_before)

    ALL_METRICS.append(metrics)

    if not QUIET:
        print(f"\n=== {name} ===")
        print(json.dumps(metrics, indent=2))
    return {"result": result, "metrics": metrics}


def reset_metrics() -> None:
    ALL_METRICS.clear()
    global SESSION_DURATION_SEC
    SESSION_DURATION_SEC = None


def summarize_current_run() -> Dict[str, Any]:
    if not ALL_METRICS:
        return {}

    total_wall = round(sum(float(m.get("wall_time_s", 0.0)) for m in ALL_METRICS), 3)
    total_cpu = 0.0
    max_rss_kb_max = 0.0
    for m in ALL_METRICS:
        total_cpu += float(m.get("cpu_user_s", 0.0)) + float(m.get("cpu_system_s", 0.0))
        step_max_rss_kb = float(m.get("max_rss_kb", 0.0))
        max_rss_kb_max = max(max_rss_kb_max, step_max_rss_kb)
    total_cpu = round(total_cpu, 3)

    approx_sessions_per_hour = round(3600.0 / total_cpu, 1) if total_cpu > 0 else None

    session_duration = SESSION_DURATION_SEC
    cpu_per_min_total = None
    approx_1min_sessions_per_hour_total = None
    if session_duration and session_duration > 0 and total_cpu > 0:
        cpu_per_min_total = round(
            total_cpu / (session_duration / 60.0),
            3,
        )
        approx_1min_sessions_per_hour_total = round(
            3600.0 / cpu_per_min_total,
            1,
        )

    return {
        "total_wall_time_s": total_wall,
        "total_cpu_time_s": total_cpu,
        "approx_sessions_per_hour_one_vcpu_total": approx_sessions_per_hour,
        "max_memory_used_kb": max_rss_kb_max,  # Only this will be meaningful for concurrency
        "total_memory_used_kb": sum(m.get("max_rss_kb", 0) for m in ALL_METRICS),
        "cpu_time_per_minute_total": cpu_per_min_total,
        "approx_1min_sessions_per_hour_one_vcpu_total": approx_1min_sessions_per_hour_total,
        "session_duration_seconds": session_duration,
        "pipelines": {},
    }


def summarize_all_runs(run_summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not run_summaries:
        return {}
    num_runs = len(run_summaries)

    run_peaks = sorted(
        [r.get("max_memory_used_kb", 0) for r in run_summaries], reverse=True
    )
    total_memory_used_kb_sum = sum(
        r.get("total_memory_used_kb", 0) for r in run_summaries
    )
    total_wall = sum(float(r.get("total_wall_time_s", 0.0)) for r in run_summaries)
    total_cpu = sum(float(r.get("total_cpu_time_s", 0.0)) for r in run_summaries)

    avg_wall = round(total_wall / num_runs, 3)
    avg_cpu = round(total_cpu / num_runs, 3)

    summary: Dict[str, Any] = {
        "num_runs": num_runs,
        "run_peaks_memory_used_kb": run_peaks,  # Ordered descending
        "max_memory_used_kb": (
            run_peaks[0] if run_peaks else 0
        ),  # Max of the peaks, for single concurrency
        "total_memory_used_kb": total_memory_used_kb_sum,
        "total_cpu_time": total_cpu,
        "total_wall_time": total_wall,
        "avg_total_wall_time_s": avg_wall,
        "avg_total_cpu_time_s": avg_cpu,
    }

    return summary


def _ensure_assets(assets_dir: Path) -> Dict[str, Path]:
    events_gzip = assets_dir / "events.json.gzip"
    events_json = assets_dir / "events.json"
    video = assets_dir / "video.mp4"

    if not events_gzip.exists():
        raise FileNotFoundError(f"events.json.gzip not found in {assets_dir}")
    if not events_json.exists():
        if not QUIET:
            print(f"events.json not found in {assets_dir}")
    if not video.exists():
        if not QUIET:
            print(f"video.mp4 not found in {assets_dir}")

    return {
        "events_gzip": events_gzip,
        "events_json": events_json,
        "video": video,
    }


def benchmark_rrvideo(
    tmp_dir: Path,
    events_gzip: Optional[Path],
    events_json: Optional[Path],
) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if events_gzip is not None and events_gzip.exists():
        decompressed_path = tmp_dir / "events_from_gzip.json"

        def _decompress() -> None:
            with (
                gzip.open(events_gzip, "rb") as f_in,
                open(decompressed_path, "wb") as f_out,
            ):
                shutil.copyfileobj(f_in, f_out)

        _measure_step("decompress_events_json_gzip", _decompress)
        input_events = decompressed_path
    elif events_json is not None and events_json.exists():
        input_events = events_json
    else:
        raise FileNotFoundError("No rrweb events JSON found to feed rrvideo")

    def _run_rrvideo() -> Dict[str, Any]:
        session = RRWebSessionUtils(str(input_events))
        result = session.convert_events_to_video()
        if not result.get("success"):
            raise RuntimeError(f"rrvideo failed: {result.get('error') or result}")
        return result

    rr_res = _measure_step("rrvideo_convert_events_to_video", _run_rrvideo)
    rr_output = rr_res["result"]
    output_path = Path(rr_output["output_path"])
    if not QUIET:
        print(
            f"rrvideo output: {output_path} "
            f"(size={output_path.stat().st_size / (1024 * 1024):.2f} MB)"
        )
    return output_path


def benchmark_slowdown(
    tmp_dir: Path,
    source_video: Path,
    slowdown_factor: float,
    backend: str,
) -> Dict[str, Optional[Path]]:
    tmp_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Optional[Path]] = {"ffmpeg": None, "opencv": None}

    if slowdown_factor <= 1.0:
        print(
            "Slowdown factor <= 1.0; skipping slowdown benchmarks. "
            "Use --slowdown-factor > 1.0 to test slowdown cost."
        )
        return results

    use_ffmpeg = backend in {"ffmpeg", "both"}
    use_opencv = backend in {"opencv", "both"}

    if use_ffmpeg and is_ffmpeg_available():
        ffmpeg_out = tmp_dir / "video_slowed_ffmpeg.mp4"

        def _ffmpeg_slow() -> None:
            ffmpeg_slow_down_video(
                str(source_video),
                str(ffmpeg_out),
                slowdown_factor=slowdown_factor,
            )

        _measure_step("slowdown_ffmpeg", _ffmpeg_slow)
        if not QUIET:
            print(
                f"FFmpeg slowed video: {ffmpeg_out} "
                f"(size={ffmpeg_out.stat().st_size / (1024 * 1024):.2f} MB)"
            )
        results["ffmpeg"] = ffmpeg_out
    elif use_ffmpeg:
        print("FFmpeg not available on PATH; skipping FFmpeg slowdown benchmark.")

    if use_opencv:
        opencv_out = tmp_dir / "video_slowed_opencv.mp4"

        def _opencv_slow() -> None:
            slow_down_video(
                str(source_video),
                str(opencv_out),
                slowdown_factor=slowdown_factor,
            )

        _measure_step("slowdown_opencv", _opencv_slow)
        if not QUIET:
            print(
                f"OpenCV slowed video: {opencv_out} "
                f"(size={opencv_out.stat().st_size / (1024 * 1024):.2f} MB)"
            )
        results["opencv"] = opencv_out

    return results


def benchmark_chunking(
    tmp_dir: Path,
    source_video: Path,
    chunk_size_seconds: int,
    backend: str,
) -> None:
    tmp_dir.mkdir(parents=True, exist_ok=True)

    use_ffmpeg = backend in {"ffmpeg", "both"}
    use_opencv = backend in {"opencv", "both"}

    if use_ffmpeg and is_ffmpeg_available():

        def _ffmpeg_chunk() -> Any:
            return ffmpeg_chunk_video(
                str(source_video),
                chunk_size_seconds=chunk_size_seconds,
                output_dir=str(tmp_dir),
            )

        ffmpeg_res = _measure_step("chunk_ffmpeg", _ffmpeg_chunk)
        chunks = ffmpeg_res["result"]
        total_size = 0
        for chunk_path, _, _ in chunks:
            total_size += os.path.getsize(chunk_path)
        if not QUIET:
            print(
                f"FFmpeg chunked into {len(chunks)} chunks "
                f"(total_size={total_size / (1024 * 1024):.2f} MB)"
            )
    elif use_ffmpeg:
        print("FFmpeg not available on PATH; skipping FFmpeg chunking benchmark.")

    if use_opencv:

        def _opencv_chunk() -> Any:
            return chunk_video(
                str(source_video),
                chunk_size_seconds=chunk_size_seconds,
                output_dir=str(tmp_dir),
            )

        opencv_res = _measure_step("chunk_opencv", _opencv_chunk)
        chunks = opencv_res["result"]
        total_size = 0
        for chunk_path, _, _ in chunks:
            total_size += os.path.getsize(chunk_path)
        if not QUIET:
            print(
                f"OpenCV chunked into {len(chunks)} chunks "
                f"(total_size={total_size / (1024 * 1024):.2f} MB)"
            )


def run_pipeline_once(
    assets_dir: Path,
    tmp_dir: Path,
    mode: str,
    slowdown_factor: float,
    chunk_size: int,
    backend: str,
) -> None:
    paths = _ensure_assets(assets_dir)
    rrvideo_output: Optional[Path] = None
    global SESSION_DURATION_SEC

    if "all" in mode or "rrvideo" in mode:
        rrvideo_output = benchmark_rrvideo(
            tmp_dir=tmp_dir,
            events_gzip=paths["events_gzip"] if paths["events_gzip"].exists() else None,
            events_json=paths["events_json"] if paths["events_json"].exists() else None,
        )
        try:
            if rrvideo_output is not None:
                if is_ffmpeg_available():
                    duration = ffmpeg_get_video_duration(str(rrvideo_output))
                else:
                    duration = get_recording_duration(str(rrvideo_output))
                SESSION_DURATION_SEC = float(duration)
        except Exception:
            SESSION_DURATION_SEC = None

    slowed_paths: Dict[str, Optional[Path]] = {"ffmpeg": None, "opencv": None}
    if "all" in mode or "slowdown" in mode:
        source_for_slowdown = rrvideo_output or paths["video"]
        slowed_paths = benchmark_slowdown(
            tmp_dir=tmp_dir,
            source_video=source_for_slowdown,
            slowdown_factor=slowdown_factor,
            backend=backend,
        )

    if "all" in mode or "chunk" in mode:
        source_for_chunk = (
            slowed_paths.get("ffmpeg")
            or slowed_paths.get("opencv")
            or rrvideo_output
            or paths["video"]
        )
        assert source_for_chunk is not None
        benchmark_chunking(
            tmp_dir=tmp_dir,
            source_video=source_for_chunk,
            chunk_size_seconds=chunk_size,
            backend=backend,
        )


def _worker_entry(
    assets_dir_str: str,
    tmp_root_str: str,
    mode: str,
    slowdown_factor: float,
    chunk_size: int,
    backend: str,
    run_index: int,
) -> Dict[str, Any]:
    assets_dir = Path(assets_dir_str)
    tmp_root = Path(tmp_root_str)
    run_tmp_dir = tmp_root / f"run_{run_index}"
    run_tmp_dir.mkdir(parents=True, exist_ok=True)

    reset_metrics()
    run_pipeline_once(
        assets_dir=assets_dir,
        tmp_dir=run_tmp_dir,
        mode=mode,
        slowdown_factor=slowdown_factor,
        chunk_size=chunk_size,
        backend=backend,
    )
    return summarize_current_run()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark heavy recording pipeline operations "
            "(rrvideo conversion, slowdown, chunking) "
            "against the sample assets in tests/assets/."
        )
    )
    parser.add_argument(
        "--assets-dir",
        type=str,
        default=str(ROOT_DIR / "scripts" / "assets"),
        help="Directory containing events.json(.gzip) and video.mp4 "
        "(default: app/scripts/assets under project root).",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["all", "rrvideo", "slowdown", "chunk"],
        default="all",
        help="Which part of the pipeline to benchmark.",
    )
    parser.add_argument(
        "--slowdown-factor",
        type=float,
        default=None,
        help="Slowdown factor for slowdown benchmarks "
        "(default: settings.SLOW_DOWN_FACTOR or 2.0 if that is <= 1.0).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Chunk size in seconds for chunking benchmarks "
        "(default: settings.RECORDING_INTERVAL_DURATION).",
    )
    parser.add_argument(
        "--tmp-dir",
        type=str,
        default=str(ROOT_DIR / "tmp" / "benchmark_pipeline"),
        help="Directory to store temporary benchmark outputs.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of times to run the benchmark pipeline.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of worker processes to use when running multiple runs.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-step logs; only print per-run and all-runs summaries.",
    )
    parser.add_argument(
        "--video-backend",
        type=str,
        choices=["ffmpeg", "opencv", "both"],
        default="ffmpeg",
        help="Video processing backend to benchmark (default: ffmpeg).",
    )

    args = parser.parse_args()

    assets_dir = Path(args.assets_dir).resolve()
    tmp_root = Path(args.tmp_dir).resolve()
    tmp_root.mkdir(parents=True, exist_ok=True)

    slowdown_factor: float
    if args.slowdown_factor is not None:
        slowdown_factor = args.slowdown_factor
    else:
        slowdown_factor = settings.SLOW_DOWN_FACTOR or 2.0
        if slowdown_factor <= 1.0:
            slowdown_factor = 2.0

    chunk_size = args.chunk_size or settings.RECORDING_INTERVAL_DURATION
    backend = args.video_backend

    global QUIET
    QUIET = args.quiet

    print(
        json.dumps(
            {
                "assets_dir": str(assets_dir),
                "tmp_dir_root": str(tmp_root),
                "mode": args.mode,
                "slowdown_factor": slowdown_factor,
                "chunk_size_seconds": chunk_size,
                "runs": args.runs,
                "concurrency": args.concurrency,
                "video_backend": backend,
            },
            indent=2,
        )
    )
    process_start_time = time.perf_counter()

    if args.concurrency <= 1:
        for run_index in range(1, args.runs + 1):
            print(f"\n### RUN {run_index}/{args.runs} (sequential) ###")
            run_tmp_dir = tmp_root / f"run_{run_index}"
            run_tmp_dir.mkdir(parents=True, exist_ok=True)

            reset_metrics()
            run_pipeline_once(
                assets_dir=assets_dir,
                tmp_dir=run_tmp_dir,
                mode=args.mode,
                slowdown_factor=slowdown_factor,
                chunk_size=chunk_size,
                backend=backend,
            )
            summary = summarize_current_run()
            if summary:
                ALL_RUN_SUMMARIES.append(summary)
                print("\n=== RUN SUMMARY ===")
                print(json.dumps(summary, indent=2))
    else:
        print(
            f"\nRunning {args.runs} runs with concurrency={args.concurrency} "
            f"using separate worker processes."
        )
        with ProcessPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {}
            for run_index in range(1, args.runs + 1):
                fut = executor.submit(
                    _worker_entry,
                    str(assets_dir),
                    str(tmp_root),
                    args.mode,
                    slowdown_factor,
                    chunk_size,
                    backend,
                    run_index,
                )
                futures[fut] = run_index

            for fut in as_completed(futures):
                run_index = futures[fut]
                summary = fut.result()
                ALL_RUN_SUMMARIES.append(summary)
                print(f"\n=== RUN {run_index} SUMMARY (concurrent) ===")
                print(json.dumps(summary, indent=2))

    if ALL_RUN_SUMMARIES:
        all_summary = summarize_all_runs(ALL_RUN_SUMMARIES)
        all_summary_sanitzed = {
            k: v for k, v in all_summary.items() if k != "run_peaks_memory_used_kb"
        }
        print("\n=== ALL RUNS SUMMARY ===")
        print(json.dumps(all_summary_sanitzed, indent=2))

        process_end_time = time.perf_counter()
        process_duration_s = round(process_end_time - process_start_time, 3)

        # Calculate per-session metrics (should be roughly constant regardless of concurrency)
        avg_cpu_per_session = all_summary.get("avg_total_cpu_time_s", 0)
        avg_wall_per_session = all_summary.get("avg_total_wall_time_s", 0)

        # Get session duration for normalization
        session_duration_sec = None
        if ALL_RUN_SUMMARIES and ALL_RUN_SUMMARIES[0].get("session_duration_seconds"):
            session_duration_sec = ALL_RUN_SUMMARIES[0].get("session_duration_seconds")

        # Memory analysis
        run_peaks = all_summary.get("run_peaks_memory_used_kb", [])
        max_concurrent = min(args.concurrency, len(run_peaks))
        worst_case_peak_kb = sum(run_peaks[:max_concurrent]) if run_peaks else 0
        worst_case_peak_mb = worst_case_peak_kb / 1024
        percent_of_2gb = (worst_case_peak_mb / 2048) * 100 if worst_case_peak_mb else 0

        # Calculate throughput metrics
        sessions_completed = all_summary.get("num_runs", 1)
        sessions_per_hour_at_1vcpu = (
            round(3600.0 / avg_cpu_per_session, 1) if avg_cpu_per_session > 0 else None
        )

        # Per-minute normalization
        cpu_per_minute = None
        sessions_per_hour_for_1min_session = None
        if (
            session_duration_sec
            and session_duration_sec > 0
            and avg_cpu_per_session > 0
        ):
            cpu_per_minute = round(
                avg_cpu_per_session / (session_duration_sec / 60.0), 3
            )
            sessions_per_hour_for_1min_session = (
                round(3600.0 / cpu_per_minute, 1) if cpu_per_minute > 0 else None
            )

        print("\n" + "=" * 80)
        print("CAPACITY ANALYSIS")
        print("=" * 80)

        print(
            f"\n📊 PER-SESSION METRICS (should be constant regardless of concurrency):"
        )
        print(
            f"   • Average CPU time per session: {avg_cpu_per_session:.2f} CPU-seconds"
        )
        print(f"   • Average wall time per session: {avg_wall_per_session:.2f} seconds")
        if session_duration_sec:
            print(
                f"   • Session video duration: {session_duration_sec:.1f} seconds ({session_duration_sec/60:.2f} minutes)"
            )
            if cpu_per_minute:
                print(
                    f"   • CPU time per minute of video: {cpu_per_minute:.2f} CPU-seconds/min"
                )

        print(f"\n💻 ON A 1 vCPU INSTANCE (your production target):")
        if sessions_per_hour_at_1vcpu:
            print(f"   • Max sessions/hour: ~{sessions_per_hour_at_1vcpu} sessions")
        if sessions_per_hour_for_1min_session:
            print(
                f"   • Max 1-minute sessions/hour: ~{sessions_per_hour_for_1min_session} sessions"
            )
        print(
            f"   • To process 1000 sessions/hour, you need: {round(1000 * avg_cpu_per_session / 3600, 1)} vCPUs"
        )

        print(f"\n🖥️  ON YOUR M1 (8 cores) - WHAT YOU JUST TESTED:")
        print(
            f"   • Total CPU time across all {sessions_completed} sessions: {all_summary.get('total_cpu_time', 0):.2f} CPU-seconds"
        )
        print(f"   • Total wall time: {process_duration_s:.2f} seconds")
        if process_duration_s > 0:
            cpu_util_pct = (
                (all_summary.get("total_cpu_time", 0) / (process_duration_s * 8) * 100)
                if process_duration_s > 0
                else 0
            )
            print(f"   • Average CPU utilization: {cpu_util_pct:.1f}% of 8 cores")
            print(
                f"   • Throughput achieved: {round(sessions_completed / (process_duration_s / 3600), 1)} sessions/hour"
            )

        print(f"\n💾 MEMORY ANALYSIS:")
        print(
            f"   • Peak memory per session: {worst_case_peak_mb / max_concurrent:.2f} MB (average)"
        )
        print(
            f"   • Worst-case peak with {args.concurrency} concurrent sessions: {worst_case_peak_mb:.2f} MB"
        )
        print(f"   • This is {percent_of_2gb:.1f}% of a 2GB RAM system")
        if percent_of_2gb > 80:
            print(
                f"   ⚠️  WARNING: Memory usage is high! Consider reducing concurrency or increasing RAM."
            )
        elif percent_of_2gb > 60:
            print(f"   ⚠️  CAUTION: Memory usage is moderate. Monitor under real load.")
        else:
            print(f"   ✅ Memory usage is safe for 2GB system")

        print(f"\n🔍 BOTTLENECK ANALYSIS:")
        if avg_wall_per_session > avg_cpu_per_session * 1.5:
            print(
                f"   • Wall time ({avg_wall_per_session:.1f}s) >> CPU time ({avg_cpu_per_session:.1f}s)"
            )
            print(
                f"   • This suggests I/O waits, subprocess overhead, or resource contention"
            )
        else:
            print(
                f"   • Wall time ≈ CPU time → CPU-bound workload (good for parallelization)"
            )

        if args.concurrency > 1 and process_duration_s > 0:
            efficiency = (
                (avg_cpu_per_session * sessions_completed)
                / (process_duration_s * args.concurrency)
                if process_duration_s > 0
                else 0
            )
            print(
                f"   • Parallel efficiency: {efficiency * 100:.1f}% (100% = perfect parallelization)"
            )
            if efficiency < 0.7:
                print(
                    f"   ⚠️  Low efficiency suggests contention - may need more CPU cores or better scheduling"
                )

        print("\n" + "=" * 80)
    if tmp_root.exists():
        shutil.rmtree(tmp_root)


if __name__ == "__main__":  # pragma: no cover
    main()
