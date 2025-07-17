import os
import argparse
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from collections import defaultdict
import traceback


def check_audio_files(directory, min_count):
    # 支持的音频格式扩展名
    audio_extensions = ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.aac']
    folder_audio_count = defaultdict(int)

    for root, dirs, files in os.walk(directory):
        for filename in files:
            filepath = os.path.join(root, filename)
            ext = os.path.splitext(filename)[1].lower()

            if ext in audio_extensions:
                folder_audio_count[root] += 1

                try:
                    # 检查比特率
                    audio = File(filepath, easy=False)
                    if audio and hasattr(audio.info, 'bitrate'):
                        bitrate = audio.info.bitrate // 1000  # 转换为kbps
                        if bitrate < 480:
                            print(f"【低比特率】{filepath} (当前: {bitrate}kbps)")

                    # 检查元数据
                    meta_missing = []

                    if ext == '.mp3':
                        mp3 = MP3(filepath)
                        if not mp3.tags or not mp3.tags.get('TIT2') or not mp3.tags.get('TALB'):
                            meta_missing.append('标签')
                        if 'APIC' not in mp3:
                            meta_missing.append('封面')

                    elif ext == '.flac':
                        flac = FLAC(filepath)
                        if not flac.tags or not flac.get('title', ['']) or not flac.get('album', ['']):
                            meta_missing.append('标签')
                        if not flac.pictures:
                            meta_missing.append('封面')

                    elif ext == '.m4a':
                        m4a = MP4(filepath)
                        if not m4a.tags or not m4a.get('\xa9nam') or not m4a.get('\xa9alb'):
                            meta_missing.append('标签')
                        if 'covr' not in m4a:
                            meta_missing.append('封面')

                    if meta_missing:
                        print(f"【元数据缺失】{filepath} (缺少: {', '.join(meta_missing)})")

                except Exception as e:
                    print(f"【处理失败】{filepath} (错误: {str(e)})")

    # 检查文件夹音频数量
    for folder, count in folder_audio_count.items():
        if count < min_count:
            print(f"【数量不足】文件夹 '{folder}' 只有 {count} 个音频文件 (要求至少 {min_count} 个)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='音频文件质量检查工具')
    parser.add_argument('directory', help='要扫描的目录路径')
    parser.add_argument('--min', type=int, default=5,
                        help='最小音频文件数量阈值 (默认: 5)')

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"错误：目录 '{args.directory}' 不存在")
        exit(1)

    print(f"开始扫描目录: {args.directory}")
    print(f"检查设置: 比特率阈值(480kbps) | 最小文件数({args.min})")
    print("-" * 60)

    check_audio_files(os.path.abspath(args.directory), args.min)

    print("\n扫描完成！")