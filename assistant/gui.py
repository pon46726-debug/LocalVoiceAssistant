import customtkinter as ctk
from tkinter import scrolledtext
import threading

from assistant.core import VoiceEngine
from assistant.logger import setup_logger

logger = setup_logger()

class AssistantGUI:
    def __init__(self):
        # Настройка темы
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.root = ctk.CTk()
        self.root.title("Local Voice Assistant")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)
        
        # Цвета
        self.bg_color = "#1a1a1a"
        self.accent_color = "#00b4d8"
        self.success_color = "#2ecc71"
        self.warning_color = "#f39c12"
        self.error_color = "#e74c3c"
        
        self.engine = None
        self.listen_thread = None
        self.is_running = False
        
        self._setup_ui()
        self._init_engine()
    
    def _setup_ui(self):
        # Главный контейнер
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        
        # === ЛЕВАЯ ПАНЕЛЬ (настройки) ===
        self.sidebar = ctk.CTkFrame(self.root, width=250, corner_radius=15)
        self.sidebar.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.sidebar.grid_propagate(False)
        
        # Логотип
        self.logo_label = ctk.CTkLabel(
            self.sidebar,
            text="🎙️ LVA",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        self.logo_label.pack(pady=(20, 10))
        
        self.version_label = ctk.CTkLabel(
            self.sidebar,
            text="Local Voice Assistant v1.0",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.version_label.pack(pady=(0, 30))
        
        # Статус
        self.status_frame = ctk.CTkFrame(self.sidebar, corner_radius=10, fg_color="#2d2d2d")
        self.status_frame.pack(fill="x", padx=15, pady=10)
        
        self.status_indicator = ctk.CTkLabel(
            self.status_frame,
            text="🔴",
            font=ctk.CTkFont(size=20)
        )
        self.status_indicator.pack(side="left", padx=10, pady=10)
        
        self.status_text = ctk.CTkLabel(
            self.status_frame,
            text="Спит",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.status_text.pack(side="left", padx=5)
        
        # Выбор голоса
        self.voice_label = ctk.CTkLabel(
            self.sidebar,
            text="Голос TTS:",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.voice_label.pack(fill="x", padx=15, pady=(20, 5))
        
        self.voice_var = ctk.StringVar(value="kseniya")
        self.voice_menu = ctk.CTkOptionMenu(
            self.sidebar,
            values=["kseniya (женский)", "baya (женский)", "xenia (женский)", 
                   "aidar (мужской)", "eugene (мужской)"],
            variable=self.voice_var,
            command=self._change_voice,
            corner_radius=8
        )
        self.voice_menu.pack(fill="x", padx=15, pady=5)
        
        # Чувствительность wake word
        self.sens_label = ctk.CTkLabel(
            self.sidebar,
            text="Чувствительность:",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.sens_label.pack(fill="x", padx=15, pady=(15, 5))
        
        self.sens_slider = ctk.CTkSlider(
            self.sidebar,
            from_=0.5,
            to=0.9,
            number_of_steps=8,
            command=self._change_sensitivity
        )
        self.sens_slider.set(0.75)
        self.sens_slider.pack(fill="x", padx=15, pady=5)
        
        self.sens_value = ctk.CTkLabel(
            self.sidebar,
            text="75%",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.sens_value.pack()
        
        # Кнопки управления
        self.btn_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=15, pady=20)
        
        self.start_btn = ctk.CTkButton(
            self.btn_frame,
            text="▶ Старт",
            command=self.start_listening,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            corner_radius=10,
            fg_color=self.success_color,
            hover_color="#27ae60"
        )
        self.start_btn.pack(fill="x", pady=5)
        
        self.stop_btn = ctk.CTkButton(
            self.btn_frame,
            text="⏹ Стоп",
            command=self.stop_listening,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            corner_radius=10,
            fg_color=self.error_color,
            hover_color="#c0392b",
            state="disabled"
        )
        self.stop_btn.pack(fill="x", pady=5)
        
        self.test_btn = ctk.CTkButton(
            self.btn_frame,
            text="🔊 Тест голоса",
            command=self.test_tts,
            font=ctk.CTkFont(size=12),
            height=35,
            corner_radius=10,
            fg_color="#34495e",
            hover_color="#2c3e50"
        )
        self.test_btn.pack(fill="x", pady=5)
        
        # Фоновый режим
        self.bg_mode_var = ctk.BooleanVar(value=False)
        self.bg_mode_switch = ctk.CTkSwitch(
            self.sidebar,
            text="Фоновый Wake Word",
            variable=self.bg_mode_var,
            command=self._toggle_bg_mode,
            font=ctk.CTkFont(size=12)
        )
        self.bg_mode_switch.pack(fill="x", padx=15, pady=(20, 5))
        
        # Автозапуск
        self.autostart_var = ctk.BooleanVar(value=False)
        self.autostart_switch = ctk.CTkSwitch(
            self.sidebar,
            text="Автозапуск Windows",
            variable=self.autostart_var,
            command=self._toggle_autostart,
            font=ctk.CTkFont(size=12)
        )
        self.autostart_switch.pack(fill="x", padx=15, pady=5)
        
        # === ПРАВАЯ ПАНЕЛЬ (лог и чат) ===
        self.main_frame = ctk.CTkFrame(self.root, corner_radius=15)
        self.main_frame.grid(row=0, column=1, padx=(0, 20), pady=20, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)
        
        # Заголовок
        self.header = ctk.CTkLabel(
            self.main_frame,
            text="История разговора",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        self.header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")
        
        # Чат/лог
        self.chat_frame = ctk.CTkFrame(self.main_frame, corner_radius=10, fg_color="#252525")
        self.chat_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.chat_frame.grid_columnconfigure(0, weight=1)
        self.chat_frame.grid_rowconfigure(0, weight=1)
        
        self.chat_text = ctk.CTkTextbox(
            self.chat_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            corner_radius=10,
            fg_color="transparent",
            text_color="#e0e0e0"
        )
        self.chat_text.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.chat_text.configure(state="disabled")
        
        # Текущая команда
        self.command_frame = ctk.CTkFrame(self.main_frame, corner_radius=10, fg_color="#2d2d2d")
        self.command_frame.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="ew")
        
        self.command_label = ctk.CTkLabel(
            self.command_frame,
            text="Скажи 'Привет' для активации",
            font=ctk.CTkFont(size=13, slant="italic"),
            text_color=self.accent_color
        )
        self.command_label.pack(pady=15)
        
        # Индикатор активности (визуализация звука)
        self.viz_canvas = ctk.CTkCanvas(self.main_frame, height=30, bg="#1a1a1a", highlightthickness=0)
        self.viz_canvas.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.viz_bars = []
        for i in range(20):
            bar = self.viz_canvas.create_rectangle(i*35+5, 15, i*35+30, 15, fill=self.accent_color, outline="")
            self.viz_bars.append(bar)
        
        # Подсказка команд
        self.hint_label = ctk.CTkLabel(
            self.main_frame,
            text="💡 Команды: время, студия, браузер, ютуб, спотифай, телеграм, выключи, перезагрузи...",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.hint_label.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="w")
    
    def _init_engine(self):
        def init():
            try:
                self._add_log("🚀 Инициализация...", "system")
                self.engine = VoiceEngine(on_text_callback=self.on_recognized)
                self._add_log("✅ Готов! Скажи 'Привет' для активации", "success")
            except Exception as e:
                self._add_log(f"❌ Ошибка: {e}", "error")
        
        threading.Thread(target=init, daemon=True).start()
    
    def _add_log(self, message: str, msg_type="normal"):
        self.chat_text.configure(state="normal")
        
        colors = {
            "user": "#00b4d8",      # Голубой
            "assistant": "#2ecc71",  # Зелёный
            "system": "#95a5a6",     # Серый
            "error": "#e74c3c",      # Красный
            "success": "#2ecc71",    # Зелёный
            "warning": "#f39c12"     # Оранжевый
        }
        
        color = colors.get(msg_type, "#e0e0e0")
        prefix = {
            "user": "👤 ",
            "assistant": "🤖 ",
            "system": "⚙️ ",
            "error": "❌ ",
            "success": "✅ ",
            "warning": "⚠️ "
        }.get(msg_type, "")
        
        self.chat_text.insert("end", f"{prefix}{message}\n", msg_type)
        self.chat_text.tag_config(msg_type, foreground=color)
        self.chat_text.see("end")
        self.chat_text.configure(state="disabled")
        
        logger.info(message)
    
    def _update_visualizer(self, active=False, level=0):
        """Обновляет визуализатор звука"""
        for i, bar in enumerate(self.viz_bars):
            if active:
                import random
                height = random.randint(5, 25) * level
                self.viz_canvas.coords(bar, i*35+5, 30-height, i*35+30, 30)
                self.viz_canvas.itemconfig(bar, fill=self.accent_color if level > 0.3 else "#34495e")
            else:
                self.viz_canvas.coords(bar, i*35+5, 15, i*35+30, 15)
                self.viz_canvas.itemconfig(bar, fill="#34495e")
        
        if self.is_running:
            self.root.after(50, lambda: self._update_visualizer(active, level))
    
    def on_recognized(self, text: str):
        self.root.after(0, lambda: self._handle_recognition(text))
    
    def _handle_recognition(self, text: str):
        self.command_label.configure(text=f"👤 {text}")
        self._update_visualizer(active=True, level=0.8)
        
        if not self.engine:
            return
        
        result = self.engine.process_text(text)
        
        if result is None:
            return
        
        # Обновляем статус
        if self.engine.is_active:
            self.status_indicator.configure(text="🟢")
            self.status_text.configure(text="Активен")
            self.command_label.configure(text="🎤 Слушаю команды... (скажи 'пока' для выхода)")
        else:
            self.status_indicator.configure(text="🔴")
            self.status_text.configure(text="Спит")
            self.command_label.configure(text="Скажи 'Привет' для активации")
        
        reply = result.get("reply")
        action = result.get("action")
        stop = result.get("stop", False)
        
        if reply:
            self._add_log(reply, "assistant")
            self.engine.speak(reply)
        
        if action:
            self.engine.execute_action(action)
            self._add_log(f"Выполнено: {action}", "system")
        
        if stop:
            self.stop_listening()
    
    def start_listening(self):
        if not self.engine:
            self._add_log("Движок не готов", "error")
            return
        
        self.is_running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._update_visualizer(active=True)
        
        self._add_log("▶ Старт прослушивания", "system")
        
        self.listen_thread = threading.Thread(
            target=self.engine.start_listening,
            args=(self.on_recognized,),
            daemon=True
        )
        self.listen_thread.start()
    
    def stop_listening(self):
        self.is_running = False
        if self.engine:
            self.engine.stop_listening()
            self.engine.is_active = False
        
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_indicator.configure(text="🔴")
        self.status_text.configure(text="Остановлен")
        self._update_visualizer(active=False)
        
        self._add_log("⏹ Стоп", "system")
    
    def test_tts(self):
        if self.engine:
            voice = self.voice_var.get().split()[0]
            self.engine.speak(f"Проверка голоса {voice}. Всё работает отлично!")
            self._add_log("🔊 Тест TTS...", "system")
    
    def _change_voice(self, choice):
        """Смена голоса TTS"""
        if self.engine:
            voice = choice.split()[0]
            # Обновляем в core через config
            import assistant.config as config
            config.TTS_SPEAKER = voice
            self._add_log(f"🎙️ Голос изменён на {voice}", "system")
    
    def _change_sensitivity(self, value):
        """Изменение чувствительности wake word"""
        self.sens_value.configure(text=f"{int(value*100)}%")
        if self.engine:
            # Обновляем threshold
            pass  # Реализуем в core
    
    def _toggle_bg_mode(self):
        """Включение/выключение фонового режима"""
        enabled = self.bg_mode_var.get()
        if enabled:
            self._add_log("🌙 Фоновый режим включён (в разработке)", "warning")
        else:
            self._add_log("☀️ Фоновый режим выключён", "system")
    
    def _toggle_autostart(self):
        """Автозапуск с Windows"""
        enabled = self.autostart_var.get()
        if enabled:
            self._add_log("🔄 Автозапуск включён (в разработке)", "warning")
        else:
            self._add_log("🔄 Автозапуск выключён", "system")
    
    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()
    
    def on_close(self):
        self.stop_listening()
        self.root.destroy()