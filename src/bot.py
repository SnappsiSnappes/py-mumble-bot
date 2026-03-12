#!/usr/bin/env python3
"""
Mumble Music Bot — чистая версия с реестром команд.
"""
import os
import sys
import subprocess
import time
import signal
import threading
from pathlib import Path
from typing import Optional, Callable, List
import queue

from Cert import GenerateMumbleCert

# === Загрузка переменных окружения ===
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# === Импорт Mumble (fallback для разных версий pymumble) ===
try:
    from pymumble_py3.mumble import Mumble
    from pymumble_py3.callbacks import (
        PYMUMBLE_CLBK_CONNECTED,
        PYMUMBLE_CLBK_DISCONNECTED,
        PYMUMBLE_CLBK_TEXTMESSAGERECEIVED,
    )
except ImportError:
    try:
        from pymumble.mumble import Mumble
        from pymumble_py3.constants import (
            PYMUMBLE_CLBK_CONNECTED,
            PYMUMBLE_CLBK_DISCONNECTED,
            PYMUMBLE_CLBK_TEXTMESSAGERECEIVED,
        )
    except ImportError:
        from pymumble_py3.mumble import Mumble

        PYMUMBLE_CLBK_CONNECTED = "connected"
        PYMUMBLE_CLBK_DISCONNECTED = "disconnected"
        PYMUMBLE_CLBK_TEXTMESSAGERECEIVED = "text_message_received"


# === Декоратор для регистрации команд ===
def command(name: str, description: str = "", min_args: int = 0):
    """Декоратор для регистрации команд бота."""

    def decorator(func: Callable):
        func._command_meta = {
            "name": name,
            "description": description,
            "min_args": min_args,
        }
        return func

    return decorator


class MumbleMusicBot:
    """Mumble-бот для воспроизведения локальных MP3-файлов."""

    def __init__(self, config: dict):
        self.config = config
        self.mumble: Optional[Mumble] = None
        self.is_playing = False
        self.stop_flag = False
        self.command_prefix = config.get("command_prefix", "!")
        self.current_volume = float(config.get("volume", 0.5))

        # 🔥 РЕЕСТР КОМАНД: имя → (метод, мета-данные)
        self._commands: dict[str, tuple[Callable, dict]] = {}
        self._register_commands()

        # Регистрация сигналов завершения
        signal.signal(signal.SIGINT, lambda s, f: self._shutdown())
        signal.signal(signal.SIGTERM, lambda s, f: self._shutdown())
        
            # 🔥 Очередь для TTS-запросов (чтобы не терять команды)
        self.tts_queue: queue.Queue = queue.Queue()
        
        # 🔥 Блокировка для безопасного доступа к состоянию
        self._state_lock = threading.Lock()
        
        # 🔥 Флаги теперь локальные для каждого типа воспроизведения
        self._music_playing = False
        self._tts_playing = False
        self._global_stop = False  # Только для полного завершения бота
        
        # Запускаем воркер очереди TTS
        threading.Thread(target=self._tts_worker, daemon=True, name="tts-worker").start()
        
        # 🔥 Persistent TTS-настройки (последние использованные значения)
        self._tts_last_speaker = config.get("tts_default_speaker", "xenia")
        self._tts_last_pitch = int(config.get("tts_pitch", 52))
        self._tts_last_rate = int(config.get("tts_rate", 55))
        
        # Блокировка для потокобезопасного доступа
        self._tts_settings_lock = threading.Lock()

    # === Регистрация команд ===
    def _register_commands(self):
        """Регистрирует все команды, помеченные декоратором @command."""
        for attr_name in dir(self):
            if attr_name.startswith("_"):
                continue
            attr = getattr(self, attr_name)
            if callable(attr) and hasattr(attr, "_command_meta"):
                meta = attr._command_meta
                self._commands[meta["name"]] = (attr, meta)

    # === Обработчик текстовых сообщений ===
    def _on_text_message(self, data):
        """Обработка входящих текстовых сообщений из Mumble."""
        if not (msg := getattr(data, "message", "") or "").strip():
            return

        sender = getattr(data, "username", "Unknown")
        if sender == self.config["user"]:  # Игнорируем свои сообщения
            return

        print(f"💬 {sender}: {msg}")

        # Парсинг команды
        if not msg.startswith(self.command_prefix):
            return

        parts = msg[len(self.command_prefix) :].strip().split(maxsplit=1)
        if not parts:
            return

        action = parts[0].lower()
        args = parts[1].split() if len(parts) > 1 else []

        # Выполнение команды
        if action in self._commands:
            handler, meta = self._commands[action]
            if len(args) < meta["min_args"]:
                self.send_text(
                    f"❌ Недостаточно аргументов. Использование: !{action} {'<arg> ' * meta['min_args']}"
                )
                return
            try:
                # Запускаем в отдельном потоке, если метод асинхронный
                if getattr(handler, "_async", False):
                    threading.Thread(target=handler, args=args, daemon=True).start()
                else:
                    handler(*args)
            except Exception as e:
                print(f"❌ Ошибка в команде {action}: {e}")
                self.send_text(f"❌ Ошибка: {str(e)[:100]}")

    def _speak_text(
    self, 
    text: str, 
    speaker: str = "xenia", 
    sample_rate: int = 48000,
    pitch: int = 52,
    rate: int = 55
) -> bool:
        """Синтез речи с надёжной доставкой в Mumble."""
        import requests
        import subprocess
        
        # 🔥 Проверяем подключение перед началом
        if not self.mumble or not hasattr(self.mumble, 'sound_output'):
            print("❌ TTS: Mumble не подключён")
            return False
        
        tts_url = self.config.get("tts_api_url", "http://silero-tts:8000")
        print(f"🗣️ TTS: '{text[:80]}...' | {speaker}, pitch={pitch}, rate={rate}")
        
        try:
            # === 1. Получаем аудио от Silero ===
            response = requests.get(
                f"{tts_url}/generate",
                params={
                    "text": text, "speaker": speaker, "sample_rate": sample_rate,
                    "pitch": pitch, "rate": rate
                },
                timeout=30,
                stream=True
            )
            response.raise_for_status()
            audio_data = response.content
            
            if len(audio_data) < 1000:  # Слишком короткий ответ
                print(f"⚠ TTS: подозрительно короткий ответ ({len(audio_data)} байт)")
            
            # === 2. Конвертируем через ffmpeg ===
            ffmpeg_cmd = [
                "ffmpeg", "-i", "pipe:0",
                "-f", "s16le", "-acodec", "pcm_s16le",
                "-ar", "48000", "-ac", "1",
                "-af", "volume=3.0,highpass=f=100,acompressor=threshold=-20dB:ratio=4:attack=20:release=250",
                "-loglevel", "error", "-"
            ]
            
            process = subprocess.Popen(
                ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            pcm_data, stderr = process.communicate(input=audio_data, timeout=60)
            
            if process.returncode != 0 or len(pcm_data) < 100:
                # Фоллбэк: простое усиление
                ffmpeg_simple = [
                    "ffmpeg", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le",
                    "-ar", "48000", "-ac", "1", "-af", "volume=3.5", "-loglevel", "error", "-"
                ]
                process = subprocess.Popen(
                    ffmpeg_simple, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                pcm_data, stderr = process.communicate(input=audio_data, timeout=60)
                if process.returncode != 0 or len(pcm_data) < 100:
                    print(f"❌ ffmpeg failed: {stderr.decode()[:200]}")
                    return False
            
            # === 3. 🔥 Стриминг с надёжной доставкой ===
            with self._state_lock:
                self._tts_playing = True
            
            CHUNK_SIZE = 960  # ~10ms @ 48kHz mono 16-bit
            total_chunks = len(pcm_data) // CHUNK_SIZE
            chunks_sent = 0
            
            # 🔥 Сбрасываем буфер перед началом (если есть такая возможность)
            if hasattr(self.mumble.sound_output, 'clear_buffer'):
                try:
                    self.mumble.sound_output.clear_buffer()
                except:
                    pass
            
            start_time = time.time()
            
            for i in range(0, len(pcm_data), CHUNK_SIZE):
                if self._global_stop:
                    break
                    
                chunk = pcm_data[i:i + CHUNK_SIZE]
                if len(chunk) < CHUNK_SIZE:
                    continue
                
                # 🔥 Адаптивная отправка с контролем буфера
                max_retries = 10
                for retry in range(max_retries):
                    if self._global_stop:
                        break
                        
                    if hasattr(self.mumble, 'sound_output'):
                        buffer_level = self.mumble.sound_output.get_buffer_size()
                        
                        if buffer_level > 0.5:  # Буфер почти полон — ждём
                            time.sleep(0.03)
                            continue
                        
                        # 🔥 Отправляем чанк
                        self.mumble.sound_output.add_sound(chunk)
                        chunks_sent += 1
                        break
                    else:
                        time.sleep(0.01)
                else:
                    print(f"⚠ TTS: не удалось отправить чанк {chunks_sent}/{total_chunks}")
                
                # 🔥 Точный тайминг: синхронизация с реальным временем
                expected_time = start_time + (chunks_sent * CHUNK_SIZE / 2 / 48000)
                sleep_time = expected_time - time.time()
                if 0 < sleep_time < 0.05:
                    time.sleep(sleep_time)
            
            # === 4. Очистка буфера с гарантией ===
            cleanup_start = time.time()
            while (
                hasattr(self.mumble, 'sound_output')
                and self.mumble.sound_output.get_buffer_size() > 0.05
                and not self._global_stop
                and time.time() - cleanup_start < 3.0  # До 3 секунд на очистку
            ):
                time.sleep(0.01)
            
            print(f"✅ TTS: отправлено {chunks_sent}/{total_chunks} чанков")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"❌ TTS API error: {e}")
            return False
        except subprocess.TimeoutExpired:
            print("❌ ffmpeg timeout")
            return False
        except Exception as e:
            print(f"❌ TTS error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            with self._state_lock:
                self._tts_playing = False
            if "process" in locals():
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except:
                    pass
    # === Воркер очереди ===
    def _tts_worker(self):
        """Фоновый обработчик очереди TTS-запросов."""
        while not self._global_stop:
            try:
                # Ждём запрос с таймаутом, чтобы можно было выйти при остановке
                task = self.tts_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            try:
                # 🔥 Выполняем синтез с повторными попытками
                success = False
                for attempt in range(3):  # До 3 попыток
                    if self._global_stop:
                        break
                    if self._speak_text(
                        text=task["text"],
                        speaker=task["speaker"],
                        sample_rate=task["sample_rate"],
                        pitch=task["pitch"],
                        rate=task["rate"]
                    ):
                        success = True
                        break
                    # Пауза перед повторной попыткой
                    time.sleep(0.5 * (attempt + 1))
                
                if not success and not self._global_stop:
                    print(f"❌ TTS не удалось после 3 попыток: {task['text'][:50]}")
                    
            except Exception as e:
                print(f"❌ Ошибка в TTS-воркере: {e}")
            finally:
                self.tts_queue.task_done()
    # === Команды бота (помечены декоратором @command) ===

    @command("play", "Воспроизвести трек из папки музыки", min_args=1)
    def cmd_play(self, *args: str):
        """!play <название> — поиск и воспроизведение MP3-файла."""
        search_name = " ".join(args).lower()

        if filepath := self._find_music_file(search_name):
            filename = Path(filepath).name
            self.send_text(f"🎵 Играю: {filename}")
            threading.Thread(
                target=self._play_mp3, args=(filepath,), daemon=True
            ).start()
        else:
            self.send_text(f"❌ Файл не найден: {search_name}")

    @command("stop", "Остановить воспроизведение и очистить очередь")
    def cmd_stop(self):
        """!stop — остановить музыку, речь и очистить очередь TTS."""
        
        # 🔥 1. Останавливаем текущее воспроизведение
        with self._state_lock:
            self._music_playing = False
            self._tts_playing = False
        
        # 🔥 2. Очищаем очередь TTS (дренируем все ожидающие задачи)
        cleared = 0
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()  # Забираем задачу
                self.tts_queue.task_done()   # Сообщаем, что задача "выполнена"
                cleared += 1
            except queue.Empty:
                break  # На всякий случай, если очередь опустела между проверками
        
        # 🔥 3. Логируем результат
        if cleared > 0:
            print(f"🗑️ TTS queue cleared: {cleared} задач удалено")
        
        # 🔥 4. Подтверждение пользователю
        if cleared > 0:
            self.send_text(f"⏹ Остановлено (+{cleared} в очереди отменено)")
        else:
            self.send_text("⏹ Остановлено")
        
    @command("volume", "Изменить громкость (0.0–1.0)", min_args=1)
    def cmd_volume(self, value: str):
        """!volume <0.0-1.0> — установить громкость."""
        try:
            new_vol = float(value)
            if 0.0 <= new_vol <= 1.0:
                self.current_volume = new_vol
                self.send_text(f"🔊 Громкость: {new_vol * 100:.0f}%")
                print(f"🔊 Громкость изменена: {new_vol * 100:.0f}%")
            else:
                self.send_text("⚠ Громкость должна быть от 0.0 до 1.0")
        except ValueError:
            self.send_text("❌ Неверный формат. Пример: !volume 0.7")

    @command("list", "Показать доступные треки (первые 10)")
    def cmd_list(self):
        """!list — список доступных MP3-файлов."""
        music_folder = self.config["music_folder"]
        files = [f for f in os.listdir(music_folder) if f.endswith(".mp3")]

        if files:
            file_list = "\n".join(f"🎵 {f}" for f in sorted(files)[:])
            self.send_text(f"📋 Доступные треки:\n{file_list}")
        else:
            self.send_text("📭 Нет MP3-файлов в папке")

    @command("help", "Показать справку по командам")
    def cmd_help(self):
        """!help — показать список команд."""
        lines = ["📖 Доступные команды:"]
        for name, (_, meta) in sorted(self._commands.items()):
            desc = meta.get("description", "Без описания")
            min_args = meta.get("min_args", 0)
            args_hint = " <arg>" * min_args if min_args else ""
            lines.append(f"• !{name}{args_hint} — {desc}")
        self.send_text("\n".join(lines))

    @command("speak", "Озвучить текст через Silero TTS", min_args=1)
    def cmd_speak(self, *args: str):
        """
        !speak <текст> [--speaker/--pitch/--rate] — синтез речи.
        
        💡 Параметры запоминаются: следующий !speak использует последние значения.
        Используйте --reset для сброса к дефолту.
        """
        # === Парсинг аргументов ===
        speaker = None  # None = использовать последнее сохранённое
        pitch = None
        rate = None
        text_parts = []
        
        VALID_SPEAKERS = {"xenia", "aidar", "baya", "kseniya", "eugene", "random"}
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg == "--speaker" and i + 1 < len(args):
                candidate = args[i + 1].lower()
                if candidate in VALID_SPEAKERS:
                    speaker = candidate  # Явно задан — запомним позже
                    i += 2
                else:
                    self.send_text(f"❌ Неизвестный голос: {candidate}")
                    return
            elif arg == "--pitch" and i + 1 < len(args):
                try:
                    pitch = int(args[i + 1])
                    if not (0 <= pitch <= 100): raise ValueError
                    i += 2
                except ValueError:
                    self.send_text("❌ Pitch: 0–100")
                    return
            elif arg == "--rate" and i + 1 < len(args):
                try:
                    rate = int(args[i + 1])
                    if not (0 <= rate <= 100): raise ValueError
                    i += 2
                except ValueError:
                    self.send_text("❌ Rate: 0–100")
                    return
            elif arg == "--reset":
                # Сброс к дефолтным значениям из конфига
                with self._tts_settings_lock:
                    self._tts_last_speaker = self.config.get("tts_default_speaker", "xenia")
                    self._tts_last_pitch = int(self.config.get("tts_pitch", 52))
                    self._tts_last_rate = int(self.config.get("tts_rate", 55))
                self.send_text("🔄 TTS-настройки сброшены к дефолту")
                return
            elif arg.startswith("--"):
                self.send_text(f"❌ Неизвестный параметр: {arg}")
                return
            else:
                text_parts.append(arg)
                i += 1
        
        text = " ".join(text_parts).strip()
        if not text:
            self.send_text("❌ Введите текст для озвучки")
            return
        
        # Лимит текста
        max_len = int(os.getenv("TTS_TEXT_LIMIT", 930))
        if len(text) > max_len:
            text = text[:max_len] + "..."
        
        # 🔥 Подставляем последние сохранённые значения, если не заданы явно
        with self._tts_settings_lock:
            if speaker is None:
                speaker = self._tts_last_speaker
            else:
                self._tts_last_speaker = speaker  # Сохраняем новое
                
            if pitch is None:
                pitch = self._tts_last_pitch
            else:
                self._tts_last_pitch = pitch
                
            if rate is None:
                rate = self._tts_last_rate
            else:
                self._tts_last_rate = rate
            
            # Копируем текущие значения для лога
            current_speaker, current_pitch, current_rate = speaker, pitch, rate
        
        # 🔥 Мгновенное подтверждение с показом используемых параметров
        params_hint = []
        if current_speaker != self.config.get("tts_default_speaker", "xenia"):
            params_hint.append(f"🎙{current_speaker}")
        if current_pitch != int(self.config.get("tts_pitch", 52)):
            params_hint.append(f"p{current_pitch}")
        if current_rate != int(self.config.get("tts_rate", 55)):
            params_hint.append(f"r{current_rate}")
        
        hint = f" [{' '.join(params_hint)}]" if params_hint else ""
        self.send_text(f"🗣️{hint} {text[:50]}{'...' if len(text)>50 else ''}")
        
        # Запускаем в очередь
        self.tts_queue.put({
            "text": text,
            "speaker": speaker,
            "pitch": pitch,
            "rate": rate,
            "sample_rate": 48000,
        })
        
        
    @command("tts", "Показать или изменить TTS-настройки")
    def cmd_tts(self, *args: str):
        """
        !tts — показать текущие настройки
        !tts <speaker|pitch|rate> <значение> — изменить настройку
        !tts reset — сбросить к дефолту
        """
        if not args:
            # Показать текущие настройки
            with self._tts_settings_lock:
                speaker = self._tts_last_speaker
                pitch = self._tts_last_pitch
                rate = self._tts_last_rate
            
            default_speaker = self.config.get("tts_default_speaker", "xenia")
            default_pitch = int(self.config.get("tts_pitch", 52))
            default_rate = int(self.config.get("tts_rate", 55))
            
            indicators = []
            if speaker != default_speaker: indicators.append("✦")
            if pitch != default_pitch: indicators.append("✦")
            if rate != default_rate: indicators.append("✦")
            
            status = "🔧" if indicators else "✅"
            self.send_text(
                f"{status} TTS-настройки:\n"
                f"• speaker: {speaker} {'(дефолт)' if speaker == default_speaker else f'← изменено'}\n"
                f"• pitch: {pitch} {'(дефолт)' if pitch == default_pitch else f'← изменено'}\n"
                f"• rate: {rate} {'(дефолт)' if rate == default_rate else f'← изменено'}\n"
                f"💡 Используйте !speak --reset для сброса"
            )
            return
        
        # Изменение настройки
        if len(args) < 2:
            self.send_text("❌ Использование: !tts <speaker|pitch|rate> <значение>")
            return
        
        setting, value = args[0].lower(), args[1]
        
        with self._tts_settings_lock:
            if setting == "speaker":
                VALID = {"xenia", "aidar", "baya", "kseniya", "eugene", "random"}
                if value.lower() in VALID:
                    self._tts_last_speaker = value.lower()
                    self.send_text(f"✅ speaker = {value.lower()}")
                else:
                    self.send_text(f"❌ Доступные голоса: {', '.join(sorted(VALID))}")
                    
            elif setting == "pitch":
                try:
                    val = int(value)
                    if 0 <= val <= 100:
                        self._tts_last_pitch = val
                        self.send_text(f"✅ pitch = {val}")
                    else:
                        self.send_text("❌ pitch: 0–100")
                except ValueError:
                    self.send_text("❌ pitch должен быть числом")
                    
            elif setting == "rate":
                try:
                    val = int(value)
                    if 0 <= val <= 100:
                        self._tts_last_rate = val
                        self.send_text(f"✅ rate = {val}")
                    else:
                        self.send_text("❌ rate: 0–100")
                except ValueError:
                    self.send_text("❌ rate должен быть числом")
                    
            elif setting == "reset":
                self._tts_last_speaker = self.config.get("tts_default_speaker", "xenia")
                self._tts_last_pitch = int(self.config.get("tts_pitch", 52))
                self._tts_last_rate = int(self.config.get("tts_rate", 55))
                self.send_text("🔄 TTS-настройки сброшены")
            else:
                self.send_text("❌ Unknown setting. Use: speaker, pitch, rate, reset")
    def _find_music_file(self, search_name: str) -> Optional[str]:
        """
        Поиск MP3-файла по имени (точное совпадение или частичное).
        Returns: путь к файлу или None.
        """
        music_folder = Path(self.config["music_folder"])
        if not music_folder.exists():
            return None

        # Вариант 1: точное совпадение (с .mp3 или без)
        if search_name.endswith(".mp3"):
            candidate = music_folder / search_name
            if candidate.exists():
                return str(candidate)
        else:
            candidate = music_folder / f"{search_name}.mp3"
            if candidate.exists():
                return str(candidate)

        # Вариант 2: частичное совпадение (регистронезависимое)
        for file in music_folder.glob("*.mp3"):
            if search_name in file.name.lower():
                return str(file)

        return None

    def _play_mp3(self, path: str) -> bool:
        """Воспроизведение MP3 с изолированным флагом."""
        if not Path(path).exists():
            return False
        
        with self._state_lock:
            if self._music_playing:
                return False  # Уже играет музыка
            self._music_playing = True
        
        print(f"🎵 {path}")
        
        ffmpeg_cmd = [
            "ffmpeg", "-i", path, "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", "48000", "-ac", "1", "-af", f"volume={self.current_volume}",
            "-loglevel", "error", "-"
        ]
        
        try:
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            CHUNK_SIZE = 1600
            
            while self._music_playing and not self._global_stop:
                if hasattr(self.mumble, "sound_output"):
                    if self.mumble.sound_output.get_buffer_size() > 0.3:
                        time.sleep(0.005)
                        continue
                chunk = process.stdout.read(CHUNK_SIZE)
                if not chunk:
                    break
                if len(chunk) == CHUNK_SIZE:
                    self.mumble.sound_output.add_sound(chunk)
                time.sleep(0.01)
            
            return True
        except Exception as e:
            print(f"❌ MP3 error: {e}")
            return False
        finally:
            with self._state_lock:
                self._music_playing = False
            if "process" in locals():
                process.terminate()
                
                
    # === Методы подключения и callbacks ===

    def connect(self):
        """Подключение к Mumble-серверу."""
        host, port = self.config["host"], self.config["port"]
        print(f"🔌 Подключение к {host}:{port}...")

        self.mumble = Mumble(
            host=host,
            port=port,
            user=self.config["user"],
            password=self.config["password"],
            certfile=self.config["certfile"],
            keyfile=self.config["keyfile"],
            reconnect=True,
            stereo=False,
            debug=False,
        )

        self._setup_callbacks()
        self._apply_mumble_settings()

        self.mumble.start()
        self.mumble.is_ready()
        print("✓ Готов")
        self.join_channel(self.config["channel"])

    def _setup_callbacks(self):
        """Регистрация callback-методов."""
        callbacks = [
            (PYMUMBLE_CLBK_CONNECTED, self.on_connected),
            (PYMUMBLE_CLBK_DISCONNECTED, self.on_disconnected),
            (PYMUMBLE_CLBK_TEXTMESSAGERECEIVED, self._on_text_message),
        ]
        for event, handler in callbacks:
            try:
                self.mumble.callbacks.set_callback(event, handler)
            except Exception as e:
                print(f"⚠ Не удалось зарегистрировать {event}: {e}")

    def _apply_mumble_settings(self):
        """Применение настроек Mumble (bandwidth, loop_rate)."""
        settings = [
            ("set_bandwidth", self.config["bandwidth"]),
            ("set_loop_rate", self.config["loop_rate"]),
        ]
        for method_name, value in settings:
            if hasattr(self.mumble, method_name):
                try:
                    getattr(self.mumble, method_name)(value)
                except Exception:
                    pass  # Игнорируем, если метод не поддерживается

    def join_channel(self, name: str):
        """Переход в указанный канал."""
        if not name:
            return
        try:
            channel = self.mumble.channels.find_by_name(name)
            channel.move_in(self.mumble.users.myself_session)
            print(f"🎤 В канале: {name}")
        except Exception as e:
            print(f"⚠ Не удалось войти в канал '{name}': {e}")

    def on_connected(self, event=None):
        """Callback: успешно подключились."""
        print("✅ Подключено к серверу!")
        self.send_text("🤖 Бот подключен! 🎵")
        # Автовоспроизведение дефолтного трека
        if default := self.config.get("default_song"):
            song_path = Path(self.config["music_folder"]) / default
            if song_path.exists():
                threading.Thread(
                    target=self._play_mp3, args=(str(song_path),), daemon=True
                ).start()

    def on_disconnected(self, event=None):
        """Callback: отключение от сервера."""
        print("❌ Отключено от сервера!")
        self.stop_flag = True

    def send_text(self, msg: str):
        """Отправка текстового сообщения в текущий канал."""
        try:
            if channel := self.mumble.my_channel():
                channel.send_text_message(msg)
                print(f"💬 {msg}")
        except Exception:
            pass  # Тихо игнорируем ошибки отправки

    def disconnect(self):
        """Корректное отключение от сервера."""
        print("👋 Отключаюсь...")
        self.stop_flag = True
        self.is_playing = False
        if self.mumble:
            try:
                self.mumble.stop()
            except Exception:
                pass

    def _shutdown(self):
        """Корректное завершение работы."""
        print("\n🛑 Завершение...")
        
        # 🔥 Сигнал всем потокам остановиться
        self._global_stop = True
        
        # 🔥 Ждём обработки очереди TTS (макс 5 секунд)
        try:
            self.tts_queue.join()
        except:
            pass
        
        # 🔥 Останавливаем Mumble
        self.disconnect()
        sys.exit(0)


# === Точка входа ===
def main():
    """Инициализация и запуск бота."""
    config = {
        
        "tts_default_speaker": os.getenv("TTS_DEFAULT_SPEAKER", "xenia"),
        "tts_pitch": int(os.getenv("TTS_PITCH", 52)),
        "tts_rate": int(os.getenv("TTS_RATE", 55)),

        "host": os.getenv("MUMBLE_HOST"),
        "port": int(os.getenv("MUMBLE_PORT", 64738)),
        "user": os.getenv("MUMBLE_USER", "MusicBot"),
        "password": os.getenv("MUMBLE_PASSWORD", ""),
        "certfile": os.getenv("BOT_CERT_FILE", "/app/certs/bot_cert.pem"),
        "keyfile": os.getenv("BOT_KEY_FILE", "/app/certs/bot_key.pem"),
        "channel": os.getenv("MUMBLE_CHANNEL", ""),
        "music_folder": os.getenv("MUSIC_FOLDER", "/app/music"),
        "default_song": os.getenv("DEFAULT_SONG", ""),
        "volume": float(os.getenv("BOT_VOLUME", 1.0)),
        "bandwidth": int(os.getenv("MUMBLE_BANDWIDTH", 72000)),
        "loop_rate": float(os.getenv("MUMBLE_LOOP_RATE", 0.01)),
        "command_prefix": os.getenv("COMMAND_PREFIX", "!"),
        "tts_api_url": os.getenv("TTS_API_URL", "http://silero-tts:8000"),
    }

    # Генерация сертификатов
    cert_dir = Path(config["certfile"]).parent
    cert_dir.mkdir(parents=True, exist_ok=True)

    if not GenerateMumbleCert(config["user"], config["certfile"], config["keyfile"]):
        print("❌ Не удалось создать сертификаты")
        sys.exit(1)

    # Запуск бота
    bot = MumbleMusicBot(config)
    try:
        bot.connect()
        print("\n🎧 Бот работает. Ожидание команд...")
        while not bot.stop_flag:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
    finally:
        bot.disconnect()


if __name__ == "__main__":
    main()
