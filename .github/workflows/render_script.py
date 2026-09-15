"""
Crime Video Generator — Full Render Pipeline
=============================================
✓ Audio enhancement (highpass, lowpass, compressor, loudnorm)
✓ Background music with ducking (sidechaincompress)
✓ PIL image preprocessing (fixes MoviePy resize bug)
✓ Ken Burns effect on images
✓ Arabic text overlay with RTL support
✓ Cloudinary upload
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
# 0) الإعدادات العامة
# ════════════════════════════════════════════════════════
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
FONT_PATH = 'fonts/NotoNaskhArabic-Regular.ttf'

# موسيقى خلفية هادئة (Pixabay — رابط مباشر)
BACKGROUND_MUSIC_URL = (
    "https://cdn.pixabay.com/download/audio/2022/05/27/"
    "audio_1808fbf07a.mp3?filename=dark-ambient-114557.mp3"
)


# ════════════════════════════════════════════════════════
# 1) استقبال البيانات من Pipedream
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
print(f"⏱️ المدة الكلية: {total_duration}s")
print(f"🎵 موسيقى خلفية: {'نعم' if enable_music else 'لا'}")

per_image_duration = total_duration / len(images)
print(f"⏱️ مدة كل صورة: {per_image_duration:.2f}s")


# ════════════════════════════════════════════════════════
# 2) تحميل الصوت الأصلي
# ════════════════════════════════════════════════════════
print("\n[1/7] 🎙️ تحميل الصوت من Cloudinary...")
try:
    audio_res = requests.get(audio_url, timeout=120)
    audio_res.raise_for_status()
    with open('/tmp/narration.mp3', 'wb') as f:
        f.write(audio_res.content)
    print(f"✅ الصوت محمّل ({len(audio_res.content) / 1024:.0f} KB)")
except Exception as e:
    print(f"❌ فشل تحميل الصوت: {e}")
    raise


# ════════════════════════════════════════════════════════
# 3) تحسين جودة الصوت بـ FFmpeg
# ════════════════════════════════════════════════════════
print("\n[2/7] 🎚️ تحسين الصوت...")

audio_filter = (
    "highpass=f=80,"                                                 # إزالة الضوضاء المنخفضة
    "lowpass=f=8000,"                                                # إزالة الترددات العالية
    "acompressor=threshold=0.5:ratio=3:attack=5:release=50,"         # ضغط ناعم
    "loudnorm=I=-16:TP=-1.5:LRA=11"                                  # معيار البث
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
    print(f"⚠️ فشل تحسين الصوت: {e.stderr.decode()[:200] if e.stderr else e}")
    import shutil
    shutil.copy('/tmp/narration.mp3', '/tmp/narration_enhanced.mp3')


# ════════════════════════════════════════════════════════
# 4) إضافة موسيقى خلفية مع Ducking
# ════════════════════════════════════════════════════════
final_audio_path = '/tmp/narration_enhanced.mp3'

if enable_music:
    print("\n[3/7] 🎵 إضافة موسيقى خلفية (Ducking)...")
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
        print("✅ الموسيقى مدمجة (Ducking فعّال)")
        final_audio_path = '/tmp/audio_final.mp3'
    except Exception as e:
        print(f"⚠️ فشل إضافة الموسيقى: {e}")
        final_audio_path = '/tmp/narration_enhanced.mp3'
else:
    print("\n[3/7] ⏭️ تخطي الموسيقى (معطّلة)")


# ════════════════════════════════════════════════════════
# 5) تحميل الصور من Pollinations
# ════════════════════════════════════════════════════════
print("\n[4/7] 🖼️ تحميل الصور من Pollinations...")

for i, url in enumerate(images):
    try:
        res = requests.get(url, timeout=90)
        res.raise_for_status()
        with open(f'/tmp/img_{i}.jpg', 'wb') as f:
            f.write(res.content)
        print(f"  ✅ صورة {i+1}/{len(images)} ({len(res.content)/1024:.0f} KB)")
    except Exception as e:
        print(f"  ⚠️ فشل صورة {i+1}: {e}")
        if i > 0 and os.path.exists('/tmp/img_0.jpg'):
            import shutil
            shutil.copy('/tmp/img_0.jpg', f'/tmp/img_{i}.jpg')


# ════════════════════════════════════════════════════════
# 6) تجهيز الصور بـ PIL (حجم موحد 1080×1920)
# ════════════════════════════════════════════════════════
print("\n[5/7] 🔧 تجهيز الصور بـ PIL...")

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

        # قص للنسبة الصحيحة (Center Crop)
        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img.crop((left, 0, left + new_w, h))
        else:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img.crop((0, top, w, top + new_h))

        # تغيير الحجم إلى 1080×1920
        img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
        img.save(dst, 'JPEG', quality=92)
        print(f"  ✅ صورة {i+1} جاهزة (1080×1920)")
    except Exception as e:
        print(f"  ⚠️ فشل تجهيز صورة {i+1}: {e}")


# ════════════════════════════════════════════════════════
# 7) بناء المقاطع (Ken Burns + النص العربي)
# ════════════════════════════════════════════════════════
print("\n[6/7] 🎞️ بناء المقاطع مع Ken Burns + النص...")

clips = []

for i in range(len(images)):
    img_path = f'/tmp/img_fixed_{i}.jpg'
    if not os.path.exists(img_path):
        continue

    # Clip أساسي
    base_clip = ImageClip(img_path).set_duration(per_image_duration)

    # ─── Ken Burns: تكبير بطيء من 1.0 إلى 1.08 ───
    try:
        dur = per_image_duration
        zoomed = base_clip.resize(lambda t: 1.0 + 0.08 * (t / dur))
        zoomed = zoomed.set_position('center')
    except Exception as e:
        print(f"  ⚠️ Ken Burns فشل {i}: {e}")
        zoomed = base_clip.set_position('center')

    # ─── النص العربي ───
    text = sentences[i] if i < len(sentences) else ""

    if text and os.path.exists(FONT_PATH):
        try:
            reshaped = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped)

            # خلفية النص (سميكة)
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
            ).set_position(('center', VIDEO_HEIGHT - 480)).set_duration(per_image_duration)

            # النص الأمامي (أبيض)
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
            ).set_position(('center', VIDEO_HEIGHT - 480)).set_duration(per_image_duration)

            clip = CompositeVideoClip(
                [zoomed, txt_bg, txt],
                size=(VIDEO_WIDTH, VIDEO_HEIGHT)
            )
        except Exception as e:
            print(f"  ⚠️ النص فشل {i}: {e}")
            clip = CompositeVideoClip([zoomed], size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    else:
        clip = CompositeVideoClip([zoomed], size=(VIDEO_WIDTH, VIDEO_HEIGHT))

    clips.append(clip)
    print(f"  ✅ مقطع {i+1}/{len(images)}")

if not clips:
    print("❌ لا توجد مقاطع — توقف")
    raise Exception("No clips generated")


# ════════════════════════════════════════════════════════
# 8) دمج المقاطع + الصوت
# ════════════════════════════════════════════════════════
print("\n[7/7] 🎬 دمج المقاطع وإضافة الصوت...")

final_video = concatenate_videoclips(clips, method="compose")

# إضافة الصوت
audio = AudioFileClip(final_audio_path)
final_video = final_video.set_audio(audio)

# تصدير الفيديو
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
# 9) رفع إلى Cloudinary
# ════════════════════════════════════════════════════════
print("\n☁️ رفع الفيديو إلى Cloudinary...")

cloudinary.config(cloudinary_url=os.environ['CLOUDINARY_URL'])

result = cloudinary.uploader.upload(
    '/tmp/final_output.mp4',
    resource_type='video',
    folder='crime_videos',
    public_id=f'crime_video_{int(time.time())}',
    overwrite=True
)

# ════════════════════════════════════════════════════════
# 10) النتيجة النهائية
# ════════════════════════════════════════════════════════
print("")
print("=" * 60)
print("🎉 تم إنشاء الفيديو بنجاح!")
print(f"🔗 الرابط: {result['secure_url']}")
print(f"⏱️ المدة: {result.get('duration', 'N/A')}s")
print(f"📦 الحجم: {size_mb:.1f} MB")
print("=" * 60)
print("")
print(f"VIDEO_URL={result['secure_url']}")
