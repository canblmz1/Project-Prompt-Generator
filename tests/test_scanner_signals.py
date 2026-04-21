import pytest
from pathlib import Path
from project_prompter.scanner import scan_project

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

