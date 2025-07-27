import os
import json
import secrets
import logging
import asyncio
import threading
import time
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import wraps
from typing import Optional, Dict, List, Tuple, Any
import tempfile
import shutil
import hashlib
import mimetypes

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory, Response
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip, concatenate_videoclips
from moviepy.video.fx import resize, crop
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from redis import Redis
import cv2

from instagrapi import Client
from instagrapi.types import (
    StoryMention, StoryLocation, StoryLink, StoryHashtag, 
    Usertag, Location, StoryPoll, StorySticker
)
from instagrapi.exceptions import LoginRequired, ClientError, ChallengeRequired

# Konfigürasyon
class Config:
    # Flask ayarları
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    UPLOAD_FOLDER = Path('uploads')
    TEMP_FOLDER = Path('temp')
    SESSION_FOLDER = Path('sessions')
    STATIC_FOLDER = Path('static')
    
    # Dosya boyutu limitleri (4K içerik için artırıldı)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for large files
    
    # Desteklenen formatlar
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'heic', 'heif', 'raw', 'tiff', 'bmp'}
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'}
    
    # Instagram özel ayarları
    STORY_DURATION_LIMIT = 15  # saniye
    REEL_MIN_DURATION = 5  # saniye
    REEL_MAX_DURATION = 90  # saniye
    STORY_WIDTH = 1080
    STORY_HEIGHT = 1920
    REEL_WIDTH = 1080
    REEL_HEIGHT = 1920
    POST_MAX_WIDTH = 1080
    POST_MAX_HEIGHT = 1350
    
    # 4K video işleme ayarları
    VIDEO_BITRATE = "10M"  # 10 Mbps for high quality
    VIDEO_PRESET = "slow"  # Better compression
    VIDEO_CRF = 23  # Quality factor (lower = better quality)
    
    # Performans ayarları
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CACHE_TTL = 3600  # 1 saat
    
    # Güvenlik ayarları
    SESSION_LIFETIME = 3600 * 24  # 24 saat
    MAX_LOGIN_ATTEMPTS = 5
    RATE_LIMIT_UPLOADS = 15  # saat başına maksimum yükleme (daha güvenli)
    DAILY_UPLOAD_LIMIT = 50  # günlük maksimum yükleme
    
    # İnsan benzeri davranış ayarları
    MIN_UPLOAD_INTERVAL = 180  # upload'lar arası minimum 3 dakika
    MAX_UPLOAD_INTERVAL = 900  # upload'lar arası maksimum 15 dakika
    HUMAN_ACTIVITY_CHANCE = 0.7  # %70 ihtimalle insan benzeri aktivite
    SESSION_REFRESH_INTERVAL = [7200, 14400]  # 2-4 saat arası session yenileme
    
    # API anahtarları (isteğe bağlı)
    UNSPLASH_ACCESS_KEY = os.environ.get('UNSPLASH_ACCESS_KEY')
    PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

# Flask uygulaması
app = Flask(__name__)
app.config.from_object(Config)
CORS(app, origins=['http://localhost:*'])

# Klasörleri oluştur
for folder in [Config.UPLOAD_FOLDER, Config.TEMP_FOLDER, Config.SESSION_FOLDER, Config.STATIC_FOLDER]:
    folder.mkdir(exist_ok=True)

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instagram_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Redis bağlantısı (cache için)
try:
    redis_client = Redis.from_url(Config.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Redis connection established")
except:
    redis_client = None
    logger.warning("Redis not available, using in-memory cache")

# In-memory cache (Redis yoksa)
memory_cache = {}

# Instagram Client yönetimi
class InstagramManager:
    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.session_file = Config.SESSION_FOLDER / 'instagram_sessions.json'
        self.upload_queue = []
        self.processing = False
        self.last_activity = {}
        self.session_refresh_times = {}
        self.load_sessions()
        
    def get_random_user_agent(self):
        """Rastgele user agent döndür"""
        user_agents = [
            "Instagram 269.0.0.18.75 Android (30/11; 450dpi; 1080x2137; samsung; SM-G973F; beyond1; exynos9820; en_US; 436384443)",
            "Instagram 271.0.0.18.86 Android (29/10; 420dpi; 1080x2280; OnePlus; GM1913; OnePlus7Pro; qcom; en_US; 439308937)",
            "Instagram 273.0.0.18.95 Android (31/12; 440dpi; 1080x2400; Google; Pixel 5; redfin; redfin; en_US; 441258931)",
            "Instagram 275.0.0.18.104 Android (28/9; 480dpi; 1440x2960; samsung; SM-G965F; star2qltexm; samsungexynos9810; en_US; 443198937)",
            "Instagram 277.0.0.18.116 Android (32/13; 560dpi; 1440x3200; samsung; SM-G998B; o1s; exynos2100; en_US; 445123456)"
        ]
        return random.choice(user_agents)
        
    def should_perform_human_activity(self, username: str) -> bool:
        """İnsan benzeri aktivite yapılmalı mı kontrol et"""
        last_activity = self.last_activity.get(username, 0)
        # Son aktiviteden 30-60 dakika geçtiyse aktivite yap
        return (time.time() - last_activity) > random.randint(1800, 3600)
        
    def perform_human_activity(self, client: Client, username: str):
        """İnsan benzeri aktiviteler gerçekleştir"""
        try:
            activities = []
            
            # %60 ihtimalle feed kontrol et
            if random.random() < 0.6:
                activities.append("feed_check")
                
            # %30 ihtimalle story kontrol et  
            if random.random() < 0.3:
                activities.append("story_check")
                
            # %20 ihtimalle profil güncelle
            if random.random() < 0.2:
                activities.append("profile_check")
                
            for activity in activities:
                try:
                    if activity == "feed_check":
                        client.get_timeline_feed()
                        logger.info(f"Human activity: feed check for {username}")
                        
                    elif activity == "story_check":
                        client.get_reels_tray_feed()
                        logger.info(f"Human activity: story check for {username}")
                        
                    elif activity == "profile_check":
                        client.account_info()
                        logger.info(f"Human activity: profile check for {username}")
                        
                    # Aktiviteler arası minimal bekleme
                    time.sleep(random.randint(1, 2))
                    
                except Exception as e:
                    logger.warning(f"Human activity error for {username}: {e}")
                    
            self.last_activity[username] = time.time()
            
        except Exception as e:
            logger.error(f"Error performing human activity for {username}: {e}")
            
    def should_refresh_session(self, username: str) -> bool:
        """Session yenilensin mi kontrol et"""
        last_refresh = self.session_refresh_times.get(username, 0)
        # 2-4 saat arası rastgele session yenileme
        refresh_interval = random.randint(7200, 14400)
        return (time.time() - last_refresh) > refresh_interval
    
    def load_sessions(self):
        """Kaydedilmiş oturumları yükle"""
        if self.session_file.exists():
            try:
                with open(self.session_file, 'r') as f:
                    sessions = json.load(f)
                    for username, settings in sessions.items():
                        try:
                            cl = Client()
                            cl.set_settings(settings)
                            # Proxy ayarları (opsiyonel)
                            if os.environ.get('PROXY_URL'):
                                cl.set_proxy(os.environ.get('PROXY_URL'))
                            self.clients[username] = cl
                        except Exception as e:
                            logger.error(f"Error loading session for {username}: {e}")
                logger.info(f"Loaded {len(self.clients)} saved sessions")
            except Exception as e:
                logger.error(f"Error loading sessions: {e}")
    
    def save_sessions(self):
        """Oturumları kaydet"""
        try:
            sessions = {}
            for username, client in self.clients.items():
                sessions[username] = client.get_settings()
            with open(self.session_file, 'w') as f:
                json.dump(sessions, f)
            logger.info("Sessions saved successfully")
        except Exception as e:
            logger.error(f"Error saving sessions: {e}")
    
    def login(self, username: str, password: str, verification_code: Optional[str] = None) -> Tuple[bool, str, Optional[Dict]]:
        """Instagram'a giriş yap"""
        try:
            cl = Client()
            # Minimal delay'ler (sadece gerçekten gerekli olanlar)
            cl.delay_range = [1, 3]  # 1-3 saniye arası minimal gecikme
            
            # Rastgele user agent ayarla
            cl.set_user_agent(self.get_random_user_agent())
            
            # Proxy kullan (opsiyonel)
            if os.environ.get('PROXY_URL'):
                cl.set_proxy(os.environ.get('PROXY_URL'))
            
            # Önce kayıtlı oturumu kontrol et
            if username in self.clients and not verification_code:
                cl = self.clients[username]
                try:
                    # Oturum geçerliliğini kontrol et
                    user_info = cl.user_info(cl.user_id)
                    logger.info(f"Using existing session for {username}")
                    return True, "Mevcut oturum kullanıldı", {
                        "user": {
                            "username": user_info.username,
                            "full_name": user_info.full_name,
                            "profile_pic_url": str(user_info.profile_pic_url),
                            "is_verified": user_info.is_verified,
                            "is_business": user_info.is_business,
                            "media_count": user_info.media_count,
                            "follower_count": user_info.follower_count,
                            "following_count": user_info.following_count
                        }
                    }
                except Exception as e:
                    logger.info(f"Existing session expired for {username}: {str(e)}")
                    # Remove expired session
                    del self.clients[username]
            
            # Yeni giriş yap
            try:
                if verification_code:
                    # 2FA ile giriş
                    cl.login(username, password, verification_code=verification_code)
                else:
                    # Normal giriş
                    cl.login(username, password)
            except ChallengeRequired as e:
                # 2FA gerekli
                self.clients[username] = cl
                return False, "2FA doğrulaması gerekli", {"requires_2fa": True}
            except Exception as e:
                if "Two-factor authentication required" in str(e):
                    # 2FA gerekli
                    self.clients[username] = cl
                    return False, "2FA doğrulaması gerekli", {"requires_2fa": True}
                else:
                    raise e
            
            # Başarılı giriş
            self.clients[username] = cl
            
            # Session refresh zamanını kaydet
            self.session_refresh_times[username] = time.time()
            
            # Giriş sonrası insan benzeri aktivite
            if random.random() < Config.HUMAN_ACTIVITY_CHANCE:
                threading.Thread(
                    target=self.perform_human_activity, 
                    args=(cl, username)
                ).start()
            
            self.save_sessions()
            
            # Kullanıcı bilgilerini al
            try:
                user_info = cl.account_info()
                logger.info(f"Login successful for {username}")
                return True, "Giriş başarılı", {
                    "user": {
                        "username": user_info.username,
                        "full_name": user_info.full_name,
                        "profile_pic_url": str(user_info.profile_pic_url),
                        "is_verified": user_info.is_verified,
                        "is_business": user_info.is_business,
                        "media_count": user_info.media_count,
                        "follower_count": user_info.follower_count,
                        "following_count": user_info.following_count
                    }
                }
            except Exception as e:
                logger.warning(f"Could not get account info for {username}: {str(e)}")
                logger.info(f"Login successful for {username} (without account details)")
                return True, "Giriş başarılı", {
                    "user": {
                        "username": username,
                        "full_name": "",
                        "profile_pic_url": "",
                        "is_verified": False,
                        "is_business": False,
                        "media_count": 0,
                        "follower_count": 0,
                        "following_count": 0
                    }
                }
            
        except Exception as e:
            logger.error(f"Login error for {username}: {str(e)}")
            return False, f"Giriş hatası: {str(e)}", None
    
    def get_client(self, username: str) -> Optional[Client]:
        """Aktif client'ı getir"""
        return self.clients.get(username)
    
    def logout(self, username: str):
        """Çıkış yap"""
        if username in self.clients:
            try:
                self.clients[username].logout()
            except:
                pass
            del self.clients[username]
            self.save_sessions()
    
    def get_user_stats(self, username: str) -> Optional[Dict]:
        """Kullanıcı istatistiklerini getir"""
        client = self.get_client(username)
        if not client:
            return None
        
        try:
            user_info = client.user_info(client.user_id)
            insights = client.insights_account()
            
            return {
                "followers": user_info.follower_count,
                "following": user_info.following_count,
                "posts": user_info.media_count,
                "reach": insights.get("reach", {}).get("value", 0) if insights else 0,
                "impressions": insights.get("impressions", {}).get("value", 0) if insights else 0
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None

# Global Instagram Manager
ig_manager = InstagramManager()

# Cache yönetimi
class CacheManager:
    @staticmethod
    def get(key: str) -> Optional[Any]:
        if redis_client:
            value = redis_client.get(key)
            return json.loads(value) if value else None
        return memory_cache.get(key)
    
    @staticmethod
    def set(key: str, value: Any, ttl: int = Config.CACHE_TTL):
        if redis_client:
            redis_client.setex(key, ttl, json.dumps(value))
        else:
            memory_cache[key] = value
    
    @staticmethod
    def delete(key: str):
        if redis_client:
            redis_client.delete(key)
        else:
            memory_cache.pop(key, None)

# Medya işleme sınıfı
class MediaProcessor:
    """Gelişmiş medya dosyalarını işleme sınıfı"""
    
    @staticmethod
    def get_video_info(video_path: Path) -> Dict:
        """Video bilgilerini al"""
        try:
            clip = VideoFileClip(str(video_path))
            info = {
                "duration": clip.duration,
                "fps": clip.fps,
                "width": clip.w,
                "height": clip.h,
                "size": video_path.stat().st_size,
                "bitrate": clip.reader.bitrate if hasattr(clip.reader, 'bitrate') else None
            }
            clip.close()
            return info
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return {}
    
    @staticmethod
    def process_4k_image_for_instagram(image_path: Path, output_path: Path, 
                                     target_type: str = "story") -> Path:
        """4K görüntüyü Instagram için optimize et"""
        try:
            img = Image.open(image_path)
            
            # EXIF verilerini koru ve yönlendirmeyi düzelt
            exif = img.info.get('exif', b'')
            if hasattr(img, '_getexif') and img._getexif():
                exif_dict = img._getexif()
                if exif_dict and 274 in exif_dict:  # Orientation tag
                    orientation = exif_dict[274]
                    rotations = {3: 180, 6: 270, 8: 90}
                    if orientation in rotations:
                        img = img.rotate(rotations[orientation], expand=True)
            
            # Hedef boyutları belirle
            if target_type == "story" or target_type == "reel":
                target_width, target_height = Config.STORY_WIDTH, Config.STORY_HEIGHT
            else:  # post
                target_width = Config.POST_MAX_WIDTH
                target_height = Config.POST_MAX_HEIGHT
            
            # Akıllı kırpma ve yeniden boyutlandırma
            img_ratio = img.width / img.height
            target_ratio = target_width / target_height
            
            if target_type in ["story", "reel"]:
                # Story/Reel için merkezi kırpma
                if img_ratio > target_ratio:
                    # Görüntü çok geniş
                    new_width = int(img.height * target_ratio)
                    left = (img.width - new_width) // 2
                    img = img.crop((left, 0, left + new_width, img.height))
                else:
                    # Görüntü çok uzun
                    new_height = int(img.width / target_ratio)
                    top = (img.height - new_height) // 2
                    img = img.crop((0, top, img.width, top + new_height))
            else:
                # Post için akıllı boyutlandırma (kırpma yapmadan)
                if img.width > target_width or img.height > target_height:
                    img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Yeniden boyutlandır
            if target_type in ["story", "reel"]:
                img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Renk profili optimizasyonu
            if img.mode not in ['RGB', 'RGBA']:
                img = img.convert('RGB')
            
            # Keskinlik artırma (4K'dan düşürüldüğü için)
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.2)
            
            # Kaydet
            img.save(output_path, 'JPEG', quality=95, optimize=True, progressive=True)
            
            return output_path
        except Exception as e:
            logger.error(f"Image processing error: {e}")
            raise
    
    @staticmethod
    def process_4k_video_for_instagram(video_path: Path, output_path: Path, 
                                     target_type: str = "story", 
                                     progress_callback: Optional[callable] = None) -> Path:
        """4K videoyu Instagram için optimize et"""
        try:
            # FFmpeg komutunu kullan (daha hızlı ve kaliteli)
            import subprocess
            
            # Video bilgilerini al
            info = MediaProcessor.get_video_info(video_path)
            
            # Hedef parametreleri
            if target_type == "story":
                max_duration = Config.STORY_DURATION_LIMIT
                target_width, target_height = Config.STORY_WIDTH, Config.STORY_HEIGHT
            else:  # reel
                max_duration = Config.REEL_MAX_DURATION
                target_width, target_height = Config.REEL_WIDTH, Config.REEL_HEIGHT
            
            # Video aspect ratio tespiti
            original_width = info.get('width', target_width)
            original_height = info.get('height', target_height)
            original_ratio = original_width / original_height
            
            # Hedef aspect ratio belirleme
            if original_ratio > 1.0:  # Yatay video
                final_width, final_height = 1920, 1080  # 16:9
            else:  # Dikey video
                final_width, final_height = 1080, 1920  # 9:16
            
            # FFmpeg komutu oluştur - stretch to fit (siyah kenar yok)
            cmd = [
                'ffmpeg', '-i', str(video_path),
                '-vf', f'scale={final_width}:{final_height}',
                '-c:v', 'libx264',
                '-preset', Config.VIDEO_PRESET,
                '-crf', str(Config.VIDEO_CRF),
                '-b:v', Config.VIDEO_BITRATE,
                '-c:a', 'aac',
                '-b:a', '256k',
                '-movflags', '+faststart',
                '-t', str(max_duration),
                '-y',
                str(output_path)
            ]
            
            # İlerleme takibi
            if progress_callback:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                
                for line in process.stderr:
                    if "time=" in line:
                        # İlerleme yüzdesini hesapla
                        time_str = line.split("time=")[1].split()[0]
                        try:
                            h, m, s = time_str.split(':')
                            current_time = int(h) * 3600 + int(m) * 60 + float(s)
                            progress = min(100, (current_time / min(info['duration'], max_duration)) * 100)
                            progress_callback(progress)
                        except:
                            pass
                
                process.wait()
                if process.returncode != 0:
                    raise Exception("FFmpeg processing failed")
            else:
                subprocess.run(cmd, check=True)
            
            return output_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e}")
            # Fallback to moviepy
            return MediaProcessor._process_video_with_moviepy(video_path, output_path, target_type)
        except Exception as e:
            logger.error(f"Video processing error: {e}")
            raise
    
    @staticmethod
    def _process_video_with_moviepy(video_path: Path, output_path: Path, 
                                   target_type: str = "story") -> Path:
        """MoviePy ile video işleme (yedek yöntem)"""
        try:
            clip = VideoFileClip(str(video_path))
            
            # Parametreler
            if target_type == "story":
                max_duration = Config.STORY_DURATION_LIMIT
                target_width, target_height = Config.STORY_WIDTH, Config.STORY_HEIGHT
            else:
                max_duration = Config.REEL_MAX_DURATION
                target_width, target_height = Config.REEL_WIDTH, Config.REEL_HEIGHT
            
            # Süre kontrolü
            if clip.duration > max_duration:
                clip = clip.subclip(0, max_duration)
            
            # Video aspect ratio tespiti ve hedef boyut belirleme
            original_ratio = clip.w / clip.h
            
            if original_ratio > 1.0:  # Yatay video
                final_width, final_height = 1920, 1080  # 16:9
            else:  # Dikey video
                final_width, final_height = 1080, 1920  # 9:16
            
            # Stretch to fit - siyah kenar olmadan
            clip = clip.resize((final_width, final_height))
            
            # Kaydet
            clip.write_videofile(
                str(output_path),
                codec='libx264',
                audio_codec='aac',
                bitrate=Config.VIDEO_BITRATE,
                fps=30,
                preset=Config.VIDEO_PRESET,
                logger=None
            )
            
            clip.close()
            return output_path
        except Exception as e:
            logger.error(f"MoviePy processing error: {e}")
            raise
    
    @staticmethod
    def create_video_from_images(image_paths: List[Path], output_path: Path, 
                               duration_per_image: int = 3,
                               transition: str = "fade") -> Path:
        """Birden fazla resimden video oluştur"""
        try:
            clips = []
            
            for i, image_path in enumerate(image_paths):
                # Resmi optimize et
                temp_image = output_path.parent / f"temp_{i}_{image_path.name}"
                MediaProcessor.process_4k_image_for_instagram(
                    image_path, temp_image, "story"
                )
                
                # Klip oluştur
                clip = ImageClip(str(temp_image), duration=duration_per_image)
                
                # Geçiş efekti ekle
                if i > 0 and transition == "fade":
                    clip = clip.crossfadein(0.5)
                
                clips.append(clip)
                temp_image.unlink()
            
            # Klipleri birleştir
            final_clip = concatenate_videoclips(clips, method="compose")
            
            # Müzik ekle (opsiyonel)
            # if audio_path:
            #     audio = AudioFileClip(str(audio_path))
            #     final_clip = final_clip.set_audio(audio)
            
            # Kaydet
            final_clip.write_videofile(
                str(output_path),
                fps=30,
                codec='libx264',
                audio_codec='aac',
                logger=None
            )
            
            final_clip.close()
            return output_path
        except Exception as e:
            logger.error(f"Image slideshow creation error: {e}")
            raise
    
    @staticmethod
    def add_watermark(media_path: Path, watermark_text: str, 
                     position: str = "bottom-right") -> Path:
        """Medyaya watermark ekle"""
        try:
            output_path = media_path.parent / f"watermarked_{media_path.name}"
            
            if media_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                # Resime watermark ekle
                img = Image.open(media_path)
                draw = ImageDraw.Draw(img)
                
                # Font boyutu
                font_size = int(img.width * 0.03)
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
                
                # Metin boyutu
                bbox = draw.textbbox((0, 0), watermark_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Pozisyon
                margin = 20
                if position == "bottom-right":
                    x = img.width - text_width - margin
                    y = img.height - text_height - margin
                elif position == "bottom-left":
                    x = margin
                    y = img.height - text_height - margin
                elif position == "top-right":
                    x = img.width - text_width - margin
                    y = margin
                else:  # top-left
                    x = margin
                    y = margin
                
                # Gölge efekti
                shadow_offset = 2
                draw.text((x + shadow_offset, y + shadow_offset), watermark_text, 
                         font=font, fill=(0, 0, 0, 128))
                draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, 200))
                
                img.save(output_path, quality=95)
            else:
                # Videoya watermark ekle
                clip = VideoFileClip(str(media_path))
                
                # Metin klibi oluştur
                txt_clip = TextClip(
                    watermark_text,
                    fontsize=int(clip.w * 0.03),
                    color='white',
                    font='Arial',
                    stroke_color='black',
                    stroke_width=1
                )
                
                # Pozisyon
                if position == "bottom-right":
                    txt_clip = txt_clip.set_position(('right', 'bottom')).set_margin(20)
                elif position == "bottom-left":
                    txt_clip = txt_clip.set_position(('left', 'bottom')).set_margin(20)
                elif position == "top-right":
                    txt_clip = txt_clip.set_position(('right', 'top')).set_margin(20)
                else:
                    txt_clip = txt_clip.set_position(('left', 'top')).set_margin(20)
                
                txt_clip = txt_clip.set_duration(clip.duration)
                
                # Birleştir
                final = CompositeVideoClip([clip, txt_clip])
                final.write_videofile(str(output_path), codec='libx264', logger=None)
                
                clip.close()
                final.close()
            
            return output_path
        except Exception as e:
            logger.error(f"Watermark error: {e}")
            return media_path

# Yardımcı fonksiyonlar
def login_required(f):
    """Login kontrolü için decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            if request.is_json:
                return jsonify({'success': False, 'message': 'Giriş gerekli'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename: str) -> bool:
    """Dosya uzantısı kontrolü"""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in Config.ALLOWED_IMAGE_EXTENSIONS or ext in Config.ALLOWED_VIDEO_EXTENSIONS

def get_file_type(filename: str) -> str:
    """Dosya tipini belirle"""
    if not filename or '.' not in filename:
        return 'unknown'
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in Config.ALLOWED_IMAGE_EXTENSIONS:
        return 'image'
    elif ext in Config.ALLOWED_VIDEO_EXTENSIONS:
        return 'video'
    return 'unknown'

def generate_unique_filename(original_filename: str) -> str:
    """Benzersiz dosya adı oluştur"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_str = secrets.token_hex(4)
    ext = original_filename.rsplit('.', 1)[1].lower()
    return f"{timestamp}_{random_str}.{ext}"

# Flask route'ları
@app.route('/')
def index():
    """Ana sayfa"""
    if 'username' in session:
        return render_template('dashboard.html', username=session['username'])
    return render_template('index.html')

@app.route('/login', methods=['GET'])
def login_page():
    """Giriş sayfasını gösterir"""
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    """Giriş işlemini API üzerinden yönetir"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    verification_code = data.get('verification_code', '').strip()
    
    if not username or not password:
        return jsonify({
            'success': False, 
            'message': 'Kullanıcı adı ve şifre gerekli'
        }), 400
    
    # Rate limiting kontrolü
    login_key = f"login_attempts:{request.remote_addr}"
    attempts = CacheManager.get(login_key) or 0
    
    if attempts >= Config.MAX_LOGIN_ATTEMPTS:
        return jsonify({
            'success': False,
            'message': 'Çok fazla başarısız giriş denemesi. Lütfen daha sonra tekrar deneyin.'
        }), 429
    
    # Giriş yap
    success, message, data = ig_manager.login(username, password, verification_code)
    
    if success:
        # Başarılı giriş
        session['username'] = username
        session['user_data'] = data.get('user') if data else None
        session.permanent = True
        CacheManager.delete(login_key)
        
        return jsonify({
            'success': True,
            'message': message,
            'redirect': url_for('dashboard'),
            'user': data.get('user') if data else None
        })
    else:
        # Başarısız giriş
        CacheManager.set(login_key, attempts + 1, 3600)
        
        return jsonify({
            'success': False,
            'message': message,
            'requires_2fa': data.get('requires_2fa', False) if data else False
        }), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    """Çıkış yap API"""
    username = session.get('username')
    if username:
        ig_manager.logout(username)
    session.clear()
    return jsonify({'success': True, 'redirect': url_for('login_page')})

@app.route('/dashboard')
@login_required
def dashboard():
    """Ana panel"""
    username = session.get('username')
    user_data = session.get('user_data')
    
    # İstatistikleri al
    stats = ig_manager.get_user_stats(username)
    
    return render_template('dashboard.html', 
                     username=username,
                     user_info=user_data, # Değişiklik burada
                     stats=stats)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Yükleme sayfası"""
    if request.method == 'GET':
        return render_template('upload.html')
    
    # Dosya yükleme işlemi
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya seçilmedi'}), 400
    
    files = request.files.getlist('file')
    upload_type = request.form.get('type', 'post')  # post, story, reel
    caption = request.form.get('caption', '')
    
    # Validasyon
    if not files or not any(f.filename for f in files):
        return jsonify({'success': False, 'message': 'Geçerli dosya seçilmedi'}), 400
    
    # Rate limiting - hem saatlik hem günlük kontrol
    hourly_rate_key = f"upload_rate_hourly:{session['username']}"
    daily_rate_key = f"upload_rate_daily:{session['username']}"
    
    hourly_uploads = CacheManager.get(hourly_rate_key) or 0
    daily_uploads = CacheManager.get(daily_rate_key) or 0
    
    if hourly_uploads >= Config.RATE_LIMIT_UPLOADS:
        return jsonify({
            'success': False,
            'message': 'Saatlik yükleme limitine ulaştınız (15 dosya/saat)'
        }), 429
        
    if daily_uploads >= Config.DAILY_UPLOAD_LIMIT:
        return jsonify({
            'success': False,
            'message': 'Günlük yükleme limitine ulaştınız (50 dosya/gün)'
        }), 429
        
    # Son upload zamanı kontrolü
    last_upload_key = f"last_upload:{session['username']}"
    last_upload_time = CacheManager.get(last_upload_key) or 0
    time_since_last = time.time() - last_upload_time
    
    if time_since_last < Config.MIN_UPLOAD_INTERVAL:
        wait_time = Config.MIN_UPLOAD_INTERVAL - time_since_last
        return jsonify({
            'success': False,
            'message': f'Bir sonraki yükleme için {int(wait_time)} saniye bekleyin'
        }), 429
    
    uploaded_files = []
    errors = []
    
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            try:
                # Benzersiz dosya adı
                filename = generate_unique_filename(file.filename)
                file_path = Config.UPLOAD_FOLDER / filename
                
                # Dosyayı kaydet
                file.save(file_path)
                
                # Dosya tipini kontrol et
                file_type = get_file_type(filename)
                
                # İşleme için kuyruğa ekle
                task_id = secrets.token_hex(16)
                task = {
                    'id': task_id,
                    'username': session['username'],
                    'file_path': str(file_path),
                    'file_type': file_type,
                    'upload_type': upload_type,
                    'caption': caption,
                    'status': 'pending',
                    'created_at': datetime.now().isoformat()
                }
                
                # Kuyruğa ekle
                ig_manager.upload_queue.append(task)
                
                # Cache'e kaydet
                CacheManager.set(f"upload_task:{task_id}", task)
                
                uploaded_files.append({
                    'filename': file.filename,
                    'task_id': task_id
                })
                
            except Exception as e:
                logger.error(f"Upload error: {e}")
                errors.append({
                    'filename': file.filename,
                    'error': str(e)
                })
    
    # Rate limit güncelle
    if uploaded_files:
        CacheManager.set(hourly_rate_key, hourly_uploads + len(uploaded_files), 3600)  # 1 saat
        CacheManager.set(daily_rate_key, daily_uploads + len(uploaded_files), 86400)  # 24 saat
        CacheManager.set(last_upload_key, time.time(), 3600)  # Son upload zamanı
    
    # İşleme başlat
    if uploaded_files and not ig_manager.processing:
        threading.Thread(target=process_upload_queue).start()
    
    return jsonify({
        'success': len(uploaded_files) > 0,
        'uploaded': uploaded_files,
        'errors': errors,
        'message': f"{len(uploaded_files)} dosya yüklendi, {len(errors)} hata"
    })

@app.route('/upload/status/<task_id>')
@login_required
def upload_status(task_id):
    """Yükleme durumunu kontrol et"""
    task = CacheManager.get(f"upload_task:{task_id}")
    if not task:
        return jsonify({'success': False, 'message': 'Task bulunamadı'}), 404
    
    return jsonify({
        'success': True,
        'task': task
    })

@app.route('/api/stats')
@login_required
def api_stats():
    """İstatistikleri getir"""
    username = session.get('username')
    stats = ig_manager.get_user_stats(username)
    
    if stats:
        return jsonify({
            'success': True,
            'stats': stats
        })
    else:
        return jsonify({
            'success': False,
            'message': 'İstatistikler alınamadı'
        }), 500

@app.route('/api/recent-posts')
@login_required
def api_recent_posts():
    """Son paylaşımları getir"""
    username = session.get('username')
    client = ig_manager.get_client(username)
    
    if not client:
        return jsonify({'success': False, 'message': 'Client bulunamadı'}), 500
    
    try:
        # Son 9 gönderiyi al
        medias = client.user_medias(client.user_id, 9)
        
        posts = []
        for media in medias:
            posts.append({
                'id': media.pk,
                'type': media.media_type,
                'thumbnail': str(media.thumbnail_url) if media.thumbnail_url else None,
                'caption': media.caption_text[:100] + '...' if media.caption_text and len(media.caption_text) > 100 else media.caption_text,
                'likes': media.like_count,
                'comments': media.comment_count,
                'date': media.taken_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'posts': posts
        })
    except Exception as e:
        logger.error(f"Error fetching recent posts: {e}")
        return jsonify({
            'success': False,
            'message': 'Gönderiler alınamadı'
        }), 500

@app.route('/static/<path:path>')
def send_static(path):
    """Statik dosyaları sun"""
    return send_from_directory('static', path)

@app.route('/upload_page') # Eski hatalı referanslar için geçici yönlendirme
def upload_page_redirect():
    return redirect(url_for('upload'))

@app.route('/queue')
@login_required
def queue_page():
    """Yükleme kuyruğu sayfasını gösterir"""
    cleanup_completed_tasks()
    # Kuyruktaki görevleri Cache'den veya ig_manager'dan alabilirsiniz
    # Şimdilik basit bir HTML render edelim
    tasks = [CacheManager.get(f"upload_task:{task['id']}") for task in ig_manager.upload_queue]
    return render_template('queue.html', tasks=tasks)

@app.route('/api/queue/count')
@login_required
def api_queue_count():
    """Kuyruktaki eleman sayısını döndürür"""
    cleanup_completed_tasks()
    return jsonify({'count': len(ig_manager.upload_queue)})

@app.route('/api/queue/tasks')
@login_required
def api_queue_tasks():
    """Kuyruktaki görevlerin detaylarını döndürür"""
    try:
        # Önce tamamlanan task'ları temizle
        cleanup_completed_tasks()
        
        tasks = []
        for task in ig_manager.upload_queue:
            # Cache'den güncel task bilgilerini al
            task_data = CacheManager.get(f"upload_task:{task['id']}")
            if task_data:
                # Dosya adından gereksiz kısmı çıkar
                filename = Path(task_data['file_path']).name
                # Prefix'i temizle
                if filename.startswith(task_data['created_at'][:8]):
                    original_filename = filename[20:]  # timestamp_uuid prefix kaldır
                else:
                    original_filename = filename
                
                tasks.append({
                    'id': task_data['id'],
                    'filename': original_filename,
                    'type': task_data['upload_type'],
                    'status': task_data['status'],
                    'created_at': task_data['created_at'],
                    'error': task_data.get('error'),
                    'media_id': task_data.get('media_id')
                })
        
        return jsonify({'success': True, 'tasks': tasks})
    except Exception as e:
        logger.error(f"Error getting queue tasks: {e}")
        return jsonify({'success': False, 'message': 'Queue verisi alınamadı'}), 500

@app.route('/api/user/stats')
@login_required
def api_user_stats():
    """Kullanıcı istatistiklerini döndürür"""
    try:
        username = session.get('username')
        stats = ig_manager.get_user_stats(username)
        
        if stats:
            # Upload istatistikleri ekle (basit hesaplama)
            today_count = len([task for task in ig_manager.upload_queue 
                             if task.get('created_at', '').startswith(datetime.now().strftime('%Y-%m-%d'))])
            
            # Haftalık upload sayısı için yaklaşık hesap
            week_ago = datetime.now() - timedelta(days=7)
            weekly_count = len([task for task in ig_manager.upload_queue 
                              if datetime.fromisoformat(task.get('created_at', '1970-01-01')) > week_ago])
            
            return jsonify({
                'success': True,
                'stats': {
                    'followers': stats.get('followers', 0),
                    'following': stats.get('following', 0),
                    'posts': stats.get('posts', 0),
                    'todayUploads': today_count,
                    'weeklyUploads': weekly_count,
                    'storageUsed': '2.4 GB'  # Bu hesaplanabilir
                }
            })
        else:
            return jsonify({
                'success': False, 
                'message': 'İstatistikler alınamadı'
            }), 500
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return jsonify({'success': False, 'message': 'Sunucu hatası'}), 500

@app.route('/api/user/refresh', methods=['POST'])
@login_required
def api_user_refresh():
    """Kullanıcı bilgilerini yeniler"""
    username = session.get('username')
    client = ig_manager.get_client(username)
    if client:
        try:
            user_info = client.account_info()
            session['user_data'] = {
                "username": user_info.username,
                "full_name": user_info.full_name,
                "profile_pic_url": str(user_info.profile_pic_url),
                "is_verified": user_info.is_verified,
                "is_business": user_info.is_business
            }
            return jsonify({'success': True, 'message': 'Kullanıcı bilgileri güncellendi'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'Client bulunamadı'}), 500

@app.route('/api/system/status')
@login_required
def api_system_status():
    """Sistem durumu"""
    try:
        return jsonify({
            'success': True,
            'status': {
                'queue_processing': ig_manager.processing,
                'queue_length': len(ig_manager.upload_queue),
                'redis_available': redis_client is not None,
                'logged_in_users': len(ig_manager.clients),
                'upload_delay_range': '5-30 seconds (optimized for speed)'
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/api/search/user/<query>')
@login_required
def api_search_user(query):
    """Kullanıcı arama"""
    client = ig_manager.get_client(session['username'])
    if not client:
        return jsonify({'success': False, 'users': []})
    users = client.user_search(query)
    results = [{'username': u.username, 'full_name': u.full_name, 'profile_pic_url': str(u.profile_pic_url), 'is_verified': u.is_verified} for u in users[:10]]
    return jsonify({'success': True, 'users': results})

@app.route('/api/search/location/<query>')
@login_required
def api_search_location(query):
    """Konum arama"""
    client = ig_manager.get_client(session['username'])
    if not client:
        return jsonify({'success': False, 'locations': []})
    locations = client.location_search(query)
    results = [{'pk': l.pk, 'name': l.name, 'address': l.address} for l in locations[:10]]
    return jsonify({'success': True, 'locations': results})

def get_optimal_upload_time():
    """En uygun upload zamanını hesapla (çok daha kısa süreler)"""
    current_time = datetime.now().time()
    current_hour = current_time.hour
    
    # Prime time saatlerinde (9-17 arası) minimal bekleme
    if 9 <= current_hour <= 17:
        return random.randint(10, 30)  # 10-30 saniye
    else:
        return random.randint(5, 20)  # 5-20 saniye
        
# Arkaplan işlemleri
def process_upload_queue():
    """Yükleme kuyruğunu işle - İnsan benzeri timing ile"""
    ig_manager.processing = True
    
    while ig_manager.upload_queue:
        # İlk pending task'ı bul
        task_index = None
        for i, task in enumerate(ig_manager.upload_queue):
            if task['status'] == 'pending':
                task_index = i
                break
        
        if task_index is None:
            # Tüm task'lar işlendi, döngüden çık
            break
            
        task = ig_manager.upload_queue[task_index]
        
        try:
            # Task'ı güncelle
            task['status'] = 'processing'
            CacheManager.set(f"upload_task:{task['id']}", task)
            
            # Client'ı al
            client = ig_manager.get_client(task['username'])
            if not client:
                raise Exception("Instagram client bulunamadı")
                
            # İnsan benzeri aktivite kontrolü
            if ig_manager.should_perform_human_activity(task['username']):
                logger.info(f"Performing human activity before upload for {task['username']}")
                ig_manager.perform_human_activity(client, task['username'])
                # Aktivite sonrası minimal bekleme
                time.sleep(random.randint(5, 10))
                
            # Session yenileme kontrolü
            if ig_manager.should_refresh_session(task['username']):
                logger.info(f"Refreshing session for {task['username']}")
                try:
                    client.account_info()  # Session kontrolü
                    ig_manager.session_refresh_times[task['username']] = time.time()
                except Exception as e:
                    logger.warning(f"Session refresh needed for {task['username']}: {e}")
            
            # Dosya yolu
            file_path = Path(task['file_path'])
            if not file_path.exists():
                raise Exception("Dosya bulunamadı")
            
            # İşlenmiş dosya yolu
            processed_path = Config.TEMP_FOLDER / f"processed_{file_path.name}"
            
            # Dosyayı işle
            if task['file_type'] == 'image':
                MediaProcessor.process_4k_image_for_instagram(
                    file_path, processed_path, task['upload_type']
                )
            else:  # video
                MediaProcessor.process_4k_video_for_instagram(
                    file_path, processed_path, task['upload_type']
                )
            
            # Upload öncesi minimal bekleme (sadece rate limiting için)
            wait_time = random.randint(5, 15)  # 5-15 saniye (daha kısa)
            logger.info(f"Waiting {wait_time} seconds before upload")
            
            # Progress indicator için task'ı güncelle
            task['status'] = 'waiting'
            task['wait_remaining'] = wait_time
            CacheManager.set(f"upload_task:{task['id']}", task)
            
            # Progress ile bekleme
            for remaining in range(wait_time, 0, -1):
                task['wait_remaining'] = remaining
                CacheManager.set(f"upload_task:{task['id']}", task)
                time.sleep(1)
            
            # Instagram'a yükle
            logger.info(f"Starting Instagram upload for task {task['id']} - {task['upload_type']}")
            task['status'] = 'uploading'
            CacheManager.set(f"upload_task:{task['id']}", task)
            
            if task['upload_type'] == 'story':
                if task['file_type'] == 'image':
                    # Resmi videoya çevir
                    video_path = processed_path.with_suffix('.mp4')
                    MediaProcessor.create_video_from_images(
                        [processed_path], video_path, duration_per_image=5
                    )
                    media = client.video_upload_to_story(video_path, caption=task['caption'])
                    video_path.unlink()
                else:
                    media = client.video_upload_to_story(processed_path, caption=task['caption'])
            
            elif task['upload_type'] == 'reel':
                media = client.clip_upload(processed_path, caption=task['caption'])
            
            else:  # post
                if task['file_type'] == 'image':
                    media = client.photo_upload(processed_path, caption=task['caption'])
                else:
                    media = client.video_upload(processed_path, caption=task['caption'])
            
            logger.info(f"Instagram upload completed for task {task['id']} - media_id: {media.pk}")
            
            # Başarılı
            task['status'] = 'completed'
            task['media_id'] = media.pk
            task['completed_at'] = datetime.now().isoformat()
            
            # Upload sonrası kısa bekleme (rate limiting için)
            if ig_manager.upload_queue:  # Kuyruktaki diğer işlemler varsa
                post_upload_wait = random.randint(30, 60)  # 30-60 saniye (çok daha kısa)
                logger.info(f"Post-upload waiting {post_upload_wait} seconds before next upload")
                
                # Progress indicator için
                for remaining in range(post_upload_wait, 0, -1):
                    # Diğer task'lar için cooldown göster
                    if ig_manager.upload_queue:
                        next_task = ig_manager.upload_queue[0]
                        if next_task['status'] == 'pending':
                            next_task['status'] = 'cooldown'
                            next_task['cooldown_remaining'] = remaining
                            CacheManager.set(f"upload_task:{next_task['id']}", next_task)
                    time.sleep(1)
            
            # Temizlik
            processed_path.unlink()
            file_path.unlink()
            
        except Exception as e:
            logger.error(f"Upload processing error: {e}")
            task['status'] = 'failed'
            task['error'] = str(e)
            task['completed_at'] = datetime.now().isoformat()
        
        finally:
            # Task'ı güncelle
            CacheManager.set(f"upload_task:{task['id']}", task)
    
    # Tamamlanan/başarısız task'ları temizle (5 dakika sonra)
    cleanup_completed_tasks()
    ig_manager.processing = False

def cleanup_completed_tasks():
    """Tamamlanan veya başarısız task'ları kuyruğundan temizle"""
    current_time = time.time()
    tasks_to_remove = []
    
    for i, task in enumerate(ig_manager.upload_queue):
        if task['status'] in ['completed', 'failed']:
            # Task'ın tamamlanma zamanını kontrol et
            completed_at = task.get('completed_at') or task.get('created_at')
            if completed_at:
                try:
                    completed_time = datetime.fromisoformat(completed_at).timestamp()
                    # 5 dakika geçmişse temizle
                    if current_time - completed_time > 300:  # 5 dakika
                        tasks_to_remove.append(i)
                except:
                    # Parsing hatası varsa da temizle
                    tasks_to_remove.append(i)
    
    # Listeden geriye doğru sil (index değişmesin diye)
    for i in reversed(tasks_to_remove):
        removed_task = ig_manager.upload_queue.pop(i)
        CacheManager.delete(f"upload_task:{removed_task['id']}")
        logger.info(f"Cleaned up completed task: {removed_task['id']}")

# Hata yönetimi
@app.errorhandler(404)
def not_found_error(error):
    if request.is_json:
        return jsonify({'success': False, 'message': 'Sayfa bulunamadı'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal error: {error}")
    if request.is_json:
        return jsonify({'success': False, 'message': 'Sunucu hatası'}), 500
    return render_template('500.html'), 500

# Uygulama başlatma
if __name__ == '__main__':
    # Development mode
    app.run(debug=True, host='0.0.0.0', port=5000)