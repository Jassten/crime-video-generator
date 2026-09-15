import os
import json
import subprocess
import requests
import arabic_reshaper
from bidi.algorithm import get_display
from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeAudioClip,
    concatenate_videoclips, TextClip, CompositeVideoClip
)
import cloudinary
import cloudinary.uploader

# ════════════════════════════════════════
# 1) استقبال البيانات
# ════════════════════════════════════════
video_data = json.loads(os.environ['VIDEO_DATA'])
images = video_data['images']
sentences = video_data['sentences']
audio_url = video_data['audio_url']
total_duration = float(video_data['duration'])

per_image_duration = total_duration / len(images)
print(f"📊 {len(images)} صور × {per_image_duration:.1f}s = {total_duration}s")

# ════════════════════════════════════════
# 2) تحميل الصوت من Cloudinary
# ════════════════════════════════════════
print("🎙️ تحميل الصوت...")
audio_res = requests.get(audio_url, timeout=60)
with open('/tmp/narration.mp3', 'wb') as f:
    f.write(audio_res.content)
print(f"✅ الصوت محمّل ({len(audio_res.content) / 1024:.0f} KB)")

# ════════════════════════════════════════
# 3) تحسين الصوت بـ FFmpeg
# ════════════════════════════════════════
print("🎚️ تحسين الصوت...")
subprocess.run([
    'ffmpeg', '-y', '-i', '/tmp/narration.mp3',
    '-af', 'highpass=f=80,lowpass=f=8000,acompressor=threshold=0.5:ratio=3:attack=5:release=50,loudnorm=I=-16:TP=-1.5:LRA=11',
    '-ar', '44100', '-ac', '2',
    '/tmp/narration_enhanced.mp3'
], check=True)
print("✅ الصوت محسّن")

# ════════════════════════════════════════
# 4) تحميل الصور
# ════════════════════════════════════════
print("🖼️ تحميل الصور...")
for i, url in enumerate(images):
    res = requests.get(url, timeout=60)
    with open(f'/tmp/img_{i}.jpg', 'wb') as f:
        f.write(res.content)
print(f"✅ {len(images)} صور محمّلة")

# ════════════════════════════════════════
# 5) إنشاء المقاطع مع Ken Burns + نصوص
# ════════════════════════════════════════
print("🎬 بناء المقاطع...")
font_path = 'fonts/NotoNaskhArabic-Regular.ttf'
clips = []

for i, img_path in enumerate([f'/tmp/img_{j}.jpg' for j in range(len(images))]):
    # Ken Burns: تكبير بطيء
    clip = (ImageClip(img_path)
            .set_duration(per_image_duration)
            .resize(lambda t: 1 + 0.04 * t)
            .set_position('center'))
    clip = clip.resize(height=1920).crop(x_center=clip.w/2, y_center=clip.h/2, width=1080, height=1920)

    # النص العربي
    text = sentences[i] if i < len(sentences) else ""
    if text:
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)

        try:
            txt = TextClip(
                bidi_text,
                fontsize=55,
                color='white',
                font=font_path,
                stroke_color='black',
                stroke_width=3,
                method='caption',
                size=(900, None),
                align='center'
            )
            txt = txt.set_position(('center', 1400)).set_duration(per_image_duration)

            # خلفية شبه شفافة للنص
            bg = (TextClip(
                bidi_text,
                fontsize=55,
                color='black',
                font=font_path,
                stroke_color='black',
                stroke_width=8,
                method='caption',
                size=(900, None),
                align='center'
            ).set_position(('center', 1400)).set_duration(per_image_duration))

            clip = CompositeVideoClip([clip, bg, txt])
        except Exception as e:
            print(f"⚠️ فشل النص {i}: {e}")
            clip = CompositeVideoClip([clip])

    clips.append(clip)

# ════════════════════════════════════════
# 6) دمج المقاطع
# ════════════════════════════════════════
print("🎞️ دمج المقاطع...")
final_video = concatenate_videoclips(clips, method="compose")

# ════════════════════════════════════════
# 7) إضافة الصوت
# ════════════════════════════════════════
voice = AudioFileClip('/tmp/narration_enhanced.mp3')
final_video = final_video.set_audio(voice)

# ════════════════════════════════════════
# 8) تصدير الفيديو
# ════════════════════════════════════════
print("💾 تصدير الفيديو...")
final_video.write_videofile(
    '/tmp/final_output.mp4',
    fps=30,
    codec='libx264',
    audio_codec='aac',
    bitrate='5000k',
    preset='medium',
    threads=4,
    logger='bar'
)

# ════════════════════════════════════════
# 9) رفع إلى Cloudinary
# ════════════════════════════════════════
print("☁️ رفع إلى Cloudinary...")
cloudinary.config(cloudinary_url=os.environ['CLOUDINARY_URL'])

result = cloudinary.uploader.upload(
    '/tmp/final_output.mp4',
    resource_type='video',
    folder='crime_videos',
    public_id=f'video_{int(__import__("time").time())}'
)

print("════════════════════════════════════")
print(f"🎬 الفيديو جاهز!")
print(f"URL: {result['secure_url']}")
print(f"المدة: {result.get('duration', 'N/A')}s")
print("════════════════════════════════════")
