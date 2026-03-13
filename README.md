🎵 Mumble Music & Voice Bot <br>
Docker-бот для Mumble с воспроизведением музыки и синтезом речи (TTS) <br>
🎧 Играет MP3 из папки <br>
🗣️ Говорит голосом через Silero TTS <br>
💬 Управляется из чата Mumble <br>
🐳 Развёртывается одной командой <br>


<h3> 🚀 Быстрый старт </h3>
<br>
1️⃣ Клонируйте репозиторий
 <br>
 
```bash
git clone https://github.com/YOUR-USERNAME/mumble-music-bot.git
cd mumble-music-bot
```

<br>
2️⃣ Добавьте музыку
<br>
Закиньте MP3-файлы в папку music/:
<br>

```
music/
├── gta_iv.mp3
├── sound.mp3
└── track.mp3
```
<br>

3️⃣ Настройте подключение
<br>

Отредактируйте файл .env его надо создать:
<br>

```bash
nano .env
```

<br>

```bash
MUMBLE_HOST  = Адрес Mumble-сервера (обязательно)
MUMBLE_PORT  = Порт сервера
MUMBLE_USER  = Имя бота в Mumble
MUMBLE_PASSWORD  = Пароль сервера (если есть)
MUMBLE_CHANNEL  = Канал для входа (пусто = корень)

# === Audio Settings ===
MUMBLE_BANDWIDTH=72000  оставить как есть
MUMBLE_LOOP_RATE=0.01  оставить как есть

# === TTS Settings ===
TTS_API_URL=http://silero-tts:8000
TTS_DEFAULT_SPEAKER=aidar    # Голос по умолчанию при первом запуске
TTS_PITCH=52                  # Дефолтный pitch (0-100)
TTS_RATE=55                   # Дефолтный rate (0-100)
TTS_TEXT_LIMIT=150

# === Bot Settings ===
BOT_CERT_FILE=/app/certs/bot_cert.pem оставить как есть
BOT_KEY_FILE=/app/certs/bot_key.pem оставить как есть
MUSIC_FOLDER=/app/music оставить как есть
DEFAULT_SONG="" звук при подключении
BOT_VOLUME=1
# === Debug ===
DEBUG=true можно выключить
```

<br>
4️⃣ Запустите бота
<br>

```bash
docker-compose up --build -d
```

<br>
💬 Команды бота
<br>
🎵 Музыка
<br>
- !play  Воспроизвести трек<br>
- !stop  Остановить воспроизведение<br>
- !list  Показать доступные треки<br>
- !volume <0.0-1.0>  Изменить громкость<br>
<br>
<br>

> 🔍 Умный поиск: можно вводить не полное название
<br> !play sound → найдёт sound.mp3
<br> !play s → найдёт первый трек на букву "s"

<br>

🗣️ TTS (Синтез речи):
<br>

- !speak  Озвучить текст
- !tts  Показать настройки TTS
- !tts <param> <value>  Изменить настройку пример !tts speaker aidar
<br>
<br>

Команды !speak:

- --speaker xeina (доступны: xenia, aidar, baya, kseniya, eugene, random) Выбор голоса
- --pitch  0–100 (50 = норма) Высота голоса (>50 = выше)
- --rate  0–100 (50 = норма) Скорость речи (>50 = быстрее)
- --reset  -- Сбросить настройки к дефолту

<br>

<br>

Примеры использования:
<br>
```
!speak {{ текст }} {{ команды --speaker --rate -- pitch }}
!speak Привет
!speak Привет от Айдара --speaker aidar 
!speak Быстрая высокая речь --pitch 60 --rate 55 
!speak Медленный мягкий голос --speaker baya --pitch 45 --rate 40 
!speak раз два три --speaker aidar --pitch 32 --rate 12
```
<br>
❓ Справка
<br>
- !help Показать все доступные команды
<br>
<br>

```

TL:DR

1) закинуть mp3 музыку в music
2) в файле .env настроить подключение
3) пуск docker-compose up -d --build
4) команды !list, !play ...
!play можно не до конца писать например 
!play sound
или
!play s


🛡️ Защита от мута пользователями
1) docker-compose up --build -d
2) выключаем docker-compose down
3) снова включаем docker-compose up --build -d

типичные примеры:

!speak раз два три --speaker aidar --pitch 32 --rate 12
!speak <текст> — синтез речи через Silero TTS.

Опции:
--speaker <имя>  — голос: xenia, aidar, baya, kseniya, eugene, random
--pitch <0-100>  — высота голоса (50 = норма, >50 = выше)
--rate <0-100>   — скорость речи (50 = норма, >50 = быстрее)

Примеры:
!speak Привет
!speak Привет от Айдара --speaker aidar 
!speak Быстрая высокая речь --pitch 60 --rate 55 
!speak Медленный мягкий голос --speaker baya --pitch 45 --rate 40 
"""
```

Сделано с ❤️ для сообщества Mumble







