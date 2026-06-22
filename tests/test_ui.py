# -*- mode: python ; coding: utf-8 -*-
import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

# Імпортуємо TkinterDnD для тестів
from tkinterdnd2 import TkinterDnD

# Add the project root to sys.path so that src. imports work properly
project_root = Path(__file__).parent
if (project_root / "src").exists():
    sys.path.insert(0, str(project_root))

# Import from the updated package structure
from src.ui import PureFFmpegTrimmer


class TestVideoCutter(unittest.TestCase):
    def setUp(self):
        """Initialization before each test case."""
        self.root = TkinterDnD.Tk()
        self.root.withdraw()

        # Patch initialization to avoid dependency on ffmpeg.exe
        # and prevent running update checks over the network
        with patch("src.ui.PureFFmpegTrimmer.check_for_updates"):
            self.app = PureFFmpegTrimmer(self.root)
            self.app.duration = 3661.0

    def tearDown(self):
        """Cleanup after each test case."""
        self.root.destroy()

    ## --- Time Parsing Logic Tests ---

    def test_parse_time_seconds(self):
        """Test parsing of raw seconds."""
        self.assertEqual(self.app.parse_time("90"), 90.0)
        self.assertEqual(self.app.parse_time("120.5"), 120.5)
        self.assertEqual(self.app.parse_time(" 10,5 "), 10.5)

    def test_parse_time_minutes(self):
        """Test parsing of the MM:SS format."""
        self.assertEqual(self.app.parse_time("01:30"), 90.0)
        self.assertEqual(self.app.parse_time("10:00"), 600.0)
        self.assertEqual(self.app.parse_time("00:05.50"), 5.5)

    def test_format_time_simple(self):
        """Test time formatting in seconds mode."""
        self.app.is_minutes_mode.set(False)
        self.assertEqual(self.app.format_time(90.5), "90.50")

    def test_format_time_minutes(self):
        """Test time formatting in MM:SS mode."""
        self.app.is_minutes_mode.set(True)
        self.assertEqual(self.app.format_time(90.5), "01:30.50")
        self.assertEqual(self.app.format_time(3661), "61:01.00")

    ## --- UI Synchronization Tests ---

    def test_update_entries_sync(self):
        """Verify that text entries update correctly when sliders move."""
        self.app.set_ui_state(tk.NORMAL)
        self.app.start_scale.set(45.0)
        self.app.update_entries()
        self.assertEqual(self.app.start_entry.get(), "45.00")

    ## --- FFmpeg Command Generation Tests ---

    @patch("subprocess.run")
    def test_trim_command_logic(self, mock_run):
        """Verify the correctness of generated FFmpeg command arguments."""
        self.app.video_path = Path("test.mp4")
        save_path = Path("output.mp4")

        # Pass values directly into the method
        self.app.run_trim(save_path, start_s=10.5, end_s=25.0)

        args, _ = mock_run.call_args
        cmd = [str(arg) for arg in args[0]]

        actual_start = float(cmd[cmd.index("-ss") + 1])
        self.assertEqual(actual_start, 10.5)


if __name__ == "__main__":
    unittest.main()
