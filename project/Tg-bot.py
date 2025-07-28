import subprocess
import os

url = "https://youtu.be/O8aQUhfbv6I?si=b74gdfv1qPg7pt-W"

# 1. Скачивание видео в MP4
download_cmd = [
    "yt-dlp",
    "-f", "mp4",
    "-o", "video.%(ext)s",
    url
]
subprocess.run(download_cmd)
print("✅ Видео скачано.")

# 2. Удаление метаданных
subprocess.run([
    "ffmpeg", "-i", "video.mp4",
    "-map_metadata", "-1",
    "-c", "copy", "video_clean.mp4"
])
print("✅ Метаданные удалены.")

# 3. Конвертация под формат TikTok (1080x1920)
subprocess.run([
    "ffmpeg", "-i", "video_clean.mp4",
    "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
    "-c:v", "libx264", "-crf", "23", "-preset", "fast",
    "-c:a", "aac", "-b:a", "128k",
    "-r", "30",
    "video_tiktok.mp4"
])
print("✅ Видео готово для TikTok.")
