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

TAG_MAP = {
    "标题": {"mp3": "TIT2", "flac": "title", "m4a": "\u00a9nam"},
    "专辑": {"mp3": "TALB", "flac": "album", "m4a": "\u00a9alb"},
    "艺术家": {"mp3": "TPE1", "flac": "artist", "m4a": "\u00a9ART"},
    "曲目号": {"mp3": "TRCK", "flac": "tracknumber", "m4a": "trkn"},
    "流派": {"mp3": "TCON", "flac": "genre", "m4a": "\u00a9gen"},
    "年份": {"mp3": "TDRC", "flac": "date", "m4a": "\u00a9day"},
}


def get_tag_value(ext, tags, tag_name):
    key = TAG_MAP.get(tag_name, {}).get(ext)
    if not key or not tags:
        return ""
    try:
        if ext == "mp3":
            return str(tags.get(key)) if key in tags else ""
        elif ext == "flac":
            return str(tags.get(key, [""])[0])
        elif ext == "m4a":
            return str(tags.tags.get(key, [""])[0])
    except Exception:
        return ""
    return ""


def check_metadata(filepath, c_skip_tags):
    ext = os.path.splitext(filepath)[1].lower().lstrip(".")
    meta_missing = []

    # 根据扩展名读取 tags
    tags = None
    try:
        if ext == "mp3":
            tags = MP3(filepath).tags
        elif ext == "flac":
            tags = FLAC(filepath).tags
        elif ext == "m4a":
            tags = MP4(filepath)
    except Exception as e:
        return ["读取标签失败"]

    # 遍历 TAG_MAP 里的中文名
    for name, key_map in TAG_MAP.items():
        if name in c_skip_tags:
            continue
        key = key_map.get(ext)
        if not key:
            continue

        # 根据不同格式检查值是否存在
        if ext == "mp3":
            if not tags or key not in tags or not tags.get(key):
                meta_missing.append(name)
        elif ext == "flac":
            if not tags or key not in tags:
                meta_missing.append(name)
        elif ext == "m4a":
            if not tags.tags or key not in tags.tags:
                meta_missing.append(name)

    # 检查封面
    if "封面" not in c_skip_tags:
        if ext == "mp3":
            if not tags or not any(k.startswith("APIC") for k in tags.keys()):
                meta_missing.append("封面")
        elif ext == "flac":
            if not tags or not getattr(FLAC(filepath), "pictures", []):
                meta_missing.append("封面")
        elif ext == "m4a":
            if not tags or "covr" not in tags.tags:
                meta_missing.append("封面")

    return meta_missing


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


def check_audio_files(directory, min_count, min_bit, c_skip_tags, c_dup_tags, csv_writer, c_console):
    audio_extensions = ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.aac']
    folder_audio = defaultdict(list)
    folder_cues = defaultdict(list)
    all_dirs = set()
    duplicates = defaultdict(list)

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
                ext = os.path.splitext(filename)[1].lower()[1:]  # 去掉点
                try:
                    audio = File(filepath, easy=False)
                    if not audio:
                        raise ValueError("无法读取音频信息")

                    # 获取标签对象
                    if ext == "mp3":
                        tags = MP3(filepath).tags
                    elif ext == "flac":
                        tags = FLAC(filepath)
                    elif ext == "m4a":
                        tags = MP4(filepath)
                    else:
                        tags = None

                    # 取标签值参与重复检测
                    length = round(audio.info.length, 2) if hasattr(audio.info, 'length') else 0
                    meta_values = [get_tag_value(ext, tags, t) for t in c_dup_tags]
                    dup_key = (length, tuple(meta_values))
                    duplicates[dup_key].append(filepath)

                    # 比特率检查
                    if audio and hasattr(audio.info, 'bitrate'):
                        bitrate = audio.info.bitrate // 1000
                        if bitrate <= min_bit:
                            status = '低比特率'
                            reason = f"当前: {bitrate}kbps"
                            table.add_row(f"[red]{status}[/]", str(filepath), reason)
                            csv_writer.writerow([status, filepath, reason])

                    # 元数据检查
                    meta_missing = check_metadata(filepath, c_skip_tags)
                    if meta_missing:
                        status = "元数据缺失"
                        reason = "缺少: " + ", ".join(meta_missing)
                        table.add_row(f"[yellow]{status}[/]", str(filepath), reason)
                        csv_writer.writerow([status, filepath, reason])

                except Exception as e:
                    status = '处理失败'
                    print(f"处理文件失败: {filepath}")
                    print(f"异常类型: {type(e).__name__}")
                    print(f"异常内容: {repr(e)}")
                    console.print_exception(show_locals=True)
                    reason = f"{type(e).__name__}: {repr(e)}"
                    table.add_row(f"[magenta]{status}[/]", str(filepath), reason)
                    csv_writer.writerow([status, filepath, reason])
            progress.update(task, advance=1)

    # 判断是否疑似重复
    for key, files in duplicates.items():
        if len(files) > 1:
            status = '疑似重复音频'
            reason = f"时长={key[0]}s, Tags={key[1]}"
            for fl in files:
                table.add_row(f"[bright_black]{status}[/]", str(fl), reason)
                csv_writer.writerow([status, fl, reason])

    c_console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='音频文件质量检查及分割工具')
    parser.add_argument('directory', help='要扫描的目录路径')
    parser.add_argument('--min', type=int, default=2, help='最小音频文件数量阈值 (默认:')
    parser.add_argument('--bit', type=int, default=128, help='最小音频比特率阈值 (默认: 128)')
    parser.add_argument('--skip-tags', default='',
                        help='要跳过检查的元数据，逗号分隔，如: 流派,年份,封面 (支持列表：标题,专辑,艺术家,曲目号,流派,年份)')
    parser.add_argument('--dup-tags', default='标题',
                        help='用于判断重复的元数据，逗号分隔，默认: 标题 (支持列表：标题,专辑,艺术家,曲目号,流派,年份)')
    parser.add_argument('--output', default='results.csv', help='输出CSV文件名 (默认: results.csv)')

    args = parser.parse_args()
    skip_tags = set([t.strip() for t in args.skip_tags.split(',') if t.strip()])
    dup_tags = [t.strip() for t in args.dup_tags.split(',') if t.strip()]

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
        check_audio_files(os.path.abspath(args.directory), args.min, args.bit, skip_tags, dup_tags, writer, console)

    console.print(f"\n扫描完成！结果已保存至 [bold]{args.output}[/]", style="green")
