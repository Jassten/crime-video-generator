"""
Crime Video Generator — Full Render Pipeline
==========================================
- Audio enhancement (highpass, lowpass, compressor, loudnorm)
- Background music with ducking (sidechaincompress)
- Ken Burns effect on images
- Arabic text overlay with RTL support
- Cloudinary upload
"""

import os
import json
import subprocess
import requests
import time
import arabic_reshaper
from bidi.algorithm import get_display
from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeAudioClip,
    concatenate_videoclips, TextClip, CompositeVideoClip,
    VideoFileClip
)
import cloudinary
import cloudinary.uploader


# ════════════════════════════════════════════════════════
# 0) إعدادات عامة
# ════════════════════════════════════════════════════════
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
FONT_PATH = 'fonts/NotoNaskhArabic-Regular.ttf'

# موسيقى خلفية (رابط مباشر لملف mp3 هادئ)
# يمكن استبداله بأي رابط آخر
BACKGROUND_MUSIC_URL = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=dark-ambient-114557.mp3"


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
print(f"🎵 موسيقى خلفية: {'نعم' if enable_music else 'لا'}")

per_image_duration = total_duration / len(images)
print(f"⏱️ مدة كل صورة: {per_image_duration:.1f}s")


# ════════════════════════════════════════════════════════
# 2) تحميل الصوت الأصلي
# ════════════════════════════════════════════════════════
print("\n[1/6] 🎙️ تحميل الصوت الأصلي...")
audio_res = requests.get(audio_url, timeout=120)
audio_res.raise_for_status()
with open('/tmp/narration.mp3', 'wb') as f:
    f.write(audio_res.content)
print(f"✅ الصوت محمّل ({len(audio_res.content) / 1024:.0f} KB)")


# ════════════════════════════════════════════════════════
# 3) تحسين جودة الصوت بـ FFmpeg
# ════════════════════════════════════════════════════════
print("\n[2/6] 🎚️ تحسين الصوت...")

audio_filter = (
    "highpass=f=80,"           # إزالة الترددات المنخفضة (ضوضاء)
    "lowpass=f=8000,"          # إزالة الترددات العالية
    "acompressor=threshold=0.5:ratio=3:attack=5:release=50,"  # ضغط ناعم
    "loudnorm=I=-16:TP=-1.5:LRA=11"  # تطبيع المعيار
)

subprocess.run([
    'ffmpeg', '-y', '-i', '/tmp/narration.mp3',
    '-af', audio_filter,
    '-ar', '44100', '-ac', '2',
    '/tmp/narration_enhanced.mp3'
], check=True, capture_output=True)
print("✅ الصوت محسّن (فلاتر عالية الجودة)")


# ════════════════════════════════════════════════════════
# 4) إضافة موسيقى خلفية مع Ducking
# ════════════════════════════════════════════════════════
if enable_music:
    print("\n[3/6] 🎵 إضافة موسيقى خلفية (Ducking)...")
    try:
        music_res = requests.get(BACKGROUND_MUSIC_URL, timeout=60)
        with open('/tmp/music.mp3', 'wb') as f:
            f.write(music_res.content)

        # دمج الصوت + موسيقى مع Ducking
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
        print("✅ الموسيقى مدمجة (Ducking فعّال)")
        final_audio_path = '/tmp/audio_final.mp3'
    except Exception as e:
        print(f"⚠️ فشل إضافة الموسيقى: {e}")
        final_audio_path = '/tmp/narration_enhanced.mp3'
else:
    final_audio_path = '/tmp/narration_enhanced.mp3'


# ════════════════════════════════════════════════════════
# 5) تحميل الصور
# ════════════════════════════════════════════════════════
print("\n[4/6] 🖼️ تحميل الصور من Pollinations...")

for i, url in enumerate(images):
    try:
        res = requests.get(url, timeout=90)
        res.raise_for_status()
        with open(f'/tmp/img_{i}.jpg', 'wb') as f:
            f.write(res.content)
        print(f"  ✅ صورة {i+1}/{len(images)} ({len(res.content)/1024:.0f} KB)")
    except Exception as e:
        print(f"  ⚠️ فشل صورة {i+1}: {e}")
        # نسخ أول صورة كبديل
        if i > 0 and os.path.exists('/tmp/img_0.jpg'):
            import shutil
            shutil.copy('/tmp/img_0.jpg', f'/tmp/img_{i}.jpg')


# ════════════════════════════════════════════════════════
# 6) بناء المقاطع (Ken Burns + نص عربي)
# ════════════════════════════════════════════════════════
print("\n[5/6] 🎬 بناء المقاطع مع Ken Burns + النص العربي...")

clips = []

for i in range(len(images)):
    img_path = f'/tmp/img_{i}.jpg'
    if not os.path.exists(img_path):
        continue

    # ─── Ken Burns Effect (تكبير بطيء) ───
    base_clip = ImageClip(img_path).set_duration(per_image_duration)

    # تكييف الحجم (9:16)
    base_clip = base_clip.resize(height=VIDEO_HEIGHT)

    if base_clip.w < VIDEO_WIDTH:
        base_clip = base_clip.resize(width=VIDEO_WIDTH)

    # قص للنسبة الصحيحة
    base_clip = base_clip.crop(
        x_center=base_clip.w / 2,
        y_center=base_clip.h / 2,
        width=VIDEO_WIDTH,
        height=VIDEO_HEIGHT
    )

    # Ken Burns: تكبير بطيء من 1.0 إلى 1.05
    base_clip = base_clip.resize(lambda t: 1 + 0.05 * (t / per_image_duration))
    base_clip = base_clip.set_position('center')

    # ─── النص العربي ───
    text = sentences[i] if i < len(sentences) else ""

    if text and os.path.exists(FONT_PATH):
        try:
            reshaped = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped)

            # النص مع خلفية سوداء
            txt_bg = TextClip(
                bidi_text,
                fontsize=60,
                color='black',
                font=FONT_PATH,
                stroke_color='black',
                stroke_width=12,
                method='caption',
                size=(VIDEO_WIDTH - 120, None),
                align='center'
            ).set_position(('center', VIDEO_HEIGHT - 500)).set_duration(per_image_duration)

            txt = TextClip(
                bidi_text,
                fontsize=60,
                color='white',
                font=FONT_PATH,
                stroke_color='black',
                stroke_width=2,
                method='caption',
                size=(VIDEO_WIDTH - 120, None),
                align='center'
            ).set_position(('center', VIDEO_HEIGHT - 500)).set_duration(per_image_duration)

            clip = CompositeVideoClip(
                [base_clip, txt_bg, txt],
                size=(VIDEO_WIDTH, VIDEO_HEIGHT)
            )
        except Exception as e:
            print(f"  ⚠️ فشل النص {i+1}: {e}")
            clip = CompositeVideoClip([base_clip], size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    else:
        clip = CompositeVideoClip([base_clip], size=(VIDEO_WIDTH, VIDEO_HEIGHT))

    clips.append(clip)
    print(f"  ✅ مقطع {i+1}/{len(images)}")


# ════════════════════════════════════════════════════════
# 7) دمج المقاطع + الصوت + تصدير
# ════════════════════════════════════════════════════════
print("\n[6/6] 🎞️ دمج المقاطع وإضافة الصوت...")

final_video = concatenate_videoclips(clips, method="compose")

# إضافة الصوت
audio = AudioFileClip(final_audio_path)
final_video = final_video.set_audio(audio)

# تصدير
print("💾 تصدير الفيديو...")
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
# 8) رفع إلى Cloudinary
# ════════════════════════════════════════════════════════
print("\n☁️ رفع إلى Cloudinary...")

cloudinary.config(cloudinary_url=os.environ['CLOUDINARY_URL'])

result = cloudinary.uploader.upload(
    '/tmp/final_output.mp4',
    resource_type='video',
    folder='crime_videos',
    public_id=f'crime_video_{int(time.time())}',
    overwrite=True
)

print("=" * 60)
print("🎉 تم إنشاء الفيديو بنجاح!")
print(f"🔗 الرابط: {result['secure_url']}")
print(f"⏱️ المدة: {result.get('duration', 'N/A')}s")
print(f"📦 الحجم: {size_mb:.1f} MB")
print("=" * 60)

# طباعة الرابط ليتم التقاطه
print(f"\nVIDEO_URL={result['secure_url']}")
