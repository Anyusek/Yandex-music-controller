import os
import logging
import subprocess
import time
import threading
from pathlib import Path
from typing import Optional, Callable, List
import customtkinter as ctk
import win32api
import win32con
import win32gui

# Логирование
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("YaMusicCtrl")

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    logger.warning("Библиотека 'keyboard' не установлена. Глобальные горячие клавиши отключены.")

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False
    logger.warning("Библиотека 'pystray' или 'Pillow' не установлена. Сворачивание в трей отключено.")


LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA", "")
APP_PATH = Path(LOCAL_APP_DATA) / "Programs" / "YandexMusic" / "Яндекс Музыка.exe" # <-- сюда указать свой путь до самого приложения Я.Музыки
WINDOW_TITLE_KEYWORD = "Яндекс Музыка"

WM_APPCOMMAND = 0x0319
APPCOMMAND_MEDIA_PLAY_PAUSE = 14
APPCOMMAND_MEDIA_NEXTTRACK = 11
APPCOMMAND_MEDIA_PREVIOUSTRACK = 12
APPCOMMAND_VOLUME_UP = 10
APPCOMMAND_VOLUME_DOWN = 9
APPCOMMAND_VOLUME_MUTE = 8

LAUNCH_TIMEOUT_SEC = 15.0  
LAUNCH_POLL_INTERVAL = 0.5 

# Слой работы с окном (Win32 API) 
class YandexMusicWindow:
    def __init__(self):
        self._cached_hwnd: Optional[int] = None

    def _is_valid_target_window(self, hwnd: int) -> bool:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER) != 0:
            return False
            
        title = win32gui.GetWindowText(hwnd)
        return WINDOW_TITLE_KEYWORD.lower() in title.lower()

    def find_hwnd(self) -> Optional[int]:
        """Ищет окно, используя кэширование для производительности."""

        if self._cached_hwnd and self._is_valid_target_window(self._cached_hwnd):
            return self._cached_hwnd

        found_hwnds: List[int] = []

        def _enum_cb(hwnd: int, _) -> bool:
            if self._is_valid_target_window(hwnd):
                found_hwnds.append(hwnd)
            return True # Продолжаем поиск на случай нескольких окон

        win32gui.EnumWindows(_enum_cb, None)
        
        if found_hwnds:
            self._cached_hwnd = found_hwnds[0]
            logger.debug("Окно найдено и закэшировано HWND=%s", self._cached_hwnd)
            return self._cached_hwnd
            
        self._cached_hwnd = None
        return None

    def send_command(self, command: int) -> bool:
        """Отправляет команду приложению."""
        hwnd = self.find_hwnd()
        if hwnd is None:
            logger.warning("Окно '%s' не найдено для отправки команды", WINDOW_TITLE_KEYWORD)
            return False

        lparam = command << 16
        try:
            win32api.PostMessage(hwnd, WM_APPCOMMAND, hwnd, lparam)
            logger.info("Команда %d отправлена", command)
            return True
        except Exception as exc:
            logger.error("Ошибка отправки команды: %s", exc)
            self._cached_hwnd = None # Сбрасываем кэш при ошибке
            return False

    def is_running(self) -> bool:
        return self.find_hwnd() is not None

    def bring_to_front(self) -> bool:
        """Восстанавливает и выводит окно на передний план."""
        hwnd = self.find_hwnd()
        if not hwnd:
            return False
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            logger.info("Окно выведено на передний план")
            return True
        except Exception as exc:
            logger.error("Ошибка SetForegroundWindow: %s", exc)
            return False

class MusicService:
    def __init__(self):
        self._window = YandexMusicWindow()

    def launch(self, callback: Optional[Callable[[bool, str], None]] = None) -> None:
        def _worker():
            try:
                if self._window.is_running():
                    logger.info("Приложение уже запущено")
                    self.bring_to_front()
                    if callback:
                        callback(True, "Уже запущено")
                    return

                if not APP_PATH.exists():
                    logger.error("Файл не найден: %s", APP_PATH)
                    if callback:
                        callback(False, "Файл не найден")
                    return

                logger.info("Запускаю %s", APP_PATH)
                subprocess.Popen(str(APP_PATH))

                start_time = time.time()
                while time.time() - start_time < LAUNCH_TIMEOUT_SEC:
                    if self._window.is_running():
                        logger.info("Приложение успешно запустилось")
                        if callback:
                            callback(True, "Запущено ✓")
                        return
                    time.sleep(LAUNCH_POLL_INTERVAL)

                logger.error("Таймаут: окно не появилось")
                if callback:
                    callback(False, "Таймаут запуска")

            except Exception as exc:
                logger.error("Ошибка запуска: %s", exc)
                if callback:
                    callback(False, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def bring_to_front(self) -> bool:
        return self._window.bring_to_front()

    def play_pause(self) -> bool:
        return self._window.send_command(APPCOMMAND_MEDIA_PLAY_PAUSE)

    def next_track(self) -> bool:
        return self._window.send_command(APPCOMMAND_MEDIA_NEXTTRACK)

    def prev_track(self) -> bool:
        return self._window.send_command(APPCOMMAND_MEDIA_PREVIOUSTRACK)

    def volume_up(self) -> bool:
        return self._window.send_command(APPCOMMAND_VOLUME_UP)

    def volume_down(self) -> bool:
        return self._window.send_command(APPCOMMAND_VOLUME_DOWN)

    def volume_mute(self) -> bool:
        return self._window.send_command(APPCOMMAND_VOLUME_MUTE)

THEME = {
    "bg": "#0D0D0D",
    "surface": "#161616",
    "surface2": "#1E1E1E",
    "accent": "#FFCC00",
    "accent_hover": "#FFD740",
    "text": "#F5F5F5",
    "text_muted": "#888888",
    "danger": "#FF4C4C",
    "success": "#4CAF50",
    "radius": 14,
    "btn_height": 42,
}


class StatusBar(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=THEME["surface2"],
            corner_radius=8,
            **kwargs,
        )
        self._dot = ctk.CTkLabel(self, text="●", font=("Segoe UI", 11), width=18)
        self._dot.pack(side="left", padx=(10, 2), pady=6)

        self._label = ctk.CTkLabel(
            self,
            text="Готово к работе",
            font=("Segoe UI", 11),
            text_color=THEME["text_muted"],
        )
        self._label.pack(side="left", padx=(0, 10), pady=6)

    def set(self, message: str, kind: str = "info") -> None:
        colors = {"info": THEME["text_muted"], "ok": THEME["success"], "error": THEME["danger"]}
        color = colors.get(kind, THEME["text_muted"])
        self._dot.configure(text_color=color)
        self._label.configure(text=message, text_color=color)


def _make_btn(master, text: str, command: Callable, accent: bool = False, width: int = 260) -> ctk.CTkButton:
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        width=width,
        height=THEME["btn_height"],
        corner_radius=THEME["radius"],
        font=("Segoe UI Semibold", 13),
        fg_color=THEME["accent"] if accent else THEME["surface2"],
        hover_color=THEME["accent_hover"] if accent else "#2A2A2A",
        text_color="#0D0D0D" if accent else THEME["text"],
        border_width=0,
    )


def _make_small_btn(master, text: str, command: Callable, width: int = 78) -> ctk.CTkButton:
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        width=width,
        height=THEME["btn_height"],
        corner_radius=THEME["radius"],
        font=("Segoe UI Semibold", 15),
        fg_color=THEME["surface2"],
        hover_color="#2A2A2A",
        text_color=THEME["text"],
        border_width=0,
    )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._service = MusicService()
        self._setup_window()
        self._build_ui()
        self._setup_hotkeys()
        self._setup_tray()

    def _setup_window(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Я.Музыка - контроллер")
        self.geometry("320x460")
        self.resizable(False, False)
        self.configure(fg_color=THEME["bg"])

        ico = Path(__file__).parent / "icon.ico"
        if ico.exists():
            self.iconbitmap(str(ico))

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(22, 4))

        ctk.CTkLabel(header, text="Я", font=("Georgia", 32, "bold"), text_color=THEME["accent"]).pack(side="left")
        ctk.CTkLabel(header, text=".Музыка", font=("Segoe UI Light", 22), text_color=THEME["text"]).pack(side="left", padx=(2, 0), pady=(6, 0))
        ctk.CTkLabel(header, text="controller", font=("Segoe UI", 10), text_color=THEME["text_muted"]).pack(side="right", pady=(14, 0))

        ctk.CTkFrame(self, height=1, fg_color=THEME["surface2"]).pack(fill="x", padx=20, pady=(8, 16))

        _make_btn(self, text="🚀  Открыть Я.Музыку", command=self._on_launch, accent=True).pack(pady=(0, 16))

        self._section_label("Управление треком")
        transport = ctk.CTkFrame(self, fg_color="transparent")
        transport.pack(pady=(6, 16))

        _make_small_btn(transport, "⏮", self._on_prev).pack(side="left", padx=4)
        _make_small_btn(transport, "⏯", self._on_play_pause, width=96).pack(side="left", padx=4)
        _make_small_btn(transport, "⏭", self._on_next).pack(side="left", padx=4)

        self._section_label("Громкость")
        volume = ctk.CTkFrame(self, fg_color="transparent")
        volume.pack(pady=(6, 16))

        _make_small_btn(volume, "🔉", self._on_vol_down).pack(side="left", padx=4)
        _make_small_btn(volume, "🔇", self._on_mute, width=54).pack(side="left", padx=4)
        _make_small_btn(volume, "🔊", self._on_vol_up).pack(side="left", padx=4)

        # Кнопка "показать окно"
        ctk.CTkFrame(self, height=1, fg_color=THEME["surface2"]).pack(fill="x", padx=20, pady=(4, 14))
        _make_btn(self, text="🪟  Показать окно плеера", command=self._on_bring_to_front).pack()

        self._status = StatusBar(self)
        self._status.pack(fill="x", padx=20, pady=(16, 14))

    def _section_label(self, text: str):
        ctk.CTkLabel(self, text=text.upper(), font=("Segoe UI", 9), text_color=THEME["text_muted"]).pack()

    # Глобальные горячие клавиши 
    def _setup_hotkeys(self):
        if not HAS_KEYBOARD:
            return
        try:
            keyboard.add_hotkey('ctrl+p', self._on_play_pause) # делает паузу трека
            keyboard.add_hotkey('ctrl+right', self._on_next) # переключает на следующий трек
            keyboard.add_hotkey('ctrl+left', self._on_prev) # переключает на предыдущий трек
            keyboard.add_hotkey('ctrl+up', self._on_vol_up) # увеличивает громкость
            keyboard.add_hotkey('ctrl+down', self._on_vol_down) # уменьшает громкость
            keyboard.add_hotkey('ctrl+m', self._on_mute) # отключает звук
            logger.info("Горячие клавиши зарегистрированы")
        except Exception as e:
            logger.error("Ошибка при регистрации горячих клавиш: %s", e)

    # Системный трей 
    def _setup_tray(self):
        if not HAS_TRAY:
            return
        # Перехватывается нажатие крестика для сворачивания в трей
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

    def _hide_to_tray(self):
        self.withdraw() 
        
        # Создается заглушку-иконку для трея
        image = Image.new('RGB', (64, 64), color=(13, 13, 13))
        draw = ImageDraw.Draw(image)
        draw.ellipse((16, 16, 48, 48), fill=(255, 204, 0))

        menu = pystray.Menu(
            pystray.MenuItem("Развернуть", self._restore_from_tray),
            pystray.MenuItem("Выход", self._quit_app)
        )
        self.tray_icon = pystray.Icon("YaMusicCtrl", image, "Я.Музыка Controller", menu)
        # Запускаем трей в отдельном потоке, чтобы не блокировать UI
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _restore_from_tray(self, icon, item):
        icon.stop()
        self.after(0, self.deiconify)

    def _quit_app(self, icon, item):
        icon.stop()
        self.after(0, self.destroy)

    def _update_status_ui(self, message: str, kind: str):
        self.after(0, lambda: self._status.set(message, kind))

    def _on_launch(self):
        self._update_status_ui("Запуск…", "info")
        def _cb(success: bool, message: str):
            self._update_status_ui(message, "ok" if success else "error")
        self._service.launch(callback=_cb)

    def _cmd(self, action: Callable[[], bool], label: str):
        ok = action()
        if ok:
            self._update_status_ui(f"{label} ✓", "ok")
        else:
            self._update_status_ui("Яндекс Музыка не найдена", "error")

    def _on_play_pause(self): self._cmd(self._service.play_pause, "Play / Pause")
    def _on_next(self): self._cmd(self._service.next_track, "Следующий трек")
    def _on_prev(self): self._cmd(self._service.prev_track, "Предыдущий трек")
    def _on_vol_up(self): self._cmd(self._service.volume_up, "Громче")
    def _on_vol_down(self): self._cmd(self._service.volume_down, "Тише")
    def _on_mute(self): self._cmd(self._service.volume_mute, "Mute")

    def _on_bring_to_front(self):
        if self._service.bring_to_front():
            self._update_status_ui("Окно открыто", "ok")
        else:
            self._update_status_ui("Яндекс Музыка не найдена", "error")


if __name__ == "__main__":
    logger.info("Запуск Яндекс Музыка Controller")
    app = App()
    app.mainloop()
