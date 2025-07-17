import os
import argparse
import csv
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from collections import defaultdict
from rich.console import Console
from rich.table import Table


def check_audio_files(directory, min_count, min_bit, csv_writer, console):
    audio_extensions = ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.aac']
    folder_audio_count = defaultdict(int)

    # 创建 Rich 表格输出
    table = Table(title="音频文件检查结果")
    table.add_column("状态", style="bold")
    table.add_column("路径")
    table.add_column("说明")

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
                        if bitrate <= min_bit:
                            status = '低比特率'
                            reason = f"当前: {bitrate}kbps"
                            table.add_row(f"[red]{status}[/]", filepath, reason)
                            csv_writer.writerow([status, filepath, reason])

                    # 检查元数据
                    meta_missing = []
                    # 通用字段检测
                    tags = None
                    unknown_metadata = False
                    if ext == '.mp3':
                        tags = MP3(filepath).tags
                        checks = {
                            'TIT2': '标题', 'TALB': '专辑', 'TPE1': '艺术家',
                            'TRCK': '曲目号', 'TCON': '流派', 'TDRC': '年份'
                        }
                        for key, name in checks.items():
                            if not tags or key not in tags or not tags.get(key):
                                meta_missing.append(name)
                        if 'APIC:' not in tags:
                            meta_missing.append('封面')

                    elif ext == '.flac':
                        flac = FLAC(filepath)
                        checks = {
                            'title': '标题', 'album': '专辑', 'artist': '艺术家',
                            'tracknumber': '曲目号', 'genre': '流派', 'date': '年份'
                        }
                        for key, name in checks.items():
                            if not flac.tags or key not in flac.tags:
                                meta_missing.append(name)
                        if not flac.pictures:
                            meta_missing.append('封面')

                    elif ext == '.m4a':
                        m4a = MP4(filepath)
                        checks = {
                            '\u00a9nam': '标题', '\u00a9alb': '专辑', '\u00a9ART': '艺术家',
                            'trkn': '曲目号', '\u00a9gen': '流派', '\u00a9day': '年份'
                        }
                        for key, name in checks.items():
                            if not m4a.tags or key not in m4a.tags:
                                meta_missing.append(name)
                        if 'covr' not in m4a.tags:
                            meta_missing.append('封面')
                    else:
                        unknown_metadata = True

                    if meta_missing:
                        status = '元数据缺失'
                        reason = '缺少: ' + ', '.join(meta_missing)
                        table.add_row(f"[yellow]{status}[/]", filepath, reason)
                        csv_writer.writerow([status, filepath, reason])
                    if unknown_metadata:
                        status = '未知元数据'
                        reason = '无法获取元数据，原因：非支持文件'
                        table.add_row(f"[yellow]{status}[/]", filepath, reason)
                        csv_writer.writerow([status, filepath, reason])

                except Exception as e:
                    status = '处理失败'
                    reason = str(e)
                    table.add_row(f"[magenta]{status}[/]", filepath, reason)
                    csv_writer.writerow([status, filepath, reason])

    # 检查文件夹音频数量
    for folder, count in folder_audio_count.items():
        if count < min_count:
            status = '数量不足'
            reason = f"仅有 {count} 个音频文件 (阈值: {min_count})"
            table.add_row(f"[blue]{status}[/]", folder, reason)
            csv_writer.writerow([status, folder, reason])

    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='音频文件质量检查工具')
    parser.add_argument('directory', help='要扫描的目录路径')
    parser.add_argument('--min', type=int, default=2,
                        help='最小音频文件数量阈值 (默认: 2)')
    parser.add_argument('--bit', type=int, default=128,
                        help='最小音频比特率阈值 (默认: 128)')
    parser.add_argument('--output', default='results.csv',
                        help='输出CSV文件名 (默认: results.csv)')

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"错误：目录 '{args.directory}' 不存在")
        exit(1)

    console = Console()
    console.print(f"开始扫描目录: [bold]{args.directory}[/]", style="green")
    console.print(f"检查设置: 比特率阈值([bold]{args.bit}[/]kbps) | 最小文件数([bold]{args.min}[/])", style="green")
    console.print("-" * 60)

    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['状态', '路径', '原因'])
        check_audio_files(os.path.abspath(args.directory), args.min, args.bit, writer, console)

    console.print(f"\n扫描完成！结果已保存至 [bold]{args.output}[/]", style="green")
