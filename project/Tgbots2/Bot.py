import glob
import os
import yt_dlp
import asyncio
import tempfile
from telegram import Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.error import BadRequest
import re

TOKEN = os.getenv("TOKEN")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли ссылку на YouTube, TikTok или Instagram, и я верну тебе видео."
    )

async def download_with_yt_dlp(url: str, outtmpl: str, status_message):
    loop = asyncio.get_running_loop()

    ydl_opts = {
        "format": "mp4",
        "outtmpl": outtmpl,
        "quiet": True
    }

    def run_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    try:
        await status_message.edit_text("⏳ Скачивание...")
        await loop.run_in_executor(None, run_download)
        await status_message.edit_text("✅ Скачивание завершено!")
        return True, None
    except Exception as e:
        return False, e


async def download_audio_with_yt_dlp(url: str, outtmpl_pattern: str, status_message):
    loop = asyncio.get_running_loop()

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl_pattern,
        "quiet": True,
        "postprocessors": [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    }

    def run_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    try:
        await status_message.edit_text("⏳ Скачивание аудио…")
        await loop.run_in_executor(None, run_download)
        await status_message.edit_text("🔁 Конвертация в MP3...")

        folder = os.path.dirname(outtmpl_pattern)
        mp3s = glob.glob(os.path.join(folder, "*.mp3"))
        if mp3s:
            mp3s.sort(key=os.path.getmtime, reverse=True)
            return True, mp3s[0]
        else:
            return False, "MP3 не найден после конверсии"
    except Exception as e:
        return False, e


async def audio_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = None

    if ctx.args:
        url = " ".join(ctx.args).strip()

    if not url:
        text = (update.message.text or "").strip()
        text = re.sub(r'^/audio(@\w+)?\s*', '', text, count=1)
        if text:
            url = text.split()[0].strip()

    if not url and update.message.reply_to_message and update.message.reply_to_message.text:
        url = update.message.reply_to_message.text.strip().split()[0]

    if not url or not url.startswith(("http://", "https://")):
        await update.message.reply_text(
            "Использование: /audio <ссылка> или ответьте на сообщение с ссылкой командой /audio\n"
            "Пример: /audio https://youtu.be/abc123"
        )
        return

    status = await update.message.reply_text("✅ Принято в обработку — извлекаю аудио…")
    tmp = tempfile.TemporaryDirectory()
    try:
        outtmpl = os.path.join(tmp.name, "audio.%(ext)s")
        ok, result = await download_audio_with_yt_dlp(url, outtmpl, status)
        if not ok:
            return await status.edit_text(f"❌ Ошибка при скачивании:\n{result}")

        audio_path = result
        await status.edit_text("✅ Готово! Отправляю MP3…")
        with open(audio_path, "rb") as f:
            await update.message.reply_audio(audio=f)
        await status.edit_text("✅ Отправлено!")
    finally:
        tmp.cleanup()
        try:
            await status.delete()
        except Exception:
            pass


async def handle_youtube(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    status = await update.message.reply_text("✅ Принято в обработку YouTube…")

    tmp = tempfile.TemporaryDirectory()
    try:
        video_in  = os.path.join(tmp.name, "video.mp4")
        video_clean = os.path.join(tmp.name, "video_clean.mp4")
        video_out   = os.path.join(tmp.name, "video_tiktok.mp4")

        ok, err = await download_with_yt_dlp(url, video_in, status)
        if not ok:
            return await status.edit_text(f"❌ Ошибка при скачивании:\n{err}")

        await status.edit_text("🔄 Удаляю метаданные…")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", video_in,
            "-map_metadata", "-1", "-c", "copy", video_clean,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        await status.edit_text("🔄 Конвертирую под TikTok…")
        cmd = [
            "ffmpeg", "-y", "-i", video_clean,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-r", "30", video_out
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        await status.edit_text("✅ Готово! Отправляю видео…")
        with open(video_out, "rb") as f:
            await update.message.reply_document(document=f)
    finally:
        tmp.cleanup()
        try:
            await status.delete()
        except Exception:
            pass


async def handle_tiktok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    status = await update.message.reply_text("✅ Загружаю видео с TikTok…")

    tmp = tempfile.TemporaryDirectory()
    video_out = os.path.join(tmp.name, "tiktok_video.mp4")

    try:
        ok, err = await download_with_yt_dlp(url, video_out, status)
        if not ok:
            return await status.edit_text(f"❌ Ошибка при скачивании:\n{err}")

        await status.edit_text("✅ Отправляю видео…")
        with open(video_out, "rb") as f:
            await update.message.reply_video(video=f, supports_streaming=True, width=1080, height=1920)
    finally:
        tmp.cleanup()
        try:
            await status.delete()
        except Exception:
            pass


async def handle_instagram(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    status = await update.message.reply_text("✅ Загружаю видео с Instagram…")

    tmp = tempfile.TemporaryDirectory()
    video_out = os.path.join(tmp.name, "instagram_video.mp4")

    try:
        ok, err = await download_with_yt_dlp(url, video_out, status)
        if not ok:
            return await status.edit_text(f"❌ Ошибка при скачивании:\n{err}")

        await status.edit_text("✅ Отправляю видео…")
        with open(video_out, "rb") as f:
            await update.message.reply_video(video=f, supports_streaming=True, width=1080, height=1920)
    finally:
        tmp.cleanup()
        try:
            await status.delete()
        except Exception:
            pass


async def handle_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "youtube.com" in url or "youtu.be" in url:
        await handle_youtube(update, ctx)
    elif "tiktok.com" in url:
        await handle_tiktok(update, ctx)
    elif "instagram.com" in url:
        await handle_instagram(update, ctx)
    else:
        await update.message.reply_text("❌ Неподдерживаемая ссылка.")


def main():
    telegram_request = HTTPXRequest(
        connect_timeout=5.0,
        read_timeout=300.0,
        write_timeout=900.0,
        pool_timeout = 60.0
    )
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .request(telegram_request) \
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audio", audio_command))   # <-- moved up

    all_filter = filters.Regex(r"(https?://)?(www\.)?(youtube\.com|youtu\.be|tiktok\.com|instagram\.com)/")
    app.add_handler(MessageHandler(all_filter, handle_all))

    app.run_polling()


if __name__ == "__main__":
    main()
