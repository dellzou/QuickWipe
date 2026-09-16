# QuickWipe - 智能硬盘安全擦除工具

## 项目简介
QuickWipe 是一个智能的硬盘安全擦除工具，能够根据硬盘类型（HDD/SSD）和接口（SATA/NVMe）自动优化填充率，在保证数据安全性的同时显著提升擦除速度。支持 Windows 和 Linux 双平台。

## 核心特性
- **智能填充率调整**：自动检测硬盘类型和接口，为不同硬件配置最优填充率
- **跨平台支持**：完全兼容 Windows 和 Linux 系统
- **平衡安全与速度**：通过部分填充（20%-30%）而非全盘填充，大幅减少等待时间
- **灵活配置**：支持自动识别和手动指定两种填充率模式
- **安全确认机制**：操作前双重确认，防止误操作
- **实时进度显示**：擦除过程中显示详细进度信息
- **演练模式**：只读磁盘信息并模拟流程，不写入任何数据，用于先确认工具识别得对不对

## 技术原理

### 硬件识别方式
工具通过 WMI 的 `MSFT_PhysicalDisk` 类读取 `MediaType`（介质类型）与 `BusType`（物理接口）的枚举值来判断硬件特性：

| 属性 | 取值 |
|------|------|
| `MediaType` | 3 = HDD，4 = SSD，5 = SCM |
| `BusType` | 7 = USB，8 = RAID，11 = SATA，17 = NVMe |

`DeviceId` 与 `Win32_DiskDrive.Index` 一一对应，因此磁盘编号在两种查询下保持一致。

**为什么不用型号字符串 + `Win32_DiskDrive.InterfaceType`**：

- 现代硬盘型号名（如 `KBG5AZNV512G`、`ZHITAI Ti600`、`ST4000DM004`）普遍不含 `ssd` / `hdd` / `nvme` 等关键词，按字符串匹配无法命中
- `Win32_DiskDrive.InterfaceType` 返回的是**驱动栈形态**而非物理接口 —— NVMe 设备会报 `SCSI`，SATA 设备会报 `IDE`

工具保留了型号匹配作为回退路径，供无法查询 `MSFT_PhysicalDisk` 的旧系统使用。

### 自动填充率策略
工具根据硬盘硬件特性自动选择最优填充率：

| 硬盘类型 | 接口类型 | 建议填充率 | 说明 |
|---------|---------|-----------|------|
| 机械硬盘 (HDD) | SATA | 20% | 机械硬盘速度较慢，20%填充在安全性和速度间取得平衡 |
| 固态硬盘 (SSD) | SATA | 25% | SATA SSD速度中等，适当提高填充率增强安全性 |
| 固态硬盘 (SSD) | NVMe | 30% | NVMe SSD速度极快，可承受更高填充率 |
| 未知类型 | 未知 | 20% | 保守策略，确保基本安全性 |

### 数据安全机制
1. **部分覆盖策略**：研究表明，对现代存储设备的部分随机覆盖已能有效防止数据恢复
2. **两种填充模式**：支持 0x00（全零）和 0xFF（全一）两种填充模式
3. **权限验证**：运行时自动检查管理员/root权限，确保操作合法性

## 系统要求
- **操作系统**：Windows 10/11 或 Linux（Ubuntu/Debian/CentOS等）
- **Python版本**：Python 3.6 或更高版本
- **权限要求**：管理员（Windows）或 root（Linux）权限

## 安装与依赖

### Windows 系统

需要安装 `wmi` 及其底层依赖 `pywin32`：

```bash
pip install pywin32 wmi
```

> `wmi` 包依赖 `pywin32`，但 pip 不一定会自动一并装上。如果运行时报
> `No module named 'pywintypes'`，说明缺的是 `pywin32`（报错的模块名不是包名），
> 单独补装即可：
>
> ```bash
> pip install --ignore-installed pywin32
> ```

**权限说明**：本工具需要管理员权限 —— 既要读写物理磁盘，`win32com` 也需要写 COM 类型库缓存。请以「以管理员身份运行」启动终端。

### Linux 系统

需要 root 权限，无额外 Python 依赖。

## 使用方法

### 交互式模式（推荐）

```bash
python QuickWipeV2.0.py -i
```

菜单提供四个操作：列出所有磁盘 / 擦除磁盘 / 查看命令行参数 / SSD 安全擦除。

### 命令行模式

```bash
python QuickWipeV2.0.py --list                    # 列出所有磁盘
python QuickWipeV2.0.py --disk 0                  # 擦除磁盘 0（自动选择填充率）
python QuickWipeV2.0.py --disk 0 --rate 0.25      # 手动指定填充率 25%
python QuickWipeV2.0.py --disk 0 --pattern 1      # 使用 0xFF 填充
```

| 参数 | 说明 |
|------|------|
| `--list` | 列出所有磁盘 |
| `--disk DISK_ID` | 指定要擦除的磁盘（Linux: `/dev/sdX`，Windows: 磁盘编号）|
| `--rate FILL_RATE` | 手动指定填充率（0.0-1.0）|
| `--pattern 0/1` | 填充模式：0 = 填充 0x00，1 = 填充 0xFF |
| `--interactive, -i` | 进入交互式模式 |
| `--simulate` | 演练模式：只读磁盘信息 + 模拟进度，不写入任何数据 |

### 演练模式

想在动手前先看看工具怎么工作、或确认它识别的硬件信息是否正确：

```bash
python QuickWipeV2.0.py --simulate --list         # 只列出磁盘，不需要管理员权限
python QuickWipeV2.0.py --simulate --disk 0       # 走完整流程，但不写入
```

演练模式会**真实读取**磁盘信息、**真实计算**填充率与填充量，并以与真实擦除一致的格式输出进度，**但不会打开任何物理设备、不会写入任何数据**，因此也不需要管理员权限。

**建议在任何一次真实擦除之前，先用它核对一遍目标磁盘。**

## 常见问题

**Q：报 `No module named 'pywintypes'`？**
缺的是 `pywin32`。执行 `pip install --ignore-installed pywin32`。

**Q：报 `PermissionError: [WinError 5] 拒绝访问。: 'C:\Windows\gen_py'`？**
`win32com` 默认把 COM 类型库缓存写到系统目录，普通权限建不了。本工具启动时会自动把缓存重定向到用户临时目录，正常情况下不会遇到；若仍然出现，请以管理员身份运行。

**Q：列表里某块盘显示 `类型: UNKNOWN`？**
说明该设备的 WMI 没有上报介质类型（部分 USB 设备会这样）。工具会自动回退到保守策略（20%），功能不受影响。

**Q：怎么确认选中的是不是我要擦的那块盘？**
先跑 `python QuickWipeV2.0.py --simulate --list`（只读、免管理员），逐项核对**型号、容量、接口**三列 —— 可移动设备会明确标为 `USB`。

## 相关阅读

这个工具的设计思路、以及硬盘擦除的实践记录，写在作者的博客上：

- **[硬盘安全擦除：为什么全盘填充是浪费时间](https://xiaozou123.cn/secure-disk-erase-why-full-disk-fill-wastes-time/)** —— 本工具的配套文章，讲清该填多少、为什么
- [SSD 知识：企业级与消费级的区别？](https://xiaozou123.cn/ssd-knowledge-what-is-the-difference-between-enterprise-level-and-consumer-level/)
- [XiaoZou123 技术博客 · 系统与硬件方向](https://xiaozou123.cn/digital-disassembly/)

## 免责声明

**本工具会永久销毁目标设备上的全部数据，且不可恢复。** 使用前请务必：

1. 核对目标磁盘编号 —— 工具会打印型号与容量，请逐项确认
2. 断开不需要擦除的可移动存储设备，减少认错编号的可能
3. **不要对承载当前操作系统的磁盘执行擦除**

作者不对因误用本工具造成的任何数据丢失承担责任。
