#!/usr/bin/env python3
import os
import subprocess
import re
import time
import sys
from bs4 import BeautifulSoup
import urllib.parse

# 定义颜色
RED = '\033[0;31m'
NC = '\033[0m'
GREEN = '\033[38;5;154m'
YELLOW = '\033[93m'
BLUE = '\033[96m'

# 定义脚本版本
SCRIPT_VERSION = "1.2"

def is_x86_64_router():
    """判断是否为x86软路由"""
    return os.uname().machine == "x86_64"

def download_common_shell():
    """下载 common.sh 脚本"""
    if not os.path.exists("common.sh"):
        print(f"{YELLOW}正在下载 common.sh...{NC}")
        try:
             cmd = ["wget", "-O", "common.sh", "http://10.10.10.13:3000/yaojiwei520/adb/raw/branch/main/common.sh"]
             subprocess.check_call(cmd)
             subprocess.check_call(["chmod", "+x", "common.sh"])
             subprocess.check_call(["source", "common.sh"], shell=True)
             print(f"{GREEN}common.sh 下载和执行成功{NC}")
        except subprocess.CalledProcessError:
            print(f"{RED}下载 common.sh 失败,请检查网络{NC}")
            sys.exit(1)


def is_integer(value):
    """检查输入是否为整数"""
    return re.match(r"^-?[0-9]+$", value) is not None

def check_adb_installed():
    """判断adb是否安装"""
    try:
        subprocess.run(["which", "adb"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def check_adb_connected():
    """判断adb是否连接成功"""
    if not check_adb_installed():
        return False
    try:
        output = subprocess.check_output(["adb", "devices"]).decode()
        devices = [line.split()[1] for line in output.strip().split('\n')[1:] if len(line.split()) > 1]
        return any("device" in dev for dev in devices)
    except subprocess.CalledProcessError:
        return False


def install_adb():
    """安装adb工具"""
    print(f"{BLUE}绝大多数软路由自带ADB 只有少数OpenWrt硬路由才需要安装ADB{NC}")
    if not check_adb_installed():
        print(f"{YELLOW}正在尝试安装adb，需要管理员权限...{NC}")
        print(f"{YELLOW}请注意,需要输入sudo密码(如果需要)...{NC}")
        try:
            subprocess.check_call(["sudo", "apt", "update"])
            subprocess.check_call(["sudo", "apt", "install", "-y", "adb"])
            print(f"{GREEN}adb 安装成功!{NC}")
        except subprocess.CalledProcessError:
            print(f"{RED}adb 安装失败,请检查日志以获取更多信息。{NC}")
            return 1
    else:
        print(f"{YELLOW}您的系统已经安装了ADB工具{NC}")
    return 0


def connect_adb():
    """连接adb"""
    if install_adb() != 0:
        return 1
    try:
        gateway_ip = subprocess.check_output(["ip", "route", "get", "1"]).decode().split()[6]
    except subprocess.CalledProcessError:
        gateway_ip = None

    if not gateway_ip:
        ip = input(f"{RED}无法自动获取网关IP地址，请手动输入电视盒子的完整IP地址：{NC}")
    else:
        gateway_prefix = ".".join(gateway_ip.split('.')[:3]) + "."
        end_number = input(f"{YELLOW}请输入电视盒子的ip地址({NC}{BLUE}{gateway_prefix}{NC}{YELLOW})的最后一段数字{NC}")
        if not is_integer(end_number):
           print(f"{RED}错误: 请输入整数。{NC}")
           return 1
        ip = f"{gateway_prefix}{end_number}"

    subprocess.run(["adb", "disconnect"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"{BLUE}首次使用,盒子上可能会提示授权弹框,给您半分钟时间来操作...【允许】{NC}")
    subprocess.run(["adb", "connect", ip])

    i = 0
    while i < 30:
        i += 1
        print(f"{YELLOW}第{i}次尝试连接ADB,请在设备上点击【允许】按钮...{NC}")
        try:
            output = subprocess.check_output(["adb", "devices"]).decode()
            if any(f"{ip}:5555" in line and "device" in line for line in output.strip().split('\n')[1:] if len(line.split()) > 1):
                print(f"{GREEN}ADB 已经连接成功啦,你可以放心操作了{NC}")
                return 0
        except subprocess.CalledProcessError:
            pass
        time.sleep(1)

    print(f"{RED}连接超时,或者您点击了【取消】,请确认电视盒子的IP地址是否正确。如果问题持续存在,请检查设备的USB调试设置是否正确并重新连接adb{NC}")
    return 1


def disconnect_adb():
    """断开adb连接"""
    if check_adb_installed():
        subprocess.run(["adb", "disconnect"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("ADB 已经断开")
    else:
        print(f"{YELLOW}您还没有安装ADB{NC}")


def get_apk_list(url):
    """获取目录下的 APK 文件列表"""
    print(f"Debug: url='{url}'")
    try:
        curl_output = subprocess.check_output(["curl", "-s", url]).decode()
        soup = BeautifulSoup(curl_output, 'html.parser')
        apk_files = []
        
        base_raw_url = url.replace("/src/", "/raw/") # 替换成 raw 路径, 用于拼接下载链接
        for a_tag in soup.find_all('a', class_='muted', href=True):
            href = a_tag['href']
            if href.endswith('.apk'):
                 apk_files.append(f"{base_raw_url}{os.path.basename(href)}") # 构建下载链接
        if not apk_files:
           print(f"{RED}错误: 未找到任何 .apk 文件，请检查 URL: {url} 或网页结构。{NC}")
           return 1, None
        return 0, apk_files
    except subprocess.CalledProcessError as e:
        print(f"{RED}获取 APK 文件列表失败, 请检查网络或 URL 是否正确: {url}{NC}")
        print(f"{RED}curl 命令错误信息: {e.output.decode()}{NC}")
        return 1, None
    except Exception as e:
        print(f"{RED}解析 HTML 出错: {e}{NC}")
        return 1, None


def select_apk_version(url, apk_files):
    """选择 APK 版本"""

    if not apk_files:
        print(f"{RED}未找到任何APK文件,请检查URL是否正确或版本列表为空。{NC}")
        return None

    num_apks = len(apk_files)

    print(f"{YELLOW}请选择要安装的 APK 版本 (输入 q 返回主菜单):{NC}")
    print("---------------------------------------------")
    for i, apk in enumerate(apk_files):
        print(f"{BLUE}{i+1}. {os.path.basename(apk)}{NC}")
    print("---------------------------------------------")

    apk_choice = input("请输入版本编号: ")
    if apk_choice == "q":
        return None

    if not is_integer(apk_choice) or not (1 <= int(apk_choice) <= num_apks):
        print(f"{RED}无效选择，请重新选择或输入 q 返回主菜单。{NC}")
        return None

    selected_apk = apk_files[int(apk_choice) - 1]
    return selected_apk


def install_apk(apk_download_url, package_name, message=""):
    """安装apk"""
    filename = os.path.basename(apk_download_url)
    if message:
       print(f"{BLUE}{message}{NC}")
    print(f"{YELLOW}正在下载:{apk_download_url}{NC}")
    try:
      subprocess.check_call(["wget", "-O", f"/tmp/{filename}", apk_download_url])
    except subprocess.CalledProcessError:
        print(f"{RED}下载APK失败,请检查网络或URL: {apk_download_url}{NC}")
        return 1

    if check_adb_connected():
        subprocess.run(["adb", "uninstall", package_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"{GREEN}正在推送和安装apk,请耐心等待...{NC}")
        print(f"{BLUE}", end='')
        for _ in range(3):
            print("..", end='', flush=True)
            time.sleep(1)
        print(f"{NC}\n", end='')
        install_result = subprocess.run(["adb", "install", "-r", f"/tmp/{filename}"], capture_output=True, text=True)
        if "Success" in install_result.stdout:
            print(f"{GREEN}APK安装成功!请在盒子上查看{NC}")
        else:
            print(f"{RED}APK安装失败:{install_result.stderr}{NC}")
        os.remove(f"/tmp/{filename}")
        print(f"{YELLOW}临时文件/tmp/{filename}已清理{NC}")
        return 0

    else:
        if connect_adb() != 0:
          return 1
        install_apk(apk_download_url, package_name)
    return 0


def uninstall_app():
    """选择卸载第三方应用程序"""
    if not check_adb_connected():
        if connect_adb() != 0:
            return 1

    try:
        # 使用 pm list packages -3 列出第三方应用
        package_list = subprocess.check_output(["adb", "shell", "pm", "list", "packages", "-3"]).decode()
        # 提取每行的包名,去掉前面的package:前缀
        package_list = [line.replace('package:','').strip() for line in package_list.splitlines()]
    except subprocess.CalledProcessError:
        print(f"{RED}获取第三方应用列表失败{NC}")
        return 1

    if not package_list:
        print(f"{RED}没有找到第三方应用, 无法卸载{NC}")
        return 1  # 返回 1 表示没有找到第三方应用

    num_packages = len(package_list)

    print(f"{YELLOW}请选择要卸载的第三方应用程序 (输入 q 返回主菜单):{NC}")
    print("---------------------------------------------")
    for i, package in enumerate(package_list):
        print(f"{BLUE}{i+1}. {package}{NC}")
    print("---------------------------------------------")
    app_choice = input("请输入应用编号: ")
    if app_choice == "q":
        return 0

    if not is_integer(app_choice) or not (1 <= int(app_choice) <= num_packages):
        print(f"{RED}无效选择，请重新选择或输入 q 返回主菜单。{NC}")
        return 1

    selected_package = package_list[int(app_choice) - 1]
    print(f"{YELLOW}正在卸载: {selected_package}{NC}")

    uninstall_result = subprocess.run(["adb", "uninstall", selected_package], capture_output=True, text=True)
    if "Success" in uninstall_result.stdout:
        print(f"{GREEN}应用 {selected_package} 卸载成功！{NC}")
    else:
        print(f"{RED}应用 {selected_package} 卸载失败: {uninstall_result.stderr}{NC}")
    return 0




def install_dbmarket():
    """安装当贝市场"""
    message = "安装过程若出现弹框,请点击详情后选择【仍然安装】即可"
    apk_download_url = "https://webapk.dangbei.net/update/dangbeimarket.apk"
    package_name = "com.dangbeimarket"
    install_apk(apk_download_url, package_name, message)


def install_mytv_latest_apk():
    """安装 my-tv，从指定 URL 获取版本列表并安装"""
    message = "项目地址: http://10.10.10.13:3000/yaojiwei520/adb/ "
    apk_base_url = "http://10.10.10.13:3000/yaojiwei520/adb/src/branch/main/OurTV/" # 使用 src 路径

    print(f"{YELLOW}正在从以下地址获取版本列表:\n{apk_base_url}{NC}")

    # 获取 APK 文件列表
    status, apk_files = get_apk_list(apk_base_url)
    if status != 0 or not apk_files:
      return 1
    
    selected_apk = select_apk_version(apk_base_url, apk_files)
    if not selected_apk:
      return 1

    apk_download_url =  selected_apk
    package_name = "com.our.tv"
    install_apk(apk_download_url, package_name, message)



def install_kodi_latest_apk():
    """安装 kodi"""
    message = "项目地址: http://10.10.10.13:3000/yaojiwei520/adb/ "
    apk_download_url = "http://10.10.10.13:3000/yaojiwei520/adb/raw/branch/main/kodi/kodi-21.2-Omega-arm64-v8a.apk"
    package_name = "com.Omega.kodi"
    print(f"{YELLOW}使用指定下载地址:\n{apk_download_url}{NC}")
    install_apk(apk_download_url, package_name, message)

def get_status():
    """获取adb连接状态"""
    if check_adb_connected():
        adb_status = f"{GREEN}已连接且已授权{NC}"
    else:
        adb_status = f"{RED}未连接{NC}"
    print(f"*      与电视盒子的连接状态:{adb_status}")


def get_tvbox_model_name():
    """获取电视盒子型号"""
    if check_adb_connected():
        try:
            model = subprocess.check_output(["adb", "shell", "getprop", "ro.product.model"]).decode().strip()
            manufacturer = subprocess.check_output(["adb", "shell", "getprop", "ro.product.manufacturer"]).decode().strip()
            print(f"*      当前电视盒子型号:{BLUE}{manufacturer} {model}{NC}")
        except subprocess.CalledProcessError:
            print(f"*      当前电视盒子型号:{BLUE}未知{NC}")
    else:
        print(f"*      当前电视盒子型号:{BLUE}请先连接ADB{NC}")

def get_tvbox_timezone():
    """获取电视盒子时区"""
    if check_adb_connected():
        try:
           device_timezone = subprocess.check_output(["adb", "shell", "getprop", "persist.sys.timezone"]).decode().strip()
           device_time = subprocess.check_output(["adb", "shell", "date", "+%Y年%m月%d日 %H:%M"]).decode().strip()
           print(f"*      当前电视盒子时区:{YELLOW}{device_timezone}{NC}")
           print(f"*      当前电视盒子时间:{YELLOW}{device_time}{NC}")
        except subprocess.CalledProcessError:
            print(f"*      当前电视盒子时区:{BLUE}未知{NC}")
            print(f"*      当前电视盒子时间:{BLUE}未知{NC}")
    else:
        print(f"*      当前电视盒子时区:{BLUE}请先连接ADB{NC}")
        print(f"*      当前电视盒子时间:{BLUE}请先连接ADB{NC}")


def get_router_name():
    """获取软路由型号信息"""
    if is_x86_64_router():
        try:
          cpuinfo = subprocess.check_output(["grep", "model name", "/proc/cpuinfo"]).decode()
          return cpuinfo.split(":", 1)[1].strip().splitlines()[0]
        except subprocess.CalledProcessError:
            return "未知"
    else:
        return "非 x86 系统"

# 菜单
menu_options = [
    "安装ADB",
    "连接ADB",
    "断开ADB",
    "安装当贝市场",
    "安装tv",
    "安装kodi",
    "卸载指定应用",
]

commands = {
    "install_adb": install_adb,
    "connect_adb": connect_adb,
    "disconnect_adb": disconnect_adb,
    "install_dbmarket": install_dbmarket,
    "install_tv": install_mytv_latest_apk,
    "install_kodi": install_kodi_latest_apk,
    "uninstall_app": uninstall_app,
}

def handle_choice(choice):
    """处理菜单选择"""
    if choice == 1:
      install_adb()
    elif choice == 2:
      connect_adb()
    elif choice == 3:
       disconnect_adb()
    elif choice == 4:
      install_dbmarket()
    elif choice == 5:
       install_mytv_latest_apk()
    elif choice == 6:
        install_kodi_latest_apk()
    elif choice == 7:
        uninstall_app()
    else:
      print(f"{RED}无效选项,请重新选择。{NC}")


def show_menu():
    """显示菜单"""
    download_common_shell()
    os.makedirs("/tmp/upload", exist_ok=True)
    os.system('clear')
    print("***********************************************************************")
    print(f"*      {YELLOW}盒子助手版 当前版本:v{SCRIPT_VERSION}{NC}        ")
    print(f"*      {GREEN}专治老人不知道如何下载app问题{NC}         ")
    print(f"*      {RED}请确保电视盒子和OpenWrt路由器处于{NC}{BLUE}同一网段{NC}\n*      {RED}且电视盒子开启了{NC}{BLUE}USB调试模式(adb开关){NC}         ")
    print("*      Developed by @yaojiwei        ")
    print("**********************************************************************")
    print()
    print(f"*      当前的路由器型号: {get_router_name()}")
    get_status()
    get_tvbox_model_name()
    get_tvbox_timezone()
    print()
    print("**********************************************************************")
    print("请选择操作：")
    for i, option in enumerate(menu_options):
        print(f"{BLUE}{i + 1}. {option}{NC}")


def show_user_tips():
    """显示用户提示"""
    input("按 Enter 键继续...")


if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("请输入选项的序号(输入q退出): ")
        if choice == 'q':
            disconnect_adb()
            print(f"{GREEN}您已退出盒子助手,下次运行 ./tv.sh 即可{NC}")
            print()
            break

        if not is_integer(choice) or not (1 <= int(choice) <= len(menu_options)):
            print(f"{RED}无效选项，请输入 1 到 {len(menu_options)} 之间的数字。{NC}")
            show_user_tips()
            continue
        
        handle_choice(int(choice))
        show_user_tips()
