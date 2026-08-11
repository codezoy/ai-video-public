from __future__ import annotations

import json

from pipelines.htube_publish import publish_from_env, publish_run_output, safe_path_component


def test_publish_from_env_unset_skips_without_failure(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    final_mp4 = run_dir / "video.mp4"
    final_mp4.write_bytes(b"mp4")
    monkeypatch.delenv("AIVIDEO_HTUBE_PUBLISH_ROOT", raising=False)

    result = publish_from_env(
        run_id="run-001",
        topic="topic",
        run_dir=run_dir,
        final_mp4_path=final_mp4,
    )

    assert result is None
    assert list(tmp_path.iterdir()) == [run_dir]


def test_publish_run_output_copies_video_manifest_logs_and_metadata(tmp_path):
    run_dir = tmp_path / "work" / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    final_mp4 = run_dir / "video.mp4"
    final_mp4.write_bytes(b"final mp4")
    (run_dir / "artifact_manifest.json").write_text('{"run_id":"run-001"}\n', encoding="utf-8")
    (run_dir / "scenes.json").write_text('{"scenes":[]}\n', encoding="utf-8")
    (run_dir / "pipeline.log").write_text("done\n", encoding="utf-8")
    audio_dir = run_dir / "audio"
    audio_dir.mkdir()
    (audio_dir / "scene01.mp3").write_bytes(b"do not copy")
    publish_root = tmp_path / "publish"

    result = publish_run_output(
        publish_root=publish_root,
        run_id="run-001",
        topic="A Test Topic",
        run_dir=run_dir,
        final_mp4_path=final_mp4,
    )

    dest = publish_root / "A-Test-Topic" / "run-001"
    assert result.destination_dir == dest
    assert (dest / "video.mp4").read_bytes() == b"final mp4"
    assert json.loads((dest / "artifact_manifest.json").read_text(encoding="utf-8")) == {
        "run_id": "run-001"
    }
    assert json.loads((dest / "scenes.json").read_text(encoding="utf-8")) == {"scenes": []}
    assert (dest / "pipeline.log").read_text(encoding="utf-8") == "done\n"
    assert not (dest / "audio").exists()

    publish_metadata = json.loads((dest / "publish_metadata.json").read_text(encoding="utf-8"))
    assert publish_metadata["run_id"] == "run-001"
    assert publish_metadata["topic"] == "A Test Topic"
    assert publish_metadata["source_final_mp4_path"] == str(final_mp4)
    assert publish_metadata["source_run_dir"] == str(run_dir)
    assert publish_metadata["destination_dir"] == str(dest)
    assert "video.mp4" in publish_metadata["copied_files"]


def test_publish_destination_sanitizes_path_components(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    final_mp4 = run_dir / "video.mp4"
    final_mp4.write_bytes(b"mp4")
    publish_root = tmp_path / "publish"

    result = publish_run_output(
        publish_root=publish_root,
        run_id="../../run/../id",
        topic="../bad topic/../../escape",
        run_dir=run_dir,
        final_mp4_path=final_mp4,
    )

    assert result.destination_dir.is_relative_to(publish_root)
    assert result.destination_dir == publish_root / "bad-topic-escape" / "run-id"
    assert (result.destination_dir / "video.mp4").exists()
    assert safe_path_component("../", "fallback") == "fallback"
