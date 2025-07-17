import os
import argparse
import csv
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from collections import defaultdict

def check_audio_files(directory, min_count, csv_writer):
    audio_extensions = ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.aac']
    folder_audio_count = defaultdict(int)

    # 扫描所有文件
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
                        bitrate = audio.info.bitrate // 1000
                        if bitrate < 480:
                            status = '低比特率'
                            reason = f"当前: {bitrate}kbps"
                            print(f"【{status}】{filepath} ({reason})")
                            csv_writer.writerow([status, filepath, reason])

                    # 检查元数据
                    meta_missing = []
                    if ext == '.mp3':
                        mp3 = MP3(filepath)
                        if not mp3.tags or not mp3.tags.get('TIT2') or not mp3.tags.get('TALB'):
                            meta_missing.append('标签')
                        if 'APIC:' not in mp3:
                            meta_missing.append('封面')

                    elif ext == '.flac':
                        flac = FLAC(filepath)
                        if not flac.tags or not flac.get('title') or not flac.get('album'):
                            meta_missing.append('标签')
                        if not flac.pictures:
                            meta_missing.append('封面')

                    elif ext == '.m4a':
                        m4a = MP4(filepath)
                        if not m4a.tags or not m4a.get('\u00a9nam') or not m4a.get('\u00a9alb'):
                            meta_missing.append('标签')
                        if 'covr' not in m4a:
                            meta_missing.append('封面')

                    if meta_missing:
                        status = '元数据缺失'
                        reason = '缺少: ' + ', '.join(meta_missing)
                        print(f"【{status}】{filepath} ({reason})")
                        csv_writer.writerow([status, filepath, reason])

                except Exception as e:
                    status = '处理失败'
                    reason = str(e)
                    print(f"【{status}】{filepath} (错误: {reason})")
                    csv_writer.writerow([status, filepath, reason])

    # 检查文件夹音频数量
    for folder, count in folder_audio_count.items():
        if count < min_count:
            status = '数量不足'
            reason = f"仅有 {count} 个音频文件 (阈值: {min_count})"
            print(f"【{status}】文件夹 '{folder}' ({reason})")
            csv_writer.writerow([status, folder, reason])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='音频文件质量检查工具')
    parser.add_argument('directory', help='要扫描的目录路径')
    parser.add_argument('--min', type=int, default=2,
                        help='最小音频文件数量阈值 (默认: 2)')
    parser.add_argument('--output', default='results.csv',
                        help='输出CSV文件名 (默认: results.csv)')

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"错误：目录 '{args.directory}' 不存在")
        exit(1)

    print(f"开始扫描目录: {args.directory}")
    print(f"检查设置: 比特率阈值(480kbps) | 最小文件数({args.min})")
    print("-" * 60)

    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # CSV 标题: 状态、路径、原因
        writer.writerow(['状态', '路径', '原因'])
        check_audio_files(os.path.abspath(args.directory), args.min, writer)

    print(f"\n扫描完成！结果已保存至 {args.output}")
