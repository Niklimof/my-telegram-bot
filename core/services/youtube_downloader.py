# core/services/youtube_downloader.py
import yt_dlp
import os
import subprocess

class YouTubeDownloader:
    async def download(self, url: str, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)
        
        ydl_opts = {
            'outtmpl': f'{output_dir}/video.mp4',
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            return {
                'path': f'{output_dir}/video.mp4',
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0)
            }
    
    async def extract_audio(self, video_path: str):
        audio_path = video_path.replace('.mp4', '.mp3')
        
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vn', '-acodec', 'libmp3lame',
            '-ab', '192k', '-ar', '44100',
            '-y', audio_path
        ]
        
        subprocess.run(cmd, capture_output=True)
        return audio_path