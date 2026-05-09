from project_prompter.scanner import _safe_read, build_file_tree, scan_project

def test_audio_binary_files_ignored_but_path_signal_can_be_used(tmp_path):
    # Create temp_audios directory
    temp_audios = tmp_path / "temp_audios"
    temp_audios.mkdir()
    
    # Create an audio file inside
    (temp_audios / "test.mp3").write_text("fake binary")
    
    all_files, _ = scan_project(tmp_path, 10, 100)
    
    # We expect temp_audios to be in the all_files as a skipped folder!
    paths = [f.relative_path for f in all_files]
    assert "temp_audios" in paths
    
    # Let's find the object
    folder_obj = next(f for f in all_files if f.relative_path == "temp_audios")
    assert folder_obj.skipped_reason == "ignored_folder"
    assert folder_obj.size == 0
    assert folder_obj.extension == ""
    
    # We should NOT see test.mp3 because its parent folder was bypassed entirely
    assert not any("test.mp3" in f.relative_path for f in all_files)


def test_extra_ignore_dirs_prunes_directory_but_keeps_signal(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw.py").write_text("SECRET = 'not read'")
    (tmp_path / "main.py").write_text("print('hello')")

    all_files, _ = scan_project(tmp_path, 10, 100, extra_ignore_dirs=["data"])

    paths = [f.relative_path for f in all_files]
    assert "data" in paths
    assert "data/raw.py" not in paths
    assert "main.py" in paths

    folder_obj = next(f for f in all_files if f.relative_path == "data")
    assert folder_obj.skipped_reason == "ignored_folder"


def test_build_file_tree_respects_extra_ignore_dirs(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "raw.py").write_text("x = 1")
    (tmp_path / "main.py").write_text("print('hello')")

    tree = build_file_tree(tmp_path, extra_ignore_dirs=["data"])

    assert "data" not in tree
    assert "raw.py" not in tree
    assert "main.py" in tree


def test_extra_ignore_dirs_match_nested_folder_name_exactly(tmp_path):
    nested_data = tmp_path / "src" / "data"
    nested_data.mkdir(parents=True)
    (nested_data / "raw.py").write_text("SECRET = 'not read'")

    database_dir = tmp_path / "database"
    database_dir.mkdir()
    (database_dir / "schema.py").write_text("print('kept')")

    all_files, _ = scan_project(tmp_path, 10, 100, extra_ignore_dirs=["data"])

    paths = [f.relative_path for f in all_files]
    assert "src/data" in paths
    assert "src/data/raw.py" not in paths
    assert "database/schema.py" in paths


def test_extra_ignore_dirs_normalize_whitespace_and_slashes(tmp_path):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    (generated_dir / "client.py").write_text("print('generated')")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "summary.py").write_text("print('report')")

    (tmp_path / "main.py").write_text("print('kept')")

    all_files, _ = scan_project(
        tmp_path,
        10,
        100,
        extra_ignore_dirs=[" generated/ ", "\\reports\\", "   "],
    )

    paths = [f.relative_path for f in all_files]
    assert "generated" in paths
    assert "generated/client.py" not in paths
    assert "reports" in paths
    assert "reports/summary.py" not in paths
    assert "main.py" in paths


def test_safe_read_zero_budget_uses_english_omission_marker(tmp_path):
    file_path = tmp_path / "large.txt"
    file_path.write_text("abcdef", encoding="utf-8")

    content, error = _safe_read(file_path, max_chars=0)

    assert error is None
    assert content == "... [MIDDLE SECTION OMITTED \u2014 6 chars] ..."
    assert "ORTA KISIM ATILDI" not in content
    assert "karakter" not in content


def test_scan_project_stops_after_max_scannable_files(tmp_path):
    for name in ("a.py", "b.py", "c.py", "d.py"):
        (tmp_path / name).write_text(f"print('{name}')", encoding="utf-8")

    all_files, _ = scan_project(tmp_path, max_files=2, max_chars_per_file=100)

    scannable = [f for f in all_files if not f.skipped_reason]
    assert len(scannable) == 2
    assert [f.relative_path for f in scannable] == ["a.py", "b.py"]
