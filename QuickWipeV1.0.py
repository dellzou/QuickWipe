#!/usr/bin/env python3
"""
硬盘安全擦除工具
根据硬盘类型自动调整填充率，平衡安全性与速度
支持Windows和Linux系统
"""

import os
import sys
import platform
import subprocess
import argparse
import time
import ctypes
import tempfile
import json
from typing import Tuple, Optional, Dict, List
import math


class DiskWiper:
    def __init__(self):
        self.system = platform.system()
        self.filling_rates = {
            'HDD_SATA': 0.2,  # 机械硬盘+SATA: 20%
            'SSD_SATA': 0.25,  # SATA SSD: 25%
            'SSD_NVMe': 0.3,  # NVMe SSD: 30%
            'UNKNOWN': 0.2  # 未知类型: 20%
        }

    def is_admin(self) -> bool:
        """检查是否具有管理员/root权限"""
        if self.system == "Windows":
            try:
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            except:
                return False
        else:  # Linux/Unix
            return os.geteuid() == 0

    def request_admin_privileges(self) -> bool:
        """请求管理员/root权限（仅在Windows上自动请求UAC提权）"""
        if not self.is_admin():
            if self.system == "Windows":
                print("检测到需要管理员权限，正在请求UAC提权...")
                # 重新以管理员身份运行
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, " ".join(sys.argv), None, 1
                )
                return True  # 原始进程应该退出
            else:  # Linux/Unix
                print("错误: 需要root权限运行此程序")
                print("请使用sudo重新运行: sudo python " + " ".join(sys.argv))
                return False
        return True  # 已经是管理员

    def get_disk_info_linux(self, disk_path: str) -> Tuple[str, str]:
        """
        在Linux系统获取磁盘信息
        返回: (disk_type, interface_type)
        """
        try:
            # 使用smartctl获取硬盘信息
            cmd = f"smartctl -i {disk_path}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            output = result.stdout.lower()

            disk_type = "UNKNOWN"
            interface_type = "UNKNOWN"

            # 检测硬盘类型
            if "solid state" in output or "ssd" in output:
                disk_type = "SSD"
            elif "rotation rate" in output:
                disk_type = "HDD"

            # 检测接口类型
            if "nvme" in output:
                interface_type = "NVMe"
            elif "sata" in output:
                interface_type = "SATA"

            return disk_type, interface_type

        except Exception as e:
            print(f"获取硬盘信息失败: {e}")
            return "UNKNOWN", "UNKNOWN"

    def get_disk_info_windows(self, disk_number: int) -> Tuple[str, str]:
        """
        在Windows系统获取磁盘信息
        返回: (disk_type, interface_type)
        """
        try:
            import wmi
            c = wmi.WMI()

            # 获取磁盘信息
            for disk in c.Win32_DiskDrive():
                if disk.Index == disk_number:
                    model = disk.Model.lower()
                    interface = disk.InterfaceType.lower() if disk.InterfaceType else ""

                    disk_type = "UNKNOWN"
                    interface_type = "UNKNOWN"

                    # 检测硬盘类型
                    if "ssd" in model or "solid state" in model:
                        disk_type = "SSD"
                    elif "hdd" in model or "hard disk" in model or disk.MediaType == "External hard disk media":
                        disk_type = "HDD"

                    # 检测接口类型
                    if "nvme" in model or "nvme" in interface:
                        interface_type = "NVMe"
                    elif "sata" in interface or "ata" in interface:
                        interface_type = "SATA"
                    elif "scsi" in interface:
                        interface_type = "SCSI"

                    return disk_type, interface_type

            return "UNKNOWN", "UNKNOWN"

        except Exception as e:
            print(f"获取硬盘信息失败: {e}")
            return "UNKNOWN", "UNKNOWN"

    def get_disk_info(self, disk_identifier: str) -> Tuple[str, str, str]:
        """
        获取磁盘信息并返回建议的填充率
        返回: (disk_type, interface_type, rate_key)
        """
        if self.system == "Linux":
            disk_type, interface_type = self.get_disk_info_linux(disk_identifier)
        elif self.system == "Windows":
            # Windows传入的是磁盘编号
            disk_number = int(disk_identifier)
            disk_type, interface_type = self.get_disk_info_windows(disk_number)
        else:
            print(f"不支持的操作系统: {self.system}")
            return "UNKNOWN", "UNKNOWN", "UNKNOWN"

        # 确定填充率键
        if disk_type == "HDD" and interface_type == "SATA":
            rate_key = "HDD_SATA"
        elif disk_type == "SSD" and interface_type == "SATA":
            rate_key = "SSD_SATA"
        elif disk_type == "SSD" and interface_type == "NVMe":
            rate_key = "SSD_NVMe"
        else:
            rate_key = "UNKNOWN"

        return disk_type, interface_type, rate_key

    def calculate_fill_size(self, disk_size_gb: float, fill_rate: float) -> int:
        """计算需要填充的大小（字节）"""
        # 转换为字节
        disk_size_bytes = int(disk_size_gb * 1024 * 1024 * 1024)
        fill_bytes = int(disk_size_bytes * fill_rate)
        return fill_bytes

    def wipe_disk_linux(self, disk_path: str, fill_rate: float, pattern: int = 0) -> bool:
        """在Linux系统上擦除磁盘"""
        try:
            # 获取磁盘大小
            cmd = f"blockdev --getsize64 {disk_path}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            disk_size_bytes = int(result.stdout.strip())

            # 计算填充大小
            fill_bytes = int(disk_size_bytes * fill_rate)

            print(f"开始擦除磁盘 {disk_path}...")
            print(f"磁盘大小: {disk_size_bytes / (1024 ** 3):.2f} GB")
            print(f"填充率: {fill_rate * 100:.1f}%")
            print(f"实际填充: {fill_bytes / (1024 ** 3):.2f} GB")

            # 创建填充数据
            pattern_byte = b'\x00' if pattern == 0 else b'\xFF'

            # 使用dd命令进行填充
            block_size = 1024 * 1024  # 1MB块
            blocks_to_write = fill_bytes // block_size

            print(f"使用模式: {'0x00' if pattern == 0 else '0xFF'}")
            print(f"块大小: {block_size / 1024:.0f}KB, 总块数: {blocks_to_write}")
            print("正在擦除，请稍候...")

            # 分块写入，显示进度
            with open(disk_path, 'wb') as f:
                for i in range(blocks_to_write):
                    f.write(pattern_byte * block_size)

                    # 显示进度
                    if i % 100 == 0:
                        progress = (i + 1) / blocks_to_write * 100
                        print(f"进度: {progress:.1f}%", end='\r')

            print(f"\n磁盘 {disk_path} 擦除完成!")
            return True

        except Exception as e:
            print(f"擦除失败: {e}")
            return False

    def wipe_disk_windows(self, disk_number: int, fill_rate: float, pattern: int = 0) -> bool:
        """
        在Windows系统上擦除磁盘
        使用系统命令和安全API实现
        """
        try:
            import wmi
            c = wmi.WMI()

            # 获取磁盘信息
            target_disk = None
            for disk in c.Win32_DiskDrive():
                if disk.Index == disk_number:
                    target_disk = disk
                    break

            if not target_disk:
                print(f"未找到磁盘编号: {disk_number}")
                return False

            disk_size_bytes = int(target_disk.Size)
            disk_size_gb = disk_size_bytes / (1024 ** 3)

            # 计算填充大小
            fill_bytes = int(disk_size_bytes * fill_rate)
            fill_gb = fill_bytes / (1024 ** 3)

            print(f"开始擦除磁盘 {target_disk.Caption}...")
            print(f"磁盘大小: {disk_size_gb:.2f} GB")
            print(f"填充率: {fill_rate * 100:.1f}%")
            print(f"实际填充: {fill_gb:.2f} GB")
            print(f"使用模式: {'0x00' if pattern == 0 else '0xFF'}")

            # 获取磁盘分区信息
            partitions = self.get_disk_partitions_windows(disk_number)

            if not partitions:
                print("警告: 该磁盘没有分区，将创建临时分区进行擦除")
                return self.wipe_unallocated_disk_windows(disk_number, fill_rate, pattern)

            # 如果有分区，对每个分区进行擦除
            success = True
            for partition in partitions:
                print(f"\n处理分区: {partition['letter']} ({partition['size_gb']:.2f} GB)")

                # 计算该分区的填充大小
                partition_fill_bytes = int(partition['size_bytes'] * fill_rate)

                # 使用不同的擦除方法
                method = input(f"选择擦除方法 (1=cipher安全擦除, 2=format格式化, 3=创建大文件填充): ")

                if method == "1":
                    # 使用cipher命令进行安全擦除
                    if not self.wipe_with_cipher(partition['letter'], pattern):
                        success = False

                elif method == "2":
                    # 使用format命令格式化
                    if not self.wipe_with_format(partition['letter'], pattern):
                        success = False

                elif method == "3":
                    # 创建大文件填充
                    if not self.wipe_with_file_fill(partition['letter'], partition_fill_bytes, pattern):
                        success = False
                else:
                    print("无效选择，跳过此分区")

            return success

        except Exception as e:
            print(f"擦除失败: {e}")
            return False

    def get_disk_partitions_windows(self, disk_number: int) -> List[Dict]:
        """获取Windows磁盘的分区信息"""
        try:
            import wmi
            c = wmi.WMI()

            partitions = []

            # 查找与磁盘关联的分区
            for partition in c.Win32_DiskPartition():
                if partition.DiskIndex == disk_number:
                    # 查找关联的逻辑磁盘
                    for logical_disk in c.Win32_LogicalDiskToPartition():
                        if logical_disk.Antecedent == partition.AntiDependence:
                            disk_id = logical_disk.Dependent.split('"')[1]

                            # 获取磁盘信息
                            for disk in c.Win32_LogicalDisk(DeviceID=disk_id):
                                partitions.append({
                                    'letter': disk.DeviceID,
                                    'size_bytes': int(disk.Size),
                                    'size_gb': int(disk.Size) / (1024 ** 3),
                                    'filesystem': disk.FileSystem,
                                    'free_space': int(disk.FreeSpace)
                                })

            return partitions

        except Exception as e:
            print(f"获取分区信息失败: {e}")
            return []

    def wipe_unallocated_disk_windows(self, disk_number: int, fill_rate: float, pattern: int) -> bool:
        """擦除未分配的Windows磁盘"""
        try:
            print("\n创建临时分区进行擦除...")

            # 创建临时脚本文件
            script_content = f"""
select disk {disk_number}
clean
create partition primary
format fs=ntfs quick
assign letter=X
exit
"""

            script_path = os.path.join(tempfile.gettempdir(), f"diskpart_script_{disk_number}.txt")
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)

            # 执行diskpart脚本
            print("正在创建临时分区...")
            result = subprocess.run(f'diskpart /s "{script_path}"', shell=True, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"创建临时分区失败: {result.stderr}")
                return False

            print("临时分区创建成功 (X:)")

            # 使用cipher命令擦除
            print("正在使用cipher命令进行安全擦除...")
            cipher_result = subprocess.run('cipher /w:X:', shell=True, capture_output=True, text=True)

            if cipher_result.returncode != 0:
                print(f"cipher擦除失败: {cipher_result.stderr}")

            # 清理临时分区
            print("清理临时分区...")
            clean_script = f"""
select disk {disk_number}
select partition 1
remove
clean
exit
"""

            clean_script_path = os.path.join(tempfile.gettempdir(), f"diskpart_clean_{disk_number}.txt")
            with open(clean_script_path, 'w', encoding='utf-8') as f:
                f.write(clean_script)

            subprocess.run(f'diskpart /s "{clean_script_path}"', shell=True, capture_output=True, text=True)

            # 删除临时文件
            os.remove(script_path)
            os.remove(clean_script_path)

            print("磁盘擦除完成!")
            return True

        except Exception as e:
            print(f"擦除未分配磁盘失败: {e}")
            return False

    def wipe_with_cipher(self, drive_letter: str, pattern: int) -> bool:
        """使用cipher命令进行安全擦除"""
        try:
            print(f"使用cipher命令擦除驱动器 {drive_letter}...")
            print("注意: cipher会执行三次覆盖 (0x00, 0xFF, 随机数)")

            result = subprocess.run(f'cipher /w:{drive_letter}', shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"驱动器 {drive_letter} cipher擦除完成")
                return True
            else:
                print(f"cipher擦除失败: {result.stderr}")
                return False

        except Exception as e:
            print(f"cipher擦除失败: {e}")
            return False

    def wipe_with_format(self, drive_letter: str, pattern: int) -> bool:
        """使用format命令格式化驱动器"""
        try:
            print(f"使用format命令格式化驱动器 {drive_letter}...")

            # 根据pattern选择不同的format选项
            if pattern == 0:
                # 填充0
                print("使用单次0填充格式化")
                result = subprocess.run(f'format {drive_letter} /FS:NTFS /Q /P:1', shell=True,
                                        capture_output=True, text=True, input='\n')
            else:
                # 填充1 (通过多次格式化实现)
                print("使用三次覆盖格式化 (包含1的填充)")
                result = subprocess.run(f'format {drive_letter} /FS:NTFS /Q /P:3', shell=True,
                                        capture_output=True, text=True, input='\n')

            if result.returncode == 0:
                print(f"驱动器 {drive_letter} 格式化完成")
                return True
            else:
                print(f"格式化失败: {result.stderr}")
                return False

        except Exception as e:
            print(f"格式化失败: {e}")
            return False

    def wipe_with_file_fill(self, drive_letter: str, fill_bytes: int, pattern: int) -> bool:
        """通过创建大文件填充驱动器"""
        try:
            print(f"通过创建大文件填充驱动器 {drive_letter}...")
            print(f"填充大小: {fill_bytes / (1024 ** 3):.2f} GB")

            # 计算可以创建的文件数量和大小
            max_file_size = 1024 * 1024 * 1024  # 1GB
            num_files = math.ceil(fill_bytes / max_file_size)

            pattern_byte = b'\x00' if pattern == 0 else b'\xFF'

            for i in range(num_files):
                file_size = min(max_file_size, fill_bytes - i * max_file_size)
                if file_size <= 0:
                    break

                filename = os.path.join(drive_letter, f"wipe_{i:04d}.tmp")
                print(f"创建文件 {i + 1}/{num_files}: {filename} ({file_size / (1024 ** 3):.2f} GB)")

                with open(filename, 'wb') as f:
                    # 分块写入
                    block_size = 1024 * 1024  # 1MB
                    blocks = file_size // block_size

                    for block in range(blocks):
                        f.write(pattern_byte * block_size)

                        if block % 100 == 0:
                            progress = (block + 1) / blocks * 100
                            print(f"  进度: {progress:.1f}%", end='\r')

                print(f"  文件 {i + 1} 创建完成")

            # 删除临时文件
            print("删除临时文件...")
            for i in range(num_files):
                filename = os.path.join(drive_letter, f"wipe_{i:04d}.tmp")
                if os.path.exists(filename):
                    os.remove(filename)

            print(f"驱动器 {drive_letter} 文件填充完成")
            return True

        except Exception as e:
            print(f"文件填充失败: {e}")
            return False

    def secure_erase_ssd_windows(self, disk_number: int) -> bool:
        """对SSD执行安全擦除 (ATA SECURITY ERASE UNIT)"""
        try:
            print("尝试执行SSD安全擦除 (ATA SECURITY ERASE UNIT)...")
            print("注意: 这需要硬盘支持ATA安全擦除功能")

            # 使用第三方工具或Windows API
            # 这里只是示例，实际需要调用相应的工具
            print("SSD安全擦除功能需要专用工具:")
            print("1. 厂商提供的工具 (如 Samsung Magician, Intel SSD Toolbox)")
            print("2. Parted Magic Live CD")
            print("3. hdparm (在Linux环境下)")

            confirm = input("是否继续尝试通过WMI发送ATA命令? (y/N): ")
            if confirm.lower() != 'y':
                return False

            # 尝试通过WMI发送ATA命令
            try:
                import wmi
                c = wmi.WMI(namespace="root\\wmi")

                # 获取ATA端口信息
                print("正在查找ATA端口...")
                # 这里需要具体的WMI调用，实际实现会更复杂

                print("由于Windows限制，直接发送ATA命令比较复杂")
                print("建议使用Linux环境或厂商工具进行SSD安全擦除")

            except Exception as e:
                print(f"WMI调用失败: {e}")

            return False

        except Exception as e:
            print(f"SSD安全擦除失败: {e}")
            return False

    def list_disks(self):
        """列出可用磁盘"""
        if self.system == "Linux":
            self.list_disks_linux()
        elif self.system == "Windows":
            self.list_disks_windows()
        else:
            print(f"不支持的操作系统: {self.system}")

    def list_disks_linux(self):
        """在Linux上列出磁盘"""
        try:
            cmd = "lsblk -o NAME,SIZE,TYPE,MODEL -d | grep -E '^(sd|nvme|vd)'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            print("可用磁盘:")
            print(result.stdout)

            cmd2 = "ls /dev/sd? /dev/nvme?n1 2>/dev/null"
            result2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True)
            if result2.stdout:
                print("\n可用磁盘设备:")
                print(result2.stdout)

        except Exception as e:
            print(f"列出磁盘失败: {e}")

    def list_disks_windows(self):
        """在Windows上列出磁盘"""
        try:
            import wmi
            c = wmi.WMI()

            print("可用磁盘:")
            print("-" * 80)
            print(f"{'编号':<5} {'型号':<40} {'大小(GB)':<10} {'接口':<10} {'类型':<10}")
            print("-" * 80)

            for disk in c.Win32_DiskDrive():
                size_gb = int(disk.Size) / (1024 ** 3)
                interface = disk.InterfaceType if disk.InterfaceType else "未知"

                # 检测磁盘类型
                model = disk.Model.lower()
                if "ssd" in model or "solid state" in model:
                    disk_type = "SSD"
                else:
                    disk_type = "HDD"

                print(f"{disk.Index:<5} {disk.Model:<40} {size_gb:<10.1f} {interface:<10} {disk_type:<10}")

        except Exception as e:
            print(f"列出磁盘失败: {e}")


def show_interactive_menu():
    """显示交互式菜单"""
    print("\n" + "=" * 60)
    print("              硬盘安全擦除工具 - 交互式菜单")
    print("=" * 60)
    print("1. 列出所有磁盘")
    print("2. 擦除磁盘")
    print("3. 显示命令行参数用法")
    print("4. SSD安全擦除 (仅Windows)")
    print("5. 退出")
    print("=" * 60)

    choice = input("\n请选择操作 (1-5): ").strip()
    return choice


def interactive_mode():
    """交互式模式"""
    wiper = DiskWiper()

    while True:
        choice = show_interactive_menu()

        if choice == "1":
            print("\n正在列出所有磁盘...")
            wiper.list_disks()
            input("\n按Enter键继续...")

        elif choice == "2":
            print("\n" + "-" * 40)
            print("擦除磁盘")
            print("-" * 40)

            # 先列出磁盘
            wiper.list_disks()
            print()

            # 获取磁盘标识符
            if platform.system() == "Linux":
                disk_input = input("请输入要擦除的磁盘设备路径 (如 /dev/sda): ").strip()
            else:  # Windows
                disk_input = input("请输入磁盘编号 (如 0): ").strip()

            if not disk_input:
                print("操作已取消")
                continue

            # 获取磁盘信息
            print("\n正在分析磁盘信息...")
            try:
                disk_type, interface_type, rate_key = wiper.get_disk_info(disk_input)

                print(f"\n磁盘信息:")
                print(f"  类型: {disk_type}")
                print(f"  接口: {interface_type}")

                # 询问是否手动指定填充率
                manual_rate = input("\n是否手动指定填充率? (y/N, 默认使用自动选择): ").strip().lower()
                if manual_rate == 'y':
                    try:
                        rate_input = input("请输入填充率 (0.0-1.0, 如 0.3 表示 30%): ").strip()
                        fill_rate = float(rate_input)
                        if fill_rate < 0 or fill_rate > 1:
                            print("错误: 填充率必须在0.0到1.0之间")
                            continue
                        print(f"  填充率: 手动指定 {fill_rate * 100:.1f}%")
                    except ValueError:
                        print("错误: 请输入有效的数字")
                        continue
                else:
                    fill_rate = wiper.filling_rates[rate_key]
                    print(f"  填充率: 自动选择 {fill_rate * 100:.1f}% ({rate_key})")

                # 选择填充模式
                pattern_input = input("\n选择填充模式 (0=填充0, 1=填充1, 默认0): ").strip()
                pattern = 0
                if pattern_input == "1":
                    pattern = 1
                print(f"使用模式: {'0x00' if pattern == 0 else '0xFF'}")

                # 最终确认
                print(f"\n即将擦除磁盘: {disk_input}")
                confirm = input("确认继续? (y/N): ").strip().lower()
                if confirm != 'y':
                    print("操作已取消")
                    continue

                # 执行擦除
                if platform.system() == "Linux":
                    success = wiper.wipe_disk_linux(disk_input, fill_rate, pattern)
                else:  # Windows
                    success = wiper.wipe_disk_windows(int(disk_input), fill_rate, pattern)

                if success:
                    print("操作完成!")
                else:
                    print("操作失败!")

            except Exception as e:
                print(f"操作出错: {e}")

            input("\n按Enter键返回主菜单...")

        elif choice == "3":
            print("\n" + "-" * 40)
            print("命令行参数用法:")
            print("-" * 40)
            print("--list                   列出所有磁盘")
            print("--disk DISK_ID           指定要擦除的磁盘")
            print("--rate FILL_RATE         手动指定填充率(0.0-1.0)")
            print("--pattern 0/1            填充模式: 0=填充0, 1=填充1")
            print("--interactive, -i        进入交互式模式")
            print()
            print("用法示例:")
            if platform.system() == "Linux":
                print("  sudo python disk_wiper.py --disk /dev/sda")
                print("  sudo python disk_wiper.py --list")
            else:
                print("  python disk_wiper.py --disk 0")
                print("  python disk_wiper.py --list")
            input("\n按Enter键返回主菜单...")

        elif choice == "4" and platform.system() == "Windows":
            print("\n" + "-" * 40)
            print("SSD安全擦除 (ATA SECURITY ERASE UNIT)")
            print("-" * 40)

            wiper.list_disks()
            print()

            disk_input = input("请输入SSD磁盘编号: ").strip()
            if not disk_input:
                print("操作已取消")
                continue

            print("\n警告: SSD安全擦除会永久删除所有数据!")
            print("此操作不可恢复!")
            confirm = input("确认继续? (y/N): ").strip().lower()
            if confirm != 'y':
                print("操作已取消")
                continue

            success = wiper.secure_erase_ssd_windows(int(disk_input))
            if success:
                print("SSD安全擦除完成!")
            else:
                print("SSD安全擦除失败或取消")

            input("\n按Enter键返回主菜单...")

        elif choice == "5" or (choice == "4" and platform.system() != "Windows"):
            if choice == "4":
                print("SSD安全擦除功能仅在Windows上可用")
            print("\n感谢使用，再见!")
            break

        else:
            print("\n无效选择，请重新输入")


def main():
    parser = argparse.ArgumentParser(description='硬盘安全擦除工具')
    parser.add_argument('--disk', help='磁盘标识符(Linux: /dev/sdX, Windows: 磁盘编号)')
    parser.add_argument('--rate', type=float, help='手动指定填充率(0.0-1.0)')
    parser.add_argument('--pattern', type=int, choices=[0, 1], default=0,
                        help='填充模式: 0=填充0, 1=填充1')
    parser.add_argument('--list', action='store_true', help='列出所有磁盘')
    parser.add_argument('--interactive', '-i', action='store_true', help='进入交互式模式')

    args = parser.parse_args()

    wiper = DiskWiper()

    # 检查权限，如果需要则请求提权
    if not wiper.request_admin_privileges():
        sys.exit(1)

    # 如果指定了--interactive参数或没有任何参数，进入交互式模式
    if args.interactive or (not args.disk and not args.rate and not args.pattern and not args.list):
        interactive_mode()
        return

    # 否则使用命令行参数模式
    if args.list:
        wiper.list_disks()
        return

    if not args.disk:
        print("错误: 请指定要擦除的磁盘")
        print("用法示例:")
        if platform.system() == "Linux":
            print("  sudo python disk_wiper.py --disk /dev/sda")
        else:
            print("  python disk_wiper.py --disk 0")
        print("\n使用 --list 查看所有磁盘")
        print("或使用 --interactive 进入交互式模式")
        return

    # 获取磁盘信息
    print("正在分析磁盘信息...")
    disk_type, interface_type, rate_key = wiper.get_disk_info(args.disk)

    print(f"\n磁盘信息:")
    print(f"  类型: {disk_type}")
    print(f"  接口: {interface_type}")

    # 确定填充率
    if args.rate is not None:
        fill_rate = args.rate
        print(f"  填充率: 手动指定 {fill_rate * 100:.1f}%")
    else:
        fill_rate = wiper.filling_rates[rate_key]
        print(f"  填充率: 自动选择 {fill_rate * 100:.1f}% ({rate_key})")

    # 确认操作
    print(f"\n即将使用模式 {'0x00' if args.pattern == 0 else '0xFF'} 擦除磁盘")
    confirm = input("确认继续? (y/N): ")
    if confirm.lower() != 'y':
        print("操作已取消")
        return

    # 执行擦除
    if platform.system() == "Linux":
        success = wiper.wipe_disk_linux(args.disk, fill_rate, args.pattern)
    elif platform.system() == "Windows":
        success = wiper.wipe_disk_windows(int(args.disk), fill_rate, args.pattern)
    else:
        print(f"不支持的操作系统: {platform.system()}")
        success = False

    if success:
        print("操作完成!")
    else:
        print("操作失败!")


if __name__ == "__main__":
    main()
