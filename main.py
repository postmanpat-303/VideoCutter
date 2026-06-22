import ctypes

# Замість стандартного tk імпортуємо TkinterDnD
from tkinterdnd2 import TkinterDnD

from src.ui import PureFFmpegTrimmer


def set_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass


if __name__ == "__main__":
    set_dpi_awareness()

    # Ініціалізуємо вікно з підтримкою Drag and Drop
    root = TkinterDnD.Tk()

    app = PureFFmpegTrimmer(root)
    if root.winfo_exists():
        root.mainloop()
