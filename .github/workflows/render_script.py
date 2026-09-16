"""
Crime Video Generator — Cinematic Pipeline v2
==============================================
✓ Paper Slam opening (0.3s zoom)
✓ Ken Burns slow motion
✓ Film grain + light flicker (FFmpeg)
✓ Arabic text with fade
✓ Audio enhancement + ducking
"""

import os
import json
import subprocess
import requests
import time
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image
from moviepy.editor import (
    ImageClip, AudioFileClip, concatenate_videoclips,
    TextClip, CompositeVideoClip
)
import cloudinary
import cloudinary.uploader


# ════════════════════════════════════════════════════════
# 0) الإعدادات
# ════════════════════════════════════════════════════════
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
FONT_PATH = 'fonts/NotoNaskhArabic-Regular.ttf'

# Paper Slam: مدة الدخول السريع
SLAM_DURATION = 0.4  # ثانية
SLAM_START_ZOOM = 0.85  # نسبة التصغير في البداية

# Ken Burns: التكبير البطيء بعد الـ Slam
KENBURNS_END_ZOOM = 1.04

# Film Grain intensity (0-10)
GRAIN_INTENSITY = 4


# ════════════════════════════════════════════════════════
# 1) استقبال البيانات
# ════════════════════════════════════════════════════════
print("=" * 60)
print("🎬 بدء عملية إنتاج الفيديو")
print("=" * 60)

video_data = json.loads(os.environ['VIDEO_DATA'])
images = video_data['images']
sentences = video_data['sentences']
audio_url = video_data['audio_url']
total_duration = float(video_data.get('duration', 90))
enable_music = video_data.get('enable_music', False)

print(f"📊 عدد الصور: {len(images)}")
print(f"📝 عدد الجمل: {len(sentences)}")
print(f"⏱️ المدة: {total_duration}s")
print(f"🎵 موسيقى: {'نعم' if enable_music else 'لا'}")

per_image_duration = total_duration / len(images)
print(f"⏱️ مدة كل صورة: {per_image_duration:.2f}s")


# ════════════════════════════════════════════════════════
# 2) تحميل الصوت
# ════════════════════════════════════════════════════════
print("\n[1/8] 🎙️ تحميل الصوت...")
audio_res = requests.get(audio_url, timeout=120)
audio_res.raise_for_status()
with open('/tmp/narration.mp3', 'wb') as f:
    f.write(audio_res.content)
print(f"✅ الصوت محمّل ({len(audio_res.content) / 1024:.0f} KB)")


# ════════════════════════════════════════════════════════
# 3) تحسين الصوت
# ════════════════════════════════════════════════════════
print("\n[2/8] 🎚️ تحسين الصوت...")

audio_filter = (
    "highpass=f=80,"
    "lowpass=f=8000,"
    "acompressor=threshold=0.5:ratio=3:attack=5:release=50,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)

try:
    subprocess.run([
        'ffmpeg', '-y', '-i', '/tmp/narration.mp3',
        '-af', audio_filter,
        '-ar', '44100', '-ac', '2',
        '/tmp/narration_enhanced.mp3'
    ], check=True, capture_output=True)
    print("✅ الصوت محسّن")
except Exception:
    import shutil
    shutil.copy('/tmp/narration.mp3', '/tmp/narration_enhanced.mp3')


final_audio_path = '/tmp/narration_enhanced.mp3'


# ════════════════════════════════════════════════════════
# 4) تحميل الصور
# ════════════════════════════════════════════════════════
print("\n[3/8] 🖼️ تحميل الصور...")

for i, url in enumerate(images):
    try:
        res = requests.get(url, timeout=90)
        res.raise_for_status()
        with open(f'/tmp/img_{i}.jpg', 'wb') as f:
            f.write(res.content)
        print(f"  ✅ صورة {i+1}/{len(images)}")
    except Exception as e:
        print(f"  ⚠️ فشل {i+1}: {e}")
        if i > 0 and os.path.exists('/tmp/img_0.jpg'):
            import shutil
            shutil.copy('/tmp/img_0.jpg', f'/tmp/img_{i}.jpg')


# ════════════════════════════════════════════════════════
# 5) تجهيز الصور بـ PIL
# ════════════════════════════════════════════════════════
print("\n[4/8] 🔧 تجهيز الصور...")

for i in range(len(images)):
    src = f'/tmp/img_{i}.jpg'
    dst = f'/tmp/img_fixed_{i}.jpg'
    if not os.path.exists(src):
        continue
    try:
        img = Image.open(src).convert('RGB')
        w, h = img.size
        target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT
        current_ratio = w / h

        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))

        img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
        img.save(dst, 'JPEG', quality=92)
        print(f"  ✅ صورة {i+1}")
    except Exception as e:
        print(f"  ⚠️ فشل {i+1}: {e}")


# ════════════════════════════════════════════════════════
# 6) بناء المقاطع (Paper Slam + Ken Burns + Text Fade)
# ════════════════════════════════════════════════════════
print("\n[5/8] 🎞️ بناء المقاطع مع Paper Slam...")

clips = []

for i in range(len(images)):
    img_path = f'/tmp/img_fixed_{i}.jpg'
    if not os.path.exists(img_path):
        continue

    duration = per_image_duration

    # ─── تأثير Paper Slam + Ken Burns ───
    def make_zoom(t, dur=duration):
        if t < SLAM_DURATION:
            # دخول سريع: 0.85 → 1.0
            progress = t / SLAM_DURATION
            return SLAM_START_ZOOM + (1.0 - SLAM_START_ZOOM) * progress
        else:
            # Ken Burns بطيء: 1.0 → 1.04
            elapsed = t - SLAM_DURATION
            remaining = dur - SLAM_DURATION
            if remaining <= 0:
                return 1.0
            progress = elapsed / remaining
            return 1.0 + (KENBURNS_END_ZOOM - 1.0) * progress

    base_clip = ImageClip(img_path).set_duration(duration)

    try:
        zoomed = base_clip.resize(make_zoom)
        zoomed = zoomed.set_position('center')
    except Exception as e:
        print(f"  ⚠️ zoom فشل {i}: {e}")
        zoomed = base_clip.set_position('center')

    # ─── النص العربي مع Fade ───
    text = sentences[i] if i < len(sentences) else ""

    if text and os.path.exists(FONT_PATH):
        try:
            reshaped = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped)

            # خلفية النص (شريط شبه شفاف)
            bg_clip = TextClip(
                bidi_text,
                fontsize=52,
                color='#000000',
                font=FONT_PATH,
                stroke_color='#000000',
                stroke_width=10,
                method='caption',
                size=(VIDEO_WIDTH - 140, None),
                align='center'
            ).set_position(('center', VIDEO_HEIGHT - 520)).set_duration(duration)

            # النص الأبيض
            txt_clip = TextClip(
                bidi_text,
                fontsize=52,
                color='#F5E9D7',
                font=FONT_PATH,
                stroke_color='#1a1a1a',
                stroke_width=3,
                method='caption',
                size=(VIDEO_WIDTH - 140, None),
                align='center'
            ).set_position(('center', VIDEO_HEIGHT - 520)).set_duration(duration)

            # Fade in/out
            bg_clip = bg_clip.crossfadein(0.4).crossfadeout(0.4)
            txt_clip = txt_clip.crossfadein(0.4).crossfadeout(0.4)

            clip = CompositeVideoClip(
                [zoomed, bg_clip, txt_clip],
                size=(VIDEO_WIDTH, VIDEO_HEIGHT)
            )
            print(f"  ✅ مقطع {i+1} (نص)")
        except Exception as e:
            print(f"  ⚠️ نص فشل {i}: {e}")
            clip = CompositeVideoClip([zoomed], size=(VIDEO_WIDTH, VIDEO_HEIGHT))
            print(f"  ✅ مقطع {i+1}")
    else:
        clip = CompositeVideoClip([zoomed], size=(VIDEO_WIDTH, VIDEO_HEIGHT))
        print(f"  ✅ مقطع {i+1}")

    clips.append(clip)

if not clips:
    raise Exception("No clips generated")


# ════════════════════════════════════════════════════════
# 7) دمج + تصدير أولي
# ════════════════════════════════════════════════════════
print("\n[6/8] 🎬 دمج المقاطع...")

final_video = concatenate_videoclips(clips, method="compose")
audio = AudioFileClip(final_audio_path)
final_video = final_video.set_audio(audio)

print("💾 تصدير أولي (بدون Grain)...")
final_video.write_videofile(
    '/tmp/video_raw.mp4',
    fps=FPS,
    codec='libx264',
    audio_codec='aac',
    bitrate='8000k',
    preset='fast',
    threads=4,
    logger=None
)

size_raw = os.path.getsize('/tmp/video_raw.mp4') / (1024 * 1024)
print(f"✅ جاهز ({size_raw:.1f} MB)")


# ════════════════════════════════════════════════════════
# 8) إضافة Film Grain + Light Flicker (FFmpeg)
# ════════════════════════════════════════════════════════
print("\n[7/8] 🎞️ إضافة Film Grain + Light Flicker...")

grain_filter = (
    f"noise=alls={GRAIN_INTENSITY}:allf=t+u,"  # حبيبات فيلم
    "eq=brightness='0.02*sin(2*PI*t*1.5)':contrast=1.05"  # وميض + تباين
)

try:
    subprocess.run([
        'ffmpeg', '-y',
        '-i', '/tmp/video_raw.mp4',
        '-vf', grain_filter,
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
        '-c:a', 'copy',
        '-pix_fmt', 'yuv420p',
        '/tmp/final_output.mp4'
    ], check=True, capture_output=True)
    size_final = os.path.getsize('/tmp/final_output.mp4') / (1024 * 1024)
    print(f"✅ Grain مطبّق ({size_final:.1f} MB)")
except subprocess.CalledProcessError as e:
    print(f"⚠️ FFmpeg grain فشل: {e}")
    import shutil
    shutil.copy('/tmp/video_raw.mp4', '/tmp/final_output.mp4')
    size_final = size_raw


# ════════════════════════════════════════════════════════
# 9) رفع Cloudinary
# ════════════════════════════════════════════════════════
print("\n[8/8] ☁️ رفع إلى Cloudinary...")

cloudinary_url = os.environ['CLOUDINARY_URL']
parts = cloudinary_url.replace('cloudinary://', '').split('@')
api_key, api_secret = parts[0].split(':', 1)
cloud_name = parts[1]

cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret,
    secure=True
)

result = cloudinary.uploader.upload(
    '/tmp/final_output.mp4',
    resource_type='video',
    folder='crime_videos',
    public_id=f'crime_video_{int(time.time())}',
    overwrite=True
)

print("")
print("=" * 60)
print("🎉 تم إنشاء الفيديو بنجاح!")
print(f"🔗 الرابط: {result['secure_url']}")
print(f"⏱️ المدة: {result.get('duration', 'N/A')}s")
print(f"📦 الحجم: {size_final:.1f} MB")
print("=" * 60)
print("")
print(f"VIDEO_URL={result['secure_url']}")
