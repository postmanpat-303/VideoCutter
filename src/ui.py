import io
import re
import subprocess
import threading
import tkinter as tk
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from tkinter import filedialog, messagebox

import requests
from PIL import Image, ImageTk

# Імпорти з наших нових модулів
from src.config import (
    VERSION,
    FFMPEG_BIN,
    SEGOE_UI,
    REPO_OWNER,
    REPO_NAME,
    BUTTON_RELEASE_,
    get_resource_path,
    FRAME_RENDER_TIMEOUT,
)
from src.i18n import LanguageManager


class PureFFmpegTrimmer:
    def __init__(self, root):
        self.file_info_label = None
        self.canvas = None
        self.status_label = None
        self.result_info_label = None
        self.end_entry = None
        self.end_scale = None
        self.start_entry = None
        self.start_scale = None
        self.btn_trim = None
        self.mode_check = None
        self.root = root
        self.lang_mgr = LanguageManager()

        # Назва програми
        self.app_name = "Pro Video Trimmer"
        self.root.title(f"{self.app_name} {VERSION}")

        self.ffmpeg_version = "Unknown"
        if not self.check_ffmpeg():
            self.root.withdraw()
            messagebox.showerror(
                self.lang_mgr.get("error_title"),
                f"{self.lang_mgr.get('error_ffmpeg')}\n{FFMPEG_BIN.absolute()}",
            )
            self.root.destroy()
            return

        self.video_path = None
        self.duration = 0.0
        self.last_img = None
        self.current_t = 0.0
        self.is_minutes_mode = tk.BooleanVar(value=False)
        self.after_id = None
        self.repeat_delay = 100
        self.interactive_widgets = []

        self.setup_ui()

        icon_path = get_resource_path("icon.ico")
        if icon_path.exists():
            self.root.iconbitmap(str(icon_path))

        threading.Thread(target=self.check_for_updates, daemon=True).start()
        self.current_render_proc = None
        self.render_lock = threading.Lock()
        self.debounce_timer = None

    def check_ffmpeg(self) -> bool:
        """Перевірка та отримання версії ffmpeg."""
        if not FFMPEG_BIN.exists():
            return False
        try:
            # Отримуємо перший рядок виводу ffmpeg -version
            result = subprocess.run(
                [str(FFMPEG_BIN), "-version"],
                capture_output=True,
                text=True,
                creationflags=0x08000000,
                check=True,
            )
            first_line = result.stdout.splitlines()[0]
            # Витягуємо версію (наприклад, "ffmpeg version 7.0.1...")
            match = re.search(r"version\s+([^\s,]+)", first_line)
            self.ffmpeg_version = match.group(1) if match else "Виявлено"
            return True
        except (subprocess.CalledProcessError, OSError, IndexError):
            return False

    def check_for_updates(self):
        # 1. Якщо поточна версія — бета, не перевіряємо оновлення (щоб не турбувати тестерів)
        if "beta" in VERSION.lower():
            return

        try:
            api_url = (
                f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
            )
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("tag_name", "")

                # 2. Перевіряємо, чи нова версія не є бетою
                if latest_version and "beta" not in latest_version.lower():
                    # 3. Порівнюємо версії (тільки якщо вони різні)
                    if latest_version != VERSION:
                        self.root.after(
                            0, lambda: self.show_update_dialog(latest_version)
                        )
        except Exception as e:
            print(f"Update check failed: {e}")

    def show_update_dialog(self, new_version):
        if messagebox.askyesno(
            self.lang_mgr.get("update_found_title"),
            self.lang_mgr.get(
                "update_message", new_version=new_version, version=VERSION
            ),
        ):
            webbrowser.open("https://olexandr-klymenko.github.io/VideoCutter/")

    def setup_ui(self):
        self.root.option_add("*Font", (SEGOE_UI, 9))
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)

        controls = tk.Frame(self.root, pady=10, padx=10)
        controls.pack(side="top", fill="x")

        btn_frame = tk.Frame(controls)
        btn_frame.pack(fill="x")

        tk.Button(
            btn_frame, text=self.lang_mgr.get("open_btn"), command=self.load_video
        ).pack(side="left", padx=5)

        self.mode_check = tk.Checkbutton(
            btn_frame,
            text=self.lang_mgr.get("minutes_mode"),
            variable=self.is_minutes_mode,
            command=self.toggle_format,
            state=tk.DISABLED,
        )
        self.mode_check.pack(side="left", padx=15)
        self.interactive_widgets.append(self.mode_check)

        info_frame = tk.Frame(btn_frame)
        info_frame.pack(side="left", padx=10)
        tk.Label(
            info_frame, text=f"App: {VERSION}", fg="#888888", font=(SEGOE_UI, 8)
        ).pack(side="top", anchor="w")
        tk.Label(
            info_frame,
            text=f"FFmpeg: {self.ffmpeg_version}",
            fg="#888888",
            font=(SEGOE_UI, 8),
        ).pack(side="top", anchor="w")

        self.btn_trim = tk.Button(
            btn_frame,
            text=self.lang_mgr.get("trim_btn"),
            bg="#28a745",
            fg="white",
            font=(SEGOE_UI, 9, "bold"),
            command=self.start_trim_thread,
            state=tk.DISABLED,
        )
        self.btn_trim.pack(side="right", padx=5)
        self.interactive_widgets.append(self.btn_trim)

        self.start_scale, self.start_entry = self.create_time_control(
            controls, self.lang_mgr.get("start_label")
        )
        self.end_scale, self.end_entry = self.create_time_control(
            controls, self.lang_mgr.get("end_label")
        )

        self.result_info_label = tk.Label(
            controls, text="", font=(SEGOE_UI, 9, "bold"), fg="#0056b3"
        )
        self.result_info_label.pack(pady=2)

        self.status_label = tk.Label(
            controls,
            text=self.lang_mgr.get("status_waiting"),
            font=("Consolas", 10),
            fg="gray",
        )
        self.status_label.pack(pady=5)

        self.canvas = tk.Label(self.root, bg="#1a1a1a")
        self.canvas.pack(expand=True, fill="both")
        self.canvas.bind("<Configure>", self.on_resize)

        version_footer = tk.Label(
            self.root,
            text=self.lang_mgr.get("version_label", version=VERSION),
            fg="gray",
        )
        version_footer.pack(side="bottom", anchor="e", padx=10, pady=5)
        # У методі setup_ui додайте:
        self.file_info_label = tk.Label(
            controls, text="", fg="#555555", font=(SEGOE_UI, 9, "italic")
        )
        self.file_info_label.pack(side="top", anchor="w", padx=5, pady=(5, 0))

        self.create_tooltip(
            self.file_info_label,
            lambda: str(self.video_path) if self.video_path else "",
        )

        # 1. Реєструємо canvas як ціль для файлів
        self.canvas.drop_target_register("DND_Files")

        # 2. Використовуємо dnd_bind замість звичайного bind
        # Це змушує обгортку коректно перехоплювати специфічні токени подій
        self.canvas.dnd_bind("<<DropEnter>>", lambda event: "copy")
        self.canvas.dnd_bind("<<DropPosition>>", lambda event: "copy")
        self.canvas.dnd_bind("<<Drop>>", self.handle_file_drop)

    def create_time_control(self, parent, label_text):
        frame = tk.Frame(parent)
        frame.pack(fill="x", pady=2)
        tk.Label(frame, text=label_text, width=12, anchor="w").pack(side="left")

        scale = tk.Scale(
            frame,
            orient="horizontal",
            from_=0,
            to=100,
            resolution=0.01,
            showvalue=False,
            state=tk.DISABLED,
            command=lambda _: self.update_entries(),
        )
        scale.pack(side="left", fill="x", expand=True, padx=5)
        scale.bind(
            "<Button-1>",
            lambda e: (
                self.jump_to_click(e, scale) if scale["state"] != tk.DISABLED else None
            ),
        )
        scale.bind(
            BUTTON_RELEASE_,
            lambda e: (
                self.update_preview(scale.get())
                if scale["state"] != tk.DISABLED
                else None
            ),
        )

        entry = tk.Entry(frame, width=10, justify="center", state=tk.DISABLED)
        entry.pack(side="left", padx=5)
        entry.bind("<Return>", lambda e: self.on_entry_change(scale, entry))

        fine_frame = tk.Frame(frame)
        fine_frame.pack(side="right")
        for d in [-0.1, 0.1]:
            btn = tk.Button(fine_frame, text=f"{d:+.1f}", width=4, state=tk.DISABLED)
            btn.pack(side="left", padx=1)
            btn.bind(
                "<ButtonPress-1>",
                lambda e, s=scale, delta=d: self.start_auto_adjust(s, delta),
            )
            btn.bind(BUTTON_RELEASE_, lambda e: self.stop_auto_adjust())
            self.interactive_widgets.append(btn)

        self.interactive_widgets.extend([scale, entry])
        return scale, entry

    def toggle_format(self):
        self.update_entries()
        self.update_status_pos(self.current_t)

    def update_status_pos(self, t):
        self.status_label.config(
            text=self.lang_mgr.get(
                "status_position",
                current=self.format_time(t),
                total=self.format_time(self.duration),
            ),
            fg="black",
        )

    def refresh_duration_info(self):
        diff = self.end_scale.get() - self.start_scale.get()
        if diff < 0:
            self.result_info_label.config(
                text=self.lang_mgr.get("error_range"), fg="red"
            )
            self.btn_trim.config(state=tk.DISABLED)
        else:
            unit = self.lang_mgr.get(
                "unit_min_sec" if self.is_minutes_mode.get() else "unit_sec"
            )
            self.result_info_label.config(
                text=self.lang_mgr.get(
                    "duration_info", time=self.format_time(diff), unit=unit
                ),
                fg="#0056b3",
            )
            if self.video_path:
                self.btn_trim.config(state=tk.NORMAL)

    @contextmanager
    def ui_blocker(self):
        """Контекстний менеджер для блокування інтерфейсу під час тривалих операцій."""
        try:
            self.set_ui_state(tk.DISABLED)
            self.root.config(
                cursor="watch"
            )  # Опціонально: змінюємо курсор на "очікування"
            yield
        finally:
            self.set_ui_state(tk.NORMAL)
            self.root.config(cursor="")  # Повертаємо звичайний курсор
            self.refresh_duration_info()  # Оновлюємо стан кнопки Trim

    def load_video(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.ts")]
        )
        if not file_path:
            return

        self.video_path = Path(file_path).resolve()
        self._execute_video_parsing()

    def create_tooltip(self, widget, text_func):
        """Створює спливаючу підказку для віджета."""
        tooltip_window = [None]

        def show_tooltip(event):
            text = text_func()
            if not text:
                return

            # Створюємо вікно без рамки (Toplevel)
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25

            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)  # Прибрати заголовок вікна
            tw.wm_geometry(f"+{x}+{y}")

            label = tk.Label(
                tw,
                text=text,
                justify="left",
                background="#ffffe1",
                relief="solid",
                borderwidth=1,
                font=(SEGOE_UI, "9", "normal"),
                padx=5,
                pady=2,
            )
            label.pack()
            tooltip_window[0] = tw

        def hide_tooltip(event):
            if tooltip_window[0]:
                tooltip_window[0].destroy()
                tooltip_window[0] = None

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)

    def update_preview(self, t):
        """Ініціює процес прев'ю з використанням debounce-таймера."""
        if not self.video_path or not FFMPEG_BIN.exists():
            return

        self.current_t = t
        self.status_label.config(text=self.lang_mgr.get("status_rendering"), fg="blue")

        if self.debounce_timer:
            self.debounce_timer.cancel()

        self.debounce_timer = threading.Timer(0.15, self._trigger_render, args=(t,))
        self.debounce_timer.start()

    def _trigger_render(self, t):
        """Запускає задачу рендерингу в демонічному потоці."""
        threading.Thread(target=self._render_task, args=(t,), daemon=True).start()

    def _stop_current_proc(self):
        """Безпечно зупиняє поточний процес FFmpeg."""
        with self.render_lock:
            if not self.current_render_proc:
                return
            try:
                self.current_render_proc.kill()
                self.current_render_proc.wait()
            except OSError:
                pass  # Процес уже міг бути закритий ОС
            finally:
                self.current_render_proc = None

    def _render_task(self, t):
        """Виконує рендеринг кадру через FFmpeg PIPE."""
        self._stop_current_proc()

        # noinspection PyArgumentList
        with self.ui_blocker():
            safe_t = max(0.0, min(float(t), self.duration - 0.1))
            cmd = [
                str(FFMPEG_BIN),
                "-ss",
                str(round(safe_t, 3)),
                "-i",
                str(self.video_path),
                "-vframes",
                "1",
                "-q:v",
                "4",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-loglevel",
                "quiet",
                "-",
            ]

            p = None
            try:
                p = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000,
                )

                with self.render_lock:
                    self.current_render_proc = p

                data, _ = p.communicate(timeout=FRAME_RENDER_TIMEOUT)

                # Перевірка актуальності запиту та наявності даних
                if self.current_t != t:
                    return

                if not data or len(data) <= 500:
                    raise ValueError("Incomplete image data received")

                image = Image.open(io.BytesIO(data))
                self.root.after(0, lambda: self.display_image(image, t))

            except subprocess.TimeoutExpired:
                self._handle_render_error("error_timeout", t, p)
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                print(f"Render error: {e}")
                self._handle_render_error("error_render", t, p)
            finally:
                self._cleanup_proc(p)

    def _handle_render_error(self, lang_key, t, proc):
        """Централізована обробка помилок рендерингу."""
        if proc:
            try:
                proc.kill()
            except OSError:
                pass

        if self.current_t == t:
            error_text = (
                self.lang_mgr.get(lang_key, time=self.format_time(t))
                if lang_key == "error_timeout"
                else self.lang_mgr.get(lang_key)
            )
            self.root.after(
                0, lambda: self.status_label.config(text=error_text, fg="red")
            )

    def _cleanup_proc(self, proc):
        """Очищення ресурсів після завершення або помилки."""
        with self.render_lock:
            if self.current_render_proc == proc:
                self.current_render_proc = None
        if proc and proc.stdout:
            proc.stdout.close()

    def display_image(self, img, t):
        self.last_img = img
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw > 10 and ch > 10:
            iw, ih = img.size
            ratio = min(cw / iw, ch / ih)
            img_res = img.resize(
                (int(iw * ratio), int(ih * ratio)), Image.Resampling.LANCZOS
            )
            tk_img = ImageTk.PhotoImage(img_res)
            self.canvas.config(image=tk_img)
            self.canvas.image = tk_img
        self.update_status_pos(t)

    def start_trim_thread(self):
        save_path = filedialog.asksaveasfilename(
            initialfile=f"trimmed_{self.video_path.name}", defaultextension=".mp4"
        )
        if save_path:
            threading.Thread(
                target=self.run_trim, args=(Path(save_path),), daemon=True
            ).start()

    def run_trim(self, save_path: Path, start_s=None, end_s=None):
        # Якщо аргументи не передані (звичайний клік у програмі), беремо значення зі слайдерів
        s = start_s if start_s is not None else self.start_scale.get()
        e = end_s if end_s is not None else self.end_scale.get()

        # noinspection PyArgumentList
        with self.ui_blocker():
            self.btn_trim.config(text=self.lang_mgr.get("trimming_process"))
            cmd = [
                str(FFMPEG_BIN),
                "-y",
                "-ss",
                str(round(s, 3)),
                "-t",
                str(round(e - s, 3)),
                "-i",
                str(self.video_path),
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                str(save_path),
            ]
            try:
                subprocess.run(cmd, creationflags=0x08000000, check=True)
                # Викликаємо кастомне вікно замість стандартного messagebox
                self.root.after(0, lambda: self.show_success_dialog(save_path))
            except Exception as err:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        self.lang_mgr.get("error_title"), str(err)
                    ),
                )
            finally:
                self.root.after(
                    0,
                    lambda: [
                        self.btn_trim.config(text=self.lang_mgr.get("trim_btn")),
                    ],
                )

    def show_success_dialog(self, save_path: Path):
        """Custom success window with a layout that prevents button disappearing."""
        dialog = tk.Toplevel(self.root)
        dialog.title(self.lang_mgr.get("success_title"))

        # Set minimum size and allow the window to grow if needed
        dialog.geometry("400x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Center the dialog
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 110
        dialog.geometry(f"+{x}+{y}")

        # Grid configuration to manage space
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)  # Message area expands

        # Message container
        msg_frame = tk.Frame(dialog, padx=20, pady=10)
        msg_frame.grid(row=0, column=0, sticky="nsew")

        # Filename processing
        display_name = save_path.name
        if len(display_name) > 80:  # Allow more chars since we use wrapping
            display_name = display_name[:40] + "..." + display_name[-35:]

        msg_text = f"{self.lang_mgr.get('success_message', name='')}\n\n{display_name}"

        # Using a fixed width for wrapping and anchor to keep it neat
        msg_label = tk.Label(
            msg_frame,
            text=msg_text,
            wraplength=350,
            justify="center",
            font=(SEGOE_UI, 9),
        )
        msg_label.pack(expand=True)

        # Bottom controls area (fixed height)
        controls_frame = tk.Frame(dialog, pady=10)
        controls_frame.grid(row=1, column=0, sticky="ew")

        var_open = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(
            controls_frame,
            text=self.lang_mgr.get("open_folder_checkbox"),
            variable=var_open,
        )
        chk.pack()

        def on_ok():
            if var_open.get():
                subprocess.run(["explorer", "/select,", str(save_path.absolute())])
            dialog.destroy()

        tk.Button(controls_frame, text="OK", width=12, command=on_ok).pack(pady=5)

    # --- Допоміжні методи (без змін логіки) ---
    def set_ui_state(self, state):
        for w in self.interactive_widgets:
            w.config(state=state)

    def format_time(self, seconds):
        if not self.is_minutes_mode.get():
            return f"{seconds:.2f}"
        return f"{int(seconds // 60):02d}:{seconds % 60:05.2f}"

    def parse_time(self, s):
        s = s.replace(",", ".").strip()
        if ":" in s:
            p = s.split(":")
            return int(p[0]) * 60 + float(p[1]) if len(p) == 2 else 0.0
        return float(s)

    def update_entries(self):
        for e, s in [
            (self.start_entry, self.start_scale),
            (self.end_entry, self.end_scale),
        ]:
            if e["state"] != tk.DISABLED:
                e.delete(0, tk.END)
                e.insert(0, self.format_time(s.get()))
        self.refresh_duration_info()

    def on_entry_change(self, scale, entry):
        try:
            val = max(0, min(self.parse_time(entry.get()), self.duration))
            scale.set(val)
            self.update_preview(val)
        except:
            self.update_entries()

    def jump_to_click(self, e, s):
        val = (max(0, min(1, (e.x - 8) / (s.winfo_width() - 16)))) * s.cget("to")
        s.set(val)
        self.update_preview(val)

    def start_auto_adjust(self, s, d):
        self.adjust_time(s, d)
        self.after_id = self.root.after(400, lambda: self.repeat_adjust(s, d))

    def repeat_adjust(self, s, d):
        self.adjust_time(s, d)
        self.after_id = self.root.after(
            self.repeat_delay, lambda: self.repeat_adjust(s, d)
        )

    def stop_auto_adjust(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None

    def adjust_time(self, s, d):
        nv = max(0, min(s.get() + d, self.duration))
        s.set(nv)
        self.update_entries()
        self.update_preview(nv)

    def on_resize(self, e):
        if self.last_img:
            self.display_image(self.last_img, self.current_t)

    def handle_file_drop(self, event):
        """Обробник події скидання файлу."""
        raw_data = event.data
        if not raw_data:
            return

        # Очищаємо шлях від фігурних дужок (актуально для Windows, якщо є пробіли)
        if raw_data.startswith("{") and raw_data.endswith("}"):
            file_path = raw_data[1:-1]
        else:
            file_path = raw_data.strip('"')

        path_obj = Path(file_path).resolve()

        # Перевіряємо розширення файлу
        valid_extensions = [".mp4", ".mkv", ".avi", ".mov", ".ts"]
        if path_obj.suffix.lower() in valid_extensions:
            # Записуємо шлях у змінну класу
            self.video_path = path_obj

            # Емулюємо процес завантаження, який зазвичай робить кнопка "Open"
            # Оскільки ваш оригінальний load_video не приймає аргументів, ми робимо
            # невеликий фокус: викликаємо внутрішню логіку напряму.
            self._execute_video_parsing()
        else:
            messagebox.showwarning(
                self.lang_mgr.get("error_title"),
                f"Непідтримуваний формат файлу!\nДозволені: {', '.join(valid_extensions)}",
            )

    def _execute_video_parsing(self):
        """Внутрішній метод для парсингу відео через FFmpeg."""
        # Витягуємо дані через FFmpeg (це ваш оригінальний код з load_video)
        cmd = [str(FFMPEG_BIN), "-hide_banner", "-i", str(self.video_path)]
        try:
            p = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=0x08000000,
            )
            _, err = p.communicate()

            # 1. Тривалість
            dur_match = re.search(r"Duration:\s(\d+):(\d+):(\d+\.\d+)", err)
            # 2. Роздільна здатність
            res_match = re.search(r",\s(\d{3,5})x(\d{3,5})", err)
            # 3. Відео кодек
            codec_match = re.search(r"Video:\s([a-z0-9]+)", err)

            if dur_match:
                h, m, s = map(float, dur_match.groups())
                self.duration = h * 3600 + m * 60 + s

                res_str = (
                    f"{res_match.group(1)}x{res_match.group(2)}"
                    if res_match
                    else "??x??"
                )
                codec_str = codec_match.group(1).upper() if codec_match else "Unknown"
                file_size = f"{self.video_path.stat().st_size / (1024 * 1024):.1f} MB"

                info_text = f"📄 {self.video_path.name}  |  🎬 {res_str}  |  🎞️ {codec_str}  |  ⚖️ {file_size}"
                self.file_info_label.config(text=info_text)

                self.set_ui_state(tk.NORMAL)
                for scale in [self.start_scale, self.end_scale]:
                    scale.config(to=self.duration)
                self.start_scale.set(0)
                self.end_scale.set(self.duration)
                self.update_preview(0)
                self.update_entries()

        except Exception as e:
            messagebox.showerror(
                self.lang_mgr.get("error_title"),
                f"{self.lang_mgr.get('error_read')} {e}",
            )
