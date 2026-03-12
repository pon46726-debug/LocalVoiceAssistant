import os
import json
import subprocess
import threading
import queue
import time
import difflib
import re
from datetime import datetime
from typing import Optional, Callable

import pyaudio
import torch
import numpy as np

try:
    from vosk import Model, KaldiRecognizer
except ImportError:
    print("Установите vosk: pip install vosk")
    raise

import assistant.config as config
from assistant.logger import setup_logger

logger = setup_logger()

# Словарь для замены английских слов на русские произношения
ENGLISH_TO_RUSSIAN = {
    'youtube': 'ютуб',
    'you tube': 'ютуб',
    'github': 'гитхаб',
    'git hub': 'гитхаб',
    'gitlab': 'гитлаб',
    'git lab': 'гитлаб',
    'spotify': 'спотифай',
    'spotify': 'спотифай',
    'discord': 'дискорд',
    'telegram': 'телеграм',
    'whatsapp': 'ватсап',
    'viber': 'вайбер',
    'steam': 'стим',
    'photoshop': 'фотошоп',
    'chrome': 'хром',
    'firefox': 'файрфокс',
    'edge': 'эдж',
    'vscode': 'вэс код',
    'vs code': 'вэс код',
    'code': 'код',
    'notepad': 'блокнот',
    'explorer': 'проводник',
    'calculator': 'калькулятор',
    'task manager': 'диспетчер задач',
    'cmd': 'командная строка',
    'terminal': 'терминал',
    'browser': 'браузер',
    'internet': 'интернет',
    'computer': 'компьютер',
    'pc': 'пэ си',
    'windows': 'виндовс',
    'microsoft': 'майкрософт',
    'google': 'гугл',
    'yandex': 'яндекс',
    'vk': 'вэ ка',
    'vkontakte': 'вконтакте',
    'instagram': 'инстаграм',
    'facebook': 'фейсбук',
    'twitter': 'твиттер',
    'tiktok': 'тик ток',
    'zoom': 'зум',
    'skype': 'скайп',
    'teams': 'тимс',
    'slack': 'слак',
    'trello': 'трелло',
    'jira': 'джира',
    'figma': 'фигма',
    'unity': 'юнити',
    'unreal': 'анриал',
    'blender': 'блендер',
    'maya': 'майя',
    '3ds max': 'три дэс макс',
    'autocad': 'автокад',
    'excel': 'эксель',
    'word': 'ворд',
    'powerpoint': 'повер поинт',
    'outlook': 'аутлук',
    'one drive': 'ван драйв',
    'dropbox': 'дропбокс',
    'github desktop': 'гитхаб десктоп',
    'sourcetree': 'соурс три',
    'postman': 'постман',
    'docker': 'докер',
    'kubernetes': 'кубернетис',
    'nginx': 'энжин икс',
    'apache': 'апач',
    'mysql': 'май эс ку эл',
    'postgresql': 'постгрес',
    'mongodb': 'монго дэ би',
    'redis': 'редис',
    'kafka': 'кафка',
    'rabbitmq': 'рэбит эм ку',
    'elasticsearch': 'эластик серч',
    'aws': 'эй дабл ю эс',
    'azure': 'азур',
    'gcp': 'джи си пи',
    'digitalocean': 'диджитал оушен',
    'heroku': 'хероку',
    'netlify': 'нетлифай',
    'vercel': 'версел',
    'cloudflare': 'клауд флэр',
}

class VoiceEngine:
    def __init__(self, on_text_callback: Optional[Callable] = None):
        self.on_text_callback = on_text_callback
        self.is_listening = False
        self.audio_queue = queue.Queue()
        self.tts_model = None
        self.tts_sample_rate = config.TTS_SAMPLE_RATE
        
        self.is_active = False
        self.last_command_time = 0
        self.command_cooldown = 2.0
        self.last_command_text = ""
        self.is_speaking = False
        self.speaking_lock = threading.Lock()
        
        self._init_stt()
        self._init_tts()
        logger.info("VoiceEngine инициализирован")
    
    def _init_stt(self):
        if not os.path.exists(config.VOSK_MODEL_PATH):
            logger.error(f"Модель Vosk не найдена: {config.VOSK_MODEL_PATH}")
            raise FileNotFoundError(f"Vosk model not found: {config.VOSK_MODEL_PATH}")
        
        self.vosk_model = Model(config.VOSK_MODEL_PATH)
        self.recognizer = KaldiRecognizer(self.vosk_model, config.AUDIO_SAMPLE_RATE)
        logger.info("Vosk STT загружен")
    
    def _init_tts(self):
        torch.set_num_threads(4)
        
        import sys
        old_path = sys.path.copy()
        
        try:
            if '' in sys.path:
                sys.path.remove('')
            if os.getcwd() in sys.path:
                sys.path.remove(os.getcwd())
            
            model_info = torch.hub.load(
                'snakers4/silero-models',
                'silero_tts',
                language=config.TTS_LANGUAGE,
                speaker=config.TTS_MODEL_ID,
                trust_repo=True,
                force_reload=False
            )
        finally:
            sys.path = old_path
        
        if isinstance(model_info, tuple) and len(model_info) >= 1:
            self.tts_model = model_info[0]
        elif isinstance(model_info, dict):
            self.tts_model = model_info['model']
            self.tts_sample_rate = model_info.get('sample_rate', config.TTS_SAMPLE_RATE)
        else:
            raise TypeError(f"Неизвестный тип: {type(model_info)}")
        
        if self.tts_model is None:
            raise RuntimeError("TTS модель не загружена!")
        
        logger.info(f"TTS готов (speaker: {config.TTS_SPEAKER})")
    
    def number_to_words(self, n: int) -> str:
        """Преобразует число в слова (0-9999)"""
        if n == 0:
            return "ноль"
        
        ones = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
        teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", 
                 "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
        tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", 
                "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
        hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", 
                    "шестьсот", "семьсот", "восемьсот", "девятьсот"]
        thousands = ["", "одна тысяча", "две тысячи", "три тысячи", "четыре тысячи",
                     "пять тысяч", "шесть тысяч", "семь тысяч", "восемь тысяч", "девять тысяч"]
        
        result = []
        
        # Тысячи
        if n >= 1000:
            t = n // 1000
            if t < 10:
                result.append(thousands[t])
            n %= 1000
        
        # Сотни
        if n >= 100:
            result.append(hundreds[n // 100])
            n %= 100
        
        # Десятки и единицы
        if n >= 20:
            result.append(tens[n // 10])
            n %= 10
            if n > 0:
                result.append(ones[n])
        elif n >= 10:
            result.append(teens[n - 10])
        elif n > 0:
            result.append(ones[n])
        
        return " ".join(result)
    
    def normalize_text_for_tts(self, text: str) -> str:
        """Нормализует текст для TTS: цифры в слова, английские слова в русские"""
        text = text.lower()
        
        # Заменяем английские слова
        for eng, rus in sorted(ENGLISH_TO_RUSSIAN.items(), key=lambda x: -len(x[0])):
            text = text.replace(eng.lower(), rus)
        
        # Заменяем числа на слова
        def replace_number(match):
            num = int(match.group())
            if 0 <= num <= 9999:
                return self.number_to_words(num)
            return match.group()
        
        text = re.sub(r'\b\d+\b', replace_number, text)
        
        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def get_current_time(self) -> str:
        now = datetime.now()
        hours = now.hour
        minutes = now.minute
        
        hour_word = "часов"
        if hours % 10 == 1 and hours % 100 != 11:
            hour_word = "час"
        elif 2 <= hours % 10 <= 4 and not 12 <= hours % 100 <= 14:
            hour_word = "часа"
        
        minute_word = "минут"
        if minutes % 10 == 1 and minutes % 100 != 11:
            minute_word = "минута"
        elif 2 <= minutes % 10 <= 4 and not 12 <= minutes % 100 <= 14:
            minute_word = "минуты"
        
        # Используем числа как есть, но нормализуем для TTS
        time_str = f"{hours} {hour_word}"
        if minutes > 0:
            time_str += f" {minutes} {minute_word}"
        
        return time_str
    
    def get_current_date(self) -> str:
        now = datetime.now()
        months = {
            1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
        }
        weekdays = {
            0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг",
            4: "пятница", 5: "суббота", 6: "воскресенье"
        }
        
        return f"{now.day} {months[now.month]} {now.year} года, {weekdays[now.weekday()]}"
    
    def recognize(self, audio_data: bytes) -> Optional[str]:
        with self.speaking_lock:
            if self.is_speaking:
                return None
        
        if self.recognizer.AcceptWaveform(audio_data):
            result = json.loads(self.recognizer.Result())
            text = result.get("text", "").strip().lower()
            if text:
                logger.info(f"Распознано: '{text}'")
                if self.on_text_callback:
                    self.on_text_callback(text)
                return text
        return None
    
    def check_wake_word(self, text: str) -> Optional[str]:
        for wake, reply in config.WAKE_WORDS.items():
            if wake in text:
                return reply
            if self._fuzzy_match(text, wake, threshold=0.75):
                return reply
        return None
    
    def check_sleep_word(self, text: str) -> bool:
        sleep_words = ["пока", "до свидания", "бай", "до встречи", "выключись", "спи"]
        for word in sleep_words:
            if word in text:
                return True
        return False
    
    def _fuzzy_match(self, text: str, pattern: str, threshold: float = None) -> bool:
        if threshold is None:
            threshold = config.FUZZY_THRESHOLD
        
        similarity = difflib.SequenceMatcher(None, text, pattern).ratio()
        if similarity >= threshold:
            return True
        
        text_words = text.split()
        pattern_words = pattern.split()
        
        for pw in pattern_words:
            for tw in text_words:
                word_sim = difflib.SequenceMatcher(None, tw, pw).ratio()
                if word_sim >= 0.8:
                    return True
        
        return False
    
    def _find_best_command(self, text: str):
        best_cmd = None
        best_action = None
        best_score = 0
        
        for cmd, action in config.COMMANDS.items():
            if cmd in text:
                return cmd, action, 1.0
            
            similarity = difflib.SequenceMatcher(None, text, cmd).ratio()
            
            text_words = set(text.split())
            cmd_words = set(cmd.split())
            if cmd_words:
                word_overlap = len(text_words & cmd_words) / len(cmd_words)
                similarity = max(similarity, word_overlap * 0.9)
            
            if similarity > best_score and similarity >= config.FUZZY_THRESHOLD:
                best_score = similarity
                best_cmd = cmd
                best_action = action
        
        return best_cmd, best_action, best_score
    
    def process_text(self, text: str) -> Optional[dict]:
        current_time = time.time()
        
        # Проверяем слово для отключения
        if self.check_sleep_word(text):
            self.is_active = False
            return {"reply": "До свидания! Выключаюсь", "action": None, "stop": True}
        
        # Проверяем wake word для активации
        wake_reply = self.check_wake_word(text)
        if wake_reply:
            self.is_active = True
            logger.info("Активирован!")
            return {"reply": wake_reply + ". Я слушаю. Скажи 'пока' чтобы выключить.", "action": None, "stop": False}
        
        # Если не активен — игнорируем
        if not self.is_active:
            return None
        
        # Не обрабатываем пока говорим
        with self.speaking_lock:
            if self.is_speaking:
                return None
        
        # Антидребезг
        if current_time - self.last_command_time < self.command_cooldown:
            if text == self.last_command_text:
                return None
            similarity = difflib.SequenceMatcher(None, text, self.last_command_text).ratio()
            if similarity > 0.7:
                logger.info(f"Игнорирую повтор (сходство {similarity:.0%})")
                return None
        
        logger.info(f"Обработка: '{text}'")
        
        # Специальные команды времени
        if "который час" in text or "сколько времени" in text or "время" in text:
            time_str = self.get_current_time()
            return {"reply": f"Сейчас {time_str}", "action": None}
        
        if "какое сегодня число" in text or "какая дата" in text or "дата" in text:
            date_str = self.get_current_date()
            return {"reply": f"Сегодня {date_str}", "action": None}
        
        # Ищем обычную команду
        cmd, action, score = self._find_best_command(text)
        
        if action:
            logger.info(f"Команда: '{cmd}' (сходство {score:.0%})")
            self.last_command_time = current_time
            self.last_command_text = text
            
            # Обрабатываем специальные действия
            real_action = action.get("action")
            if real_action in ["media_next", "media_play_pause", "volume_up", "volume_down", "volume_mute", "key_f"]:
                try:
                    import keyboard
                    key_map = {
                        "media_next": "next track",
                        "media_play_pause": "play/pause media",
                        "volume_up": "volume up",
                        "volume_down": "volume down",
                        "volume_mute": "volume mute",
                        "key_f": "f"
                    }
                    keyboard.press_and_release(key_map.get(real_action, real_action))
                    real_action = None
                except ImportError:
                    real_action = None
            
            return {
                "reply": action.get("reply", ""),
                "action": real_action,
                "stop": action.get("stop", False)
            }
        
        logger.info("Не распознано")
        return {"reply": "Не понял команду. Попробуй ещё раз.", "action": None}
    
    def speak(self, text: str):
        if self.tts_model is None:
            logger.error("TTS не готов!")
            return
        
        def _speak():
            try:
                with self.speaking_lock:
                    self.is_speaking = True
                
                # Нормализуем текст для TTS
                tts_text = self.normalize_text_for_tts(text)
                logger.info(f"TTS (нормализовано): '{tts_text}'")
                
                audio = self.tts_model.apply_tts(
                    text=tts_text,
                    speaker=config.TTS_SPEAKER,
                    sample_rate=self.tts_sample_rate
                )
                
                audio_np = audio.numpy() if torch.is_tensor(audio) else audio
                audio_np = audio_np / np.max(np.abs(audio_np))
                self._play_audio(audio_np, self.tts_sample_rate)
                
                time.sleep(0.3)
                
            except Exception as e:
                logger.error(f"Ошибка TTS: {e}")
                import traceback
                logger.error(traceback.format_exc())
            finally:
                with self.speaking_lock:
                    self.is_speaking = False
        
        thread = threading.Thread(target=_speak, daemon=True)
        thread.start()
        return thread
    
    def _play_audio(self, audio_np: np.ndarray, sample_rate: int):
        audio_int16 = (audio_np * 32767).astype(np.int16).tobytes()
        
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            output=True
        )
        
        chunk_size = 1024
        for i in range(0, len(audio_int16), chunk_size * 2):
            chunk = audio_int16[i:i + chunk_size * 2]
            stream.write(chunk)
        
        stream.stop_stream()
        stream.close()
        p.terminate()
    
    def execute_action(self, action: str):
        if not action:
            return
        
        logger.info(f"Выполнение: {action}")
        try:
            allowed = ('start ', 'notepad', 'calc', 'explorer', 'code',
                     'taskmgr', 'cmd', 'wt', 'shutdown ', 'https://', 
                     'msedge', 'chrome', 'firefox', 'telegram', 'discord',
                     'spotify', 'steam', 'photoshop', 'whatsapp', 'viber',
                     'rundll32')
            
            if not any(action.startswith(a) for a in allowed):
                logger.warning(f"Не разрешено: {action}")
                return
            
            if action.startswith('start https://'):
                subprocess.Popen(['start', action[6:]], shell=True)
            else:
                subprocess.Popen(action, shell=True)
                
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
    def start_listening(self, callback: Callable[[str], None]):
        self.is_listening = True
        
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=config.AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=config.AUDIO_CHUNK_SIZE,
            input_device_index=config.AUDIO_DEVICE
        )
        
        logger.info("Слушаю... (скажи 'Привет' для активации, 'пока' для выхода)")
        
        while self.is_listening:
            try:
                data = stream.read(config.AUDIO_CHUNK_SIZE, exception_on_overflow=False)
                text = self.recognize(data)
                
                if text:
                    callback(text)
                    
            except Exception as e:
                logger.error(f"Ошибка аудио: {e}")
        
        stream.stop_stream()
        stream.close()
        p.terminate()
        logger.info("Стоп")
    
    def stop_listening(self):
        self.is_listening = False