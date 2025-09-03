import argparse
import csv
import os
from collections import defaultdict

import chardet
from mutagen import File
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from utils.cueparser import CueSheet


def parse_cue_file(cue_path):
    with open(cue_path, 'rb') as fl:
        raw = fl.read()
        enc = chardet.detect(raw)['encoding'] or 'utf-8'
    text = raw.decode(enc, errors='ignore')

    cs = CueSheet()
    cs.setOutputFormat("%performer% - %title%", "%number% - %title%")
    cs.setData(text)
    cs.parse()

    global_meta = {
        'performer': cs.performer,
        'title': cs.title,
        'rem': cs.rem
    }
    tracks = cs.tracks
    return global_meta, tracks


def check_audio_files(directory, min_count, min_bit, c_skip_tags, csv_writer, c_console):
    audio_extensions = ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.aac']
    folder_audio = defaultdict(list)
    folder_cues = defaultdict(list)
    all_dirs = set()

    # 收集文件列表
    c_console.print(f"🗃️ 收集文件目录中...", style="cyan")
    for root, dirs, files in os.walk(directory):
        all_dirs.add(root)
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in audio_extensions:
                folder_audio[root].append(filename)
            elif ext == '.cue':
                folder_cues[root].append(filename)

    table = Table(title="音频文件检查及分割结果")
    table.add_column("状态", style="bold")
    table.add_column("路径")
    table.add_column("说明")

    # 检测嵌套文件夹
    c_console.print(f"📂 正在检查嵌套文件夹...", style="cyan")
    for folder in sorted(all_dirs):
        if folder not in folder_audio:
            # 检查是否有子目录包含音频
            has_child_audio = any(
                child.startswith(folder + os.sep) and child in folder_audio
                for child in folder_audio.keys()
            )
            if has_child_audio:
                status = '嵌套目录'
                reason = '此目录无音频，但子目录中存在音频文件'
                table.add_row(f"[magenta3]{status}[/]", folder, reason)
                csv_writer.writerow([status, folder, reason])

    with Progress(console=c_console, transient=True) as progress:
        task = progress.add_task("[cyan]📄 正在检查音频文件...", total=len(folder_audio))
        # 处理每个包含音频的目录
        for folder in sorted(folder_audio.keys()):
            audios = folder_audio[folder]
            cues = folder_cues.get(folder, [])

            # 未分割音频检测
            if len(audios) == 1 and len(cues) == 1:
                status = '未分割音频'
                cue_path = os.path.join(folder, cues[0])
                global_meta, tracks = parse_cue_file(cue_path)
                reason = f"CUE 解析成功，共 {len(tracks)} 首"
                table.add_row(f"[cyan]{status}[/]", folder, reason)
                csv_writer.writerow([status, folder, reason])

            # 文件数量检查
            count = len(audios)
            if count < min_count and not (len(audios) == 1 and len(cues) == 1):
                status = '数量不足'
                reason = f"仅有 {count} 个音频文件 (阈值: {min_count})"
                table.add_row(f"[blue]{status}[/]", folder, reason)
                csv_writer.writerow([status, folder, reason])

            # 每个音频文件检查
            for filename in audios:
                filepath = os.path.join(folder, filename)
                try:
                    # 比特率检查
                    audio = File(filepath, easy=False)
                    if audio and hasattr(audio.info, 'bitrate'):
                        bitrate = audio.info.bitrate // 1000
                        if bitrate <= min_bit:
                            status = '低比特率'
                            reason = f"当前: {bitrate}kbps"
                            table.add_row(f"[red]{status}[/]", str(filepath), reason)
                            csv_writer.writerow([status, filepath, reason])

                    # 元数据检查
                    ext = os.path.splitext(filename)[1].lower()
                    meta_missing = []
                    if ext == '.mp3':
                        tags = MP3(filepath).tags
                        checks = {
                            'TIT2': '标题', 'TALB': '专辑', 'TPE1': '艺术家',
                            'TRCK': '曲目号', 'TCON': '流派', 'TDRC': '年份'
                        }
                        for key, name in checks.items():
                            if name in c_skip_tags:
                                continue
                            if not tags or key not in tags or not tags.get(key):
                                meta_missing.append(name)
                        if '封面' not in c_skip_tags and ('APIC:' not in tags if tags else True):
                            meta_missing.append('封面')
                    elif ext == '.flac':
                        flac = FLAC(filepath)
                        checks = {
                            'title': '标题', 'album': '专辑', 'artist': '艺术家',
                            'tracknumber': '曲目号', 'genre': '流派', 'date': '年份'
                        }
                        for key, name in checks.items():
                            if name in c_skip_tags:
                                continue
                            if not flac.tags or key not in flac.tags:
                                meta_missing.append(name)
                        if '封面' not in c_skip_tags and not flac.pictures:
                            meta_missing.append('封面')
                    elif ext == '.m4a':
                        m4a = MP4(filepath)
                        checks = {
                            '\u00a9nam': '标题', '\u00a9alb': '专辑', '\u00a9ART': '艺术家',
                            'trkn': '曲目号', '\u00a9gen': '流派', '\u00a9day': '年份'
                        }
                        for key, name in checks.items():
                            if name in c_skip_tags:
                                continue
                            if not m4a.tags or key not in m4a.tags:
                                meta_missing.append(name)
                        if '封面' not in c_skip_tags and 'covr' not in m4a.tags:
                            meta_missing.append('封面')
                    if meta_missing:
                        status = '元数据缺失'
                        reason = '缺少: ' + ', '.join(meta_missing)
                        table.add_row(f"[yellow]{status}[/]", str(filepath), reason)
                        csv_writer.writerow([status, filepath, reason])

                except Exception as e:
                    status = '处理失败'
                    reason = str(e)
                    table.add_row(f"[magenta]{status}[/]", str(filepath), reason)
                    csv_writer.writerow([status, filepath, reason])
            progress.update(task, advance=1)

    c_console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='音频文件质量检查及分割工具')
    parser.add_argument('directory', help='要扫描的目录路径')
    parser.add_argument('--min', type=int, default=2, help='最小音频文件数量阈值 (默认:')
    parser.add_argument('--bit', type=int, default=128, help='最小音频比特率阈值 (默认: 128)')
    parser.add_argument('--skip-tags', default='', help='要跳过检查的元数据，逗号分隔，如: 流派,年份,封面 (支持列表：标题,专辑,艺术家,曲目号,流派,年份)')
    parser.add_argument('--output', default='results.csv', help='输出CSV文件名 (默认: results.csv)')

    args = parser.parse_args()
    skip_tags = set([t.strip() for t in args.skip_tags.split(',') if t.strip()])

    if not os.path.isdir(args.directory):
        print(f"错误：目录 '{args.directory}' 不存在")
        exit(1)

    console = Console()
    console.print(f"开始扫描目录: [bold]{args.directory}[/]", style="green")
    console.print(f"检查设置: 比特率阈值([bold]{args.bit}[/]kbps) | 最小文件数([bold]{args.min}[/])", style="green")
    console.print("-" * 60)

    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['状态', '路径', '说明'])
        check_audio_files(os.path.abspath(args.directory), args.min, args.bit, skip_tags, writer, console)

    console.print(f"\n扫描完成！结果已保存至 [bold]{args.output}[/]", style="green")
