# album-check

<p align="center">
<img alt="image" src="https://github.com/user-attachments/assets/9892a34e-eb11-43f5-85bc-c9d21b74fae9" />
<br>
  一个用来检测音乐库的小工具
</p>

## Why?

因为本人的音乐库早期并没有进行规范化管理，并且下了很多high loss的音频，导致库中非常的乱

因此写了个小工具来方便进行管理

## 支持功能

（所有功能都支持子文件夹）

- [x] 检测文件夹中的音频比特率
- [x] 检测文件夹中的音频元数据
- [x] 检测文件夹中的音频数量
- [x] 支持检测未分割的音频并进行分割(暂未测试)
- [ ] More functions are under development

## How to use

```bash
git clone https://github.com/misaka10843/album-check.git

cd album-check

pip install -r requirements.txt
```

在安装了依赖之后在项目根目录中即可运行

```bash
(.venv) PS D:\misaka10843\Documents\GitHub\album-check> python main.py -h
usage: main.py [-h] [--min MIN] [--bit BIT] [--split] [--output OUTPUT] directory

音频文件质量检查及分割工具

positional arguments:
  directory        要扫描的目录路径

options:
  -h, --help       show this help message and exit
  --min MIN        最小音频文件数量阈值 (默认:
  --bit BIT        最小音频比特率阈值 (默认: 128)
  --split          自动根据 CUE 分割未分割音频文件
  --output OUTPUT  输出CSV文件名 (默认: results.csv)
```
