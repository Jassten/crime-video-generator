"""
Crime Video Generator — Full Render Pipeline
=============================================
✓ Audio enhancement (highpass, lowpass, compressor, loudnorm)
✓ Background music with ducking (sidechaincompress)
✓ PIL image preprocessing (fixes MoviePy resize bug)
✓ Ken Burns effect on images
✓ Arabic text overlay with RTL support
✓ Cloudinary upload with manual URL parsing
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
    ImageClip, AudioFileClip, CompositeAudioClip,
    concatenate_videoclips, TextClip, CompositeVideoClip
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

BACKGROUND_MUSIC_URL = (
    "https://cdn.pixabay.com/download/audio/2022/05/27/"
    "audio_1808fbf07a.mp3?filename=dark-ambient-114557.mp3"
)


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
enable_music = video_data.get('enable_music', True)

print(f"📊 عدد الصور: {len(images)}")
print(f"📝 عدد الجمل: {len(sentences)}")
print(f"⏱️ المدة: {total_duration}s")
print(f"🎵 موسيقى: {'نعم' if enable_music else 'لا'}")

per_image_duration = total_duration / len(images)
print(f"⏱️ مدة كل صورة: {per_image_duration:.2f}s")


# ════════════════════════════════════════════════════════
# 2) تحميل الصوت
# ════════════════════════════════════════════════════════
print("\n[1/7] 🎙️ تحميل الصوت...")
audio_res = requests.get(audio_url, timeout=120)
audio_res.raise_for_status()
with open('/tmp/narration.mp3', 'wb') as f:
    f.write(audio_res.content)
print(f"✅ الصوت محمّل ({len(audio_res.content) / 1024:.0f} KB)")


# ════════════════════════════════════════════════════════
# 3) تحسين الصوت
# ════════════════════════════════════════════════════════
print("\n[2/7] 🎚️ تحسين الصوت...")

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
    print("✅ الصوت محسّن (4 فلاتر)")
except subprocess.CalledProcessError as e:
    print(f"⚠️ فشل التحسين، استخدام الصوت الأصلي")
    import shutil
    shutil.copy('/tmp/narration.mp3', '/tmp/narration_enhanced.mp3')


# ════════════════════════════════════════════════════════
# 4) موسيقى خلفية (Ducking)
# ════════════════════════════════════════════════════════
final_audio_path = '/tmp/narration_enhanced.mp3'

if enable_music:
    print("\n[3/7] 🎵 إضافة موسيقى (Ducking)...")
    try:
        music_res = requests.get(BACKGROUND_MUSIC_URL, timeout=60)
        music_res.raise_for_status()
        with open('/tmp/music.mp3', 'wb') as f:
            f.write(music_res.content)

        ducking_filter = (
            "[1:a]volume=0.15[music];"
            "[music][0:a]sidechaincompress="
            "threshold=0.05:ratio=8:attack=20:release=400[ducked];"
            "[0:a][ducked]amix=inputs=2:duration=first:normalize=0[a]"
        )

        subprocess.run([
            'ffmpeg', '-y',
            '-i', '/tmp/narration_enhanced.mp3',
            '-i', '/tmp/music.mp3',
            '-filter_complex', ducking_filter,
            '-map', '[a]',
            '-c:a', 'libmp3lame', '-b:a', '192k',
            '-shortest',
            '/tmp/audio_final.mp3'
        ], check=True, capture_output=True)
        print("✅ الموسيقى مدمجة")
        final_audio_path = '/tmp/audio_final.mp3'
    except Exception as e:
        print(f"⚠️ تخطي الموسيقى: {e}")
else:
    print("\n[3/7] ⏭️ تخطي الموسيقى")


# ════════════════════════════════════════════════════════
# 5) تحميل الصور
# ════════════════════════════════════════════════════════
print("\n[4/7] 🖼️ تحميل الصور...")

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
# 6) تجهيز الصور بـ PIL
# ════════════════════════════════════════════════════════
print("\n[5/7] 🔧 تجهيز الصور...")

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
# 7) بناء المقاطع
# ════════════════════════════════════════════════════════
print("\n[6/7] 🎞️ بناء المقاطع...")

clips = []

for i in range(len(images)):
    img_path = f'/tmp/img_fixed_{i}.jpg'
    if not os.path.exists(img_path):
        continue

    base_clip = ImageClip(img_path).set_duration(per_image_duration)

    # Ken Burns
    try:
        dur = per_image_duration
        zoomed = base_clip.resize(lambda t: 1.0 + 0.08 * (t / dur))
        zoomed = zoomed.set_position('center')
    except Exception as e:
        print(f"  ⚠️ Ken Burns {i}: {e}")
        zoomed = base_clip.set_position('center')

    # نص عربي
    text = sentences[i] if i < len(sentences) else ""

    if text and os.path.exists(FONT_PATH):
        try:
            reshaped = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped)

            txt_bg = TextClip(
                bidi_text, fontsize=60, color='black', font=FONT_PATH,
                stroke_color='black', stroke_width=12,
                method='caption', size=(VIDEO_WIDTH - 120, None), align='center'
            ).set_position(('center', VIDEO_HEIGHT - 480)).set_duration(per_image_duration)

            txt = TextClip(
                bidi_text, fontsize=60, color='white', font=FONT_PATH,
                stroke_color='black', stroke_width=2,
                method='caption', size=(VIDEO_WIDTH - 120, None), align='center'
            ).set_position(('center', VIDEO_HEIGHT - 480)).set_duration(per_image_duration)

            clip = CompositeVideoClip(
                [zoomed, txt_bg, txt],
                size=(VIDEO_WIDTH, VIDEO_HEIGHT)
            )
        except Exception as e:
            print(f"  ⚠️ نص فشل {i}: {e}")
            clip = CompositeVideoClip([zoomed], size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    else:
        clip = CompositeVideoClip([zoomed], size=(VIDEO_WIDTH, VIDEO_HEIGHT))

    clips.append(clip)
    print(f"  ✅ مقطع {i+1}/{len(images)}")

if not clips:
    raise Exception("No clips generated")


# ════════════════════════════════════════════════════════
# 8) دمج + تصدير
# ════════════════════════════════════════════════════════
print("\n[7/7] 🎬 دمج + تصدير...")

final_video = concatenate_videoclips(clips, method="compose")
audio = AudioFileClip(final_audio_path)
final_video = final_video.set_audio(audio)

final_video.write_videofile(
    '/tmp/final_output.mp4',
    fps=FPS,
    codec='libx264',
    audio_codec='aac',
    bitrate='6000k',
    preset='medium',
    threads=4,
    logger=None
)

size_mb = os.path.getsize('/tmp/final_output.mp4') / (1024 * 1024)
print(f"✅ الفيديو جاهز ({size_mb:.1f} MB)")


# ════════════════════════════════════════════════════════
# 9) رفع Cloudinary (parse manual)
# ════════════════════════════════════════════════════════
print("\n☁️ رفع إلى Cloudinary...")

cloudinary_url = os.environ['CLOUDINARY_URL']
try:
    parts = cloudinary_url.replace('cloudinary://', '').split('@')
    auth = parts[0].split(':')
    api_key = auth[0]
    api_secret = auth[1]
    cloud_name = parts[1]

    print(f"🔑 Cloud: {cloud_name} | Key: {api_key[:8]}...")

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
    print(f"📦 الحجم: {size_mb:.1f} MB")
    print("=" * 60)
    print("")
    print(f"VIDEO_URL={result['secure_url']}")

except Exception as e:
    print(f"❌ فشل الرفع: {e}")
    raise
