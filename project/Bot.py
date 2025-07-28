import os
from os import getenv
import yt_dlp
import asyncio
import tempfile
from telegram import Update
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes
)

TOKEN = os.getenv("token")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Пришли ссылку на YouTube, и я верну тебе видео в TikTok‑формате."
    )

async def handle_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    status = await update.message.reply_text("✅ Принято в обработку…")


    tmp = tempfile.TemporaryDirectory()
    try:
        video_in  = os.path.join(tmp.name, "video.mp4")
        video_clean = os.path.join(tmp.name, "video_clean.mp4")
        video_out   = os.path.join(tmp.name, "video_tiktok.mp4")


        try:
            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
                "outtmpl": video_in,
                "merge_output_format": "mp4",
                "quiet": True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            return await status.edit_text(f"❌ Ошибка при скачивании:\n{e}")

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
            await update.message.reply_document(
                document=f
            )
    finally:
        tmp.cleanup()


    await status.delete()

def main():

    telegram_request = HTTPXRequest(
        connect_timeout=5.0,
        read_timeout=300.0,
        write_timeout=900.0
    )
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .request(telegram_request) \
        .build()

    app.add_handler(CommandHandler("start", start))
    yt_filter = filters.Regex(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/")
    app.add_handler(MessageHandler(yt_filter, handle_link))

    app.run_polling()

if __name__ == "__main__":
    main()