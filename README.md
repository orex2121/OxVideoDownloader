<p align="center">
  <img src="assets/app.png" alt="OxVideoDownloader Logo" width="96" />
</p>

<h1 align="center">OxVideoDownloader</h1>

<p align="center">
  A portable Windows desktop video downloader and media converter with a modern dark UI.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.2.0-d47a39?style=flat-square" alt="Version 0.2.0" />
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square" alt="Platform: Windows" />
  <img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/GUI-Tkinter-4B8BBE?style=flat-square" alt="GUI: Tkinter" />
  <img src="https://img.shields.io/badge/engine-yt--dlp-FF0000?style=flat-square" alt="Engine: yt-dlp" />
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="OxVideoDownloader Main Window" width="820" />
</p>

<a id="languages"></a>
<p align="center">
  <a href="#english">🇬🇧 English</a> | <a href="#russian">🇷🇺 Русский</a>
</p>

---

<a id="english"></a>
## 🇬🇧 English

**OxVideoDownloader** is a portable desktop application for Windows that downloads videos, audio tracks, and playlists from over 1,800 websites and converts local media files through a clean, modern dark interface.

### ✨ Features

- **Engine & Queue Management:** Powered by `yt-dlp` and `FFmpeg`. Downloads single videos, audio tracks, and entire playlists from a link. Features a multi-task queue displaying thumbnails, source, duration, file size, status, live transfer speed, and ETA per task, with full controls (`Start All`, `Pause All`, `Restart`, `Remove`, `Remove Completed`).
- **Quality Presets:**
  - **Video:** `Best`, `2160p` (4K), `1440p`, `1080p` (Full HD), `720p` (HD), `480p`, `360p`.
  - **Audio:** `Best`, `~256 kbps`, `~128 kbps`.
- **Convert-While-Downloading:** Remux or transcode on the fly into `MP4`, `MKV`, `WEBM`, `MOV`, or `AVI` containers using `H.264`, `H.265 (HEVC)`, `VP9`, or `AV1` codecs. Supports concurrent segment downloading and browser sign-in cookies for age-restricted or member-only videos.
- **Local Media Converter (`Convert` Tab):** Convert local media files between `MP4`, `MKV`, `WEBM`, `MOV`, `AVI`, `MP3`, `M4A`, `WAV`, and `FLAC`. Includes advanced controls for CRF quality and audio bitrate, with options to convert **Now** or queue for **Later**.
- **100% Portable:** Zero installation and no registry entries—the entire application resides in a single folder and runs directly from a USB stick. `FFmpeg` binaries are not committed to the repository; on first launch, the app checks the local `ffmpeg\` folder and downloads them automatically via a cancelable progress dialog.
- **Customization & Settings:** 5 interface languages (English, Russian, German, Spanish, French), Light and dark **Obsidian Copper** themes, automatic retry for failed downloads, and custom download directory selection.

### 🌐 Supported Sources

| Platform | Domain | Platform | Domain | Platform | Domain |
| :--- | :--- | :--- | :--- | :--- | :--- |
| <img src="assets/hosters/youtube.com.png" width="16" /> **YouTube** | `youtube.com` | <img src="assets/hosters/tiktok.com.png" width="16" /> **TikTok** | `tiktok.com` | <img src="assets/hosters/x.com.png" width="16" /> **X / Twitter** | `x.com` |
| <img src="assets/hosters/rutube.ru.png" width="16" /> **Rutube** | `rutube.ru` | <img src="assets/hosters/dailymotion.com.png" width="16" /> **Dailymotion** | `dailymotion.com` | <img src="assets/hosters/instagram.com.png" width="16" /> **Instagram** | `instagram.com` |
| <img src="assets/hosters/vk.com.png" width="16" /> **VK Video** | `vk.com` | <img src="assets/hosters/vimeo.com.png" width="16" /> **Vimeo** | `vimeo.com` | <img src="assets/hosters/facebook.com.png" width="16" /> **Facebook** | `facebook.com` |
| <img src="assets/hosters/ok.ru.png" width="16" /> **OK.ru** | `ok.ru` | <img src="assets/hosters/twitch.tv.png" width="16" /> **Twitch** | `twitch.tv` | <img src="assets/hosters/reddit.com.png" width="16" /> **Reddit** | `reddit.com` |

*…and 1,800+ more sites thanks to yt-dlp.*

### 📦 Getting Started

1. **Get the code:** Run `git clone` on the repository (or download and unzip the archive).
2. **Choose how to run:**
   - **A) Bring your own Python:** Install Python 3.12+ x64 with `pip`, install dependencies via `pip install -r requirements.txt`, then run `python oxvideodownloader.py` or double-click `"OxVideo Downloader.bat"`.
   - **B) Portable mode:** Place an embeddable Python 3.12 x64 environment (with `pip` and `requirements.txt` packages installed) inside a `python\` subfolder next to the app, then double-click `"OxVideo Downloader.exe"`.
3. **First launch:** The application checks for `FFmpeg` inside `ffmpeg\` and downloads the required binaries automatically.

### 🗂 Project Layout

```text
├── oxvideodownloader.py   # Application entry point
├── oxvd/
│   ├── core.py            # Download, queue, and FFmpeg conversion logic
│   ├── ui.py              # Tkinter GUI views and components
│   ├── themes.py          # Light and Obsidian Copper theme definitions
│   └── i18n.py            # Localization loader
├── assets/                # App icons and assets/hosters/<domain>.png icons
├── local/                 # 5 language translation files (EN, RU, DE, ES, FR)
├── launcher/
│   └── launcher.cs        # C# source for compiling "OxVideo Downloader.exe"
├── requirements.txt       # Python package dependencies
└── config.json / tasks.json  # Runtime state & queue (auto-created, not committed)
```

### ⚙️ How It Works

`yt-dlp` resolves media URLs, parses playlists, and downloads the selected video and audio streams with concurrent segment fetching. `FFmpeg` then merges separate streams, remuxes containers, or transcodes local and downloaded media to your target codec and quality settings.

### ⚖️ License & Fair Use

`yt-dlp` and `FFmpeg` are distributed and used under their respective open-source licenses. This application is intended solely for downloading and converting content that you own or have explicit permission and legal right to download.

[⬆ Back to language selection](#languages)

---

<a id="russian"></a>
## 🇷🇺 Русский

**OxVideoDownloader** — портативное настольное приложение для Windows с современным тёмным интерфейсом, предназначенное для скачивания видео, аудиодорожек и плейлистов с более чем 1800 сайтов, а также конвертации локальных медиафайлов.

### ✨ Возможности

- **Движок и управление очередью:** Работает на базе `yt-dlp` и `FFmpeg`. Скачивает одиночные видео, аудиодорожки и целые плейлисты по ссылке. Многозадачная очередь отображает превью, источник, длительность, размер файла, статус, текущую скорость загрузки и оставшееся время (ETA) для каждой задачи с полным набором элементов управления (`Start All`, `Pause All`, `Restart`, `Remove`, `Remove Completed`).
- **Пресеты качества:**
  - **Видео:** `Best`, `2160p` (4K), `1440p`, `1080p` (Full HD), `720p` (HD), `480p`, `360p`.
  - **Аудио:** `Best`, `~256 kbps`, `~128 kbps`.
- **Конвертация при скачивании:** Ремультиплексирование (remux) или перекодирование «на лету» в контейнеры `MP4`, `MKV`, `WEBM`, `MOV` или `AVI` с использованием кодеков `H.264`, `H.265 (HEVC)`, `VP9` или `AV1`. Поддерживается многопоточная загрузка сегментов и использование файлов cookie из браузера для видео с возрастными ограничениями или закрытым доступом по подписке.
- **Конвертер локальных файлов (вкладка `Convert`):** Конвертация локальных медиафайлов между форматами `MP4`, `MKV`, `WEBM`, `MOV`, `AVI`, `MP3`, `M4A`, `WAV` и `FLAC`. Включает гибкие настройки качества CRF и битрейта аудио с возможностью запустить конвертацию сразу (**Now**) или добавить в очередь на потом (**Later**).
- **100% портативность:** Не требует установки и не оставляет записей в реестре — всё приложение находится в одной папке и может запускаться напрямую с USB-накопителя. Бинарные файлы `FFmpeg` не включены в репозиторий: при первом запуске приложение проверяет локальную папку `ffmpeg\` и автоматически скачивает их через окно прогресса с возможностью отмены.
- **Персонализация и настройки:** 5 языков интерфейса (английский, русский, немецкий, испанский, французский), светлая и тёмная темы оформления (**Obsidian Copper**), автоматический повтор при сбоях загрузки и выбор пользовательской папки для сохранения файлов.

### 🌐 Поддерживаемые источники

| Платформа | Домен | Платформа | Домен | Платформа | Домен |
| :--- | :--- | :--- | :--- | :--- | :--- |
| <img src="assets/hosters/youtube.com.png" width="16" /> **YouTube** | `youtube.com` | <img src="assets/hosters/tiktok.com.png" width="16" /> **TikTok** | `tiktok.com` | <img src="assets/hosters/x.com.png" width="16" /> **X / Twitter** | `x.com` |
| <img src="assets/hosters/rutube.ru.png" width="16" /> **Rutube** | `rutube.ru` | <img src="assets/hosters/dailymotion.com.png" width="16" /> **Dailymotion** | `dailymotion.com` | <img src="assets/hosters/instagram.com.png" width="16" /> **Instagram** | `instagram.com` |
| <img src="assets/hosters/vk.com.png" width="16" /> **VK Video** | `vk.com` | <img src="assets/hosters/vimeo.com.png" width="16" /> **Vimeo** | `vimeo.com` | <img src="assets/hosters/facebook.com.png" width="16" /> **Facebook** | `facebook.com` |
| <img src="assets/hosters/ok.ru.png" width="16" /> **OK.ru** | `ok.ru` | <img src="assets/hosters/twitch.tv.png" width="16" /> **Twitch** | `twitch.tv` | <img src="assets/hosters/reddit.com.png" width="16" /> **Reddit** | `reddit.com` |

*…и ещё более 1800 сайтов благодаря yt-dlp.*

### 📦 Установка и запуск

1. **Получите исходный код:** Выполните `git clone` репозитория (или скачайте и распакуйте архив).
2. **Выберите способ запуска:**
   - **A) Системный Python:** Установите Python 3.12+ x64 с `pip`, установите зависимости командой `pip install -r requirements.txt`, после чего запустите `python oxvideodownloader.py` или дважды кликните по `"OxVideo Downloader.bat"`.
   - **B) Портативный режим:** Поместите портативное окружение Python 3.12 x64 (с установленным `pip` и пакетами из `requirements.txt`) в подпапку `python\` рядом с приложением, затем дважды кликните по `"OxVideo Downloader.exe"`.
3. **Первый запуск:** Приложение проверит наличие `FFmpeg` в папке `ffmpeg\` и автоматически докачает необходимые исполняемые файлы.

### 🗂 Структура проекта

```text
├── oxvideodownloader.py   # Точка входа приложения
├── oxvd/
│   ├── core.py            # Логика загрузки, очереди и конвертации через FFmpeg
│   ├── ui.py              # Компоненты и экраны графического интерфейса Tkinter
│   ├── themes.py          # Определения светлой темы и тёмной темы Obsidian Copper
│   └── i18n.py            # Загрузчик локализаций
├── assets/                # Иконки приложения и логотипы сервисов в assets/hosters/<domain>.png
├── local/                 # Файлы перевода на 5 языков (EN, RU, DE, ES, FR)
├── launcher/
│   └── launcher.cs        # Исходный код на C# для компиляции "OxVideo Downloader.exe"
├── requirements.txt       # Зависимости пакетов Python
└── config.json / tasks.json  # Состояние и очередь задач (создаются автоматически, вне Git)
```

### ⚙️ Как это работает

`yt-dlp` извлекает прямые ссылки на медиапотоки, обрабатывает плейлисты и скачивает выбранные видео- и аудиодорожки с параллельной загрузкой сегментов. Затем `FFmpeg` объединяет отдельные потоки, меняет контейнер без перекодирования (remux) или транскодирует скачанные и локальные файлы в соответствии с выбранным кодеком и настройками качества.

### ⚖️ Лицензия и добросовестное использование

`yt-dlp` и `FFmpeg` распространяются и используются в соответствии с их собственными лицензиями с открытым исходным кодом. Данное приложение предназначено исключительно для загрузки и конвертации контента, который принадлежит вам или на скачивание которого у вас есть явное разрешение и законное право.

[⬆ Вернуться к выбору языка](#languages)