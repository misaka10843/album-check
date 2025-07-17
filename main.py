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
import chardet
import subprocess
from utils.cueparser import CueSheet


def parse_cue_file(cue_path):
    with open(cue_path, 'rb') as f:
        raw = f.read()
        enc = chardet.detect(raw)['encoding'] or 'utf-8'
    text = raw.decode(enc, errors='ignore')

    cs = CueSheet()
    cs.setOutputFormat("%performer% - %title%", "%number% - %title%")
    print(cue_path)
    cs.setData(text)
    cs.parse()

    global_meta = {
        'performer': cs.performer,
        'title': cs.title,
        'rem': cs.rem
    }
    tracks = cs.tracks
    return global_meta, tracks


def split_audio_by_cue(audio_path, cue_path, output_dir, console):
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        'ffmpeg', '-i', audio_path,
        '-i', cue_path,
        '-map_metadata', '1',
        '-codec', 'copy',
        os.path.join(output_dir, '%02d_' + os.path.basename(audio_path))
    ]
    console.print(f"[green]正在根据 CUE 分割：{audio_path} -> {output_dir}[/]")
    subprocess.run(cmd, check=True)


def check_audio_files(directory, min_count, min_bit, do_split, csv_writer, console):
    audio_extensions = ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.aac']
    folder_audio = defaultdict(list)
    folder_cues = defaultdict(list)

    # 收集文件列表
    for root, dirs, files in os.walk(directory):
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

    for folder, audios in folder_audio.items():
        cues = folder_cues.get(folder, [])
        # 未分割音频检测
        if len(audios) == 1 and len(cues) == 1:
            status = '未分割音频'
            audio_path = os.path.join(folder, audios[0])
            cue_path = os.path.join(folder, cues[0])
            global_meta, tracks = parse_cue_file(cue_path)
            reason = f"CUE 解析成功，共 {len(tracks)} 首"
            table.add_row(f"[cyan]{status}[/]", folder, reason)
            csv_writer.writerow([status, folder, reason])

            if do_split:
                out_dir = os.path.join(folder, 'split')
                split_audio_by_cue(audio_path, cue_path, out_dir, console)
            else:
                console.print(f"[cyan]{status}[/] 文件夹 '{folder}'，可使用 --split 自动分割，共 {len(tracks)} 首曲目。")

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
                        table.add_row(f"[red]{status}[/]", filepath, reason)
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
                if meta_missing:
                    status = '元数据缺失'
                    reason = '缺少: ' + ', '.join(meta_missing)
                    table.add_row(f"[yellow]{status}[/]", filepath, reason)
                    csv_writer.writerow([status, filepath, reason])

            except Exception as e:
                status = '处理失败'
                reason = str(e)
                table.add_row(f"[magenta]{status}[/]", filepath, reason)
                csv_writer.writerow([status, filepath, reason])

    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='音频文件质量检查及分割工具')
    parser.add_argument('directory', help='要扫描的目录路径')
    parser.add_argument('--min', type=int, default=2, help='最小音频文件数量阈值 (默认:')
    parser.add_argument('--bit', type=int, default=128, help='最小音频比特率阈值 (默认: 128)')
    parser.add_argument('--split', action='store_true', help='自动根据 CUE 分割未分割音频文件')
    parser.add_argument('--output', default='results.csv', help='输出CSV文件名 (默认: results.csv)')

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"错误：目录 '{args.directory}' 不存在")
        exit(1)

    console = Console()
    console.print(f"开始扫描目录: [bold]{args.directory}[/]", style="green")
    console.print(f"检查设置: 比特率阈值([bold]{args.bit}[/]kbps) | 最小文件数([bold]{args.min}[/]) | 自动分割: {args.split}", style="green")
    console.print("-" * 60)

    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['状态', '路径', '说明'])
        check_audio_files(os.path.abspath(args.directory), args.min, args.bit, args.split, writer, console)

    console.print(f"\n扫描完成！结果已保存至 [bold]{args.output}[/]", style="green")
