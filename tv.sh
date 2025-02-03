#!/bin/bash

# 定义颜色
RED='\033[0;31m'
NC='\033[0m'
GREEN='\e[38;5;154m'
YELLOW='\e[93m'
BLUE='\e[96m'

# 定义脚本版本
SCRIPT_VERSION="1.2"

# 判断是否为x86软路由
is_x86_64_router() {
    [[ $(uname -m) == "x86_64" ]]
}

download_common_shell() {
    if [ ! -f common.sh ]; then
        echo -e "${YELLOW}正在下载 common.sh...${NC}"
        if wget -O common.sh "http://10.10.10.13:3000/yaojiwei520/adb/raw/branch/main/common.sh"; then
           chmod +x common.sh
           source common.sh
           echo -e "${GREEN}common.sh 下载和执行成功${NC}"
        else
           echo -e "${RED}下载 common.sh 失败,请检查网络${NC}"
            exit 1
        fi
   fi
}

# 检查输入是否为整数
is_integer() {
    [[ "$1" =~ ^-?[0-9]+$ ]]
}

# 判断adb是否安装
check_adb_installed() {
    command -v adb >/dev/null 2>&1
}

# 判断adb是否连接成功
check_adb_connected() {
    check_adb_installed && [[ -n $(adb devices | awk 'NR>1 {print $2}' | grep 'device$') ]]
}

# 安装adb工具
install_adb() {
    echo -e "${BLUE}绝大多数软路由自带ADB 只有少数OpenWrt硬路由才需要安装ADB${NC}"
    if ! check_adb_installed; then
        echo -e "${YELLOW}正在尝试安装adb，需要管理员权限...${NC}"
        echo -e "${YELLOW}请注意,需要输入sudo密码(如果需要)...${NC}"
        sudo apt update
        if sudo apt install -y adb; then
            echo -e "${GREEN}adb 安装成功!${NC}"
        else
            echo -e "${RED}adb 安装失败,请检查日志以获取更多信息。${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}您的系统已经安装了ADB工具${NC}"
    fi
}

# 连接adb
connect_adb() {
    install_adb
    if [[ $? -ne 0 ]];then
        return 1
    fi
    local gateway_ip
    gateway_ip=$(ip route get 1 | awk '{print $7}' | head -n 1)

    if [ -z "$gateway_ip" ]; then
        read -p "${RED}无法自动获取网关IP地址，请手动输入电视盒子的完整IP地址：${NC}" ip
    else
        local gateway_prefix
        gateway_prefix=$(echo "$gateway_ip" | sed 's/\.[0-9]*$//').
        echo -e "${YELLOW}请输入电视盒子的ip地址(${NC}${BLUE}${gateway_prefix}${NC}${YELLOW})的最后一段数字${NC}"
        read end_number
        if ! is_integer "$end_number"; then
            echo -e "${RED}错误: 请输入整数。${NC}"
            return 1
        fi
        ip="${gateway_prefix}${end_number}"
    fi

    adb disconnect
    echo -e "${BLUE}首次使用,盒子上可能会提示授权弹框,给您半分钟时间来操作...【允许】${NC}"
    adb connect "$ip"

    local i=0
    while [[ $i -lt 30 ]]; do
         i=$((i + 1))
        echo -e "${YELLOW}第${i}次尝试连接ADB,请在设备上点击【允许】按钮...${NC}"
        if [[ $(adb devices | grep "${ip}:5555" | awk '{print $2}') == "device" ]]; then
            echo -e "${GREEN}ADB 已经连接成功啦,你可以放心操作了${NC}"
            return 0
        fi
        sleep 1
    done
    echo -e "${RED}连接超时,或者您点击了【取消】,请确认电视盒子的IP地址是否正确。如果问题持续存在,请检查设备的USB调试设置是否正确并重新连接adb${NC}"
    return 1
}

#断开adb连接
disconnect_adb() {
    if check_adb_installed; then
        adb disconnect >/dev/null 2>&1
        echo "ADB 已经断开"
    else
        echo -e "${YELLOW}您还没有安装ADB${NC}"
    fi
}

# 获取目录下的 APK 文件列表
get_apk_list() {
    local url="$1"
    local files
    files=$(curl -s "$url" | grep 'href=".*\.apk"' | sed 's/.*href="\([^"]*\).*/\1/' )
    if [[ -z "$files" ]]; then
         echo -e "${RED}获取APK列表失败, 请检查网络或URL是否正确: $url${NC}"
         return 1
    fi
    echo "$files"
}

# 选择 APK 版本
select_apk_version() {
    local url="$1"
    local apk_list
    apk_list=$(get_apk_list "$url")
    if [[ $? -ne 0 ]];then
        return 1
    fi

    if [[ -z "$apk_list" ]]; then
        echo -e "${RED}未找到任何APK文件,请检查URL是否正确或版本列表为空。${NC}"
        return 1
    fi

    local apk_array
    readarray -t apk_array <<< "$apk_list"
    local num_apks="${#apk_array[@]}"
    echo -e "${YELLOW}请选择要安装的 APK 版本 (输入 q 返回主菜单):${NC}"
    echo "---------------------------------------------"
    for i in "${!apk_array[@]}"; do
        echo -e "${BLUE}$((i+1)). ${apk_array[i]}${NC}"
    done
    echo "---------------------------------------------"
    read -p "请输入版本编号: " apk_choice
    if [[ "$apk_choice" == "q" ]]; then
        return 1
    fi
    if ! [[ "$apk_choice" =~ ^[0-9]+$ ]] || [[ "$apk_choice" -lt 1 ]] || [[ "$apk_choice" -gt "$num_apks" ]]; then
        echo -e "${RED}无效选择，请重新选择或输入 q 返回主菜单。${NC}"
        return 1
    fi
    local selected_apk="${apk_array[$((apk_choice - 1))]}"
    echo "$selected_apk"
}


# 安装apk
install_apk() {
    local apk_download_url="$1"
    local package_name="$2"
    local message="$3"
    local filename=$(basename "$apk_download_url")

   if [ -n "$message" ]; then
      echo -e "${BLUE}$message${NC}"
    fi
   echo -e "${YELLOW}正在下载:$apk_download_url${NC}"
    if wget -O /tmp/"$filename" "$apk_download_url";then
    if check_adb_connected; then
        adb uninstall "$package_name" >/dev/null 2>&1
        echo -e "${GREEN}正在推送和安装apk,请耐心等待...${NC}"
         printf "${BLUE}"
        local i=0
        while [[ $i -lt 3 ]]; do
            i=$((i+1))
            printf ".."
             sleep 1
        done
         echo -ne "${NC}\n"
        local install_result=$(adb install -r /tmp/"$filename" 2>&1)
        if [[ "$install_result" == *"Success"* ]]; then
            echo -e "${GREEN}APK安装成功!请在盒子上查看${NC}"
        else
            echo -e "${RED}APK安装失败:$install_result${NC}"
        fi
        rm -rf /tmp/"$filename"
        echo -e "${YELLOW}临时文件/tmp/${filename}已清理${NC}"
         return 0
    else
        connect_adb
         if ! check_adb_connected; then
            return 1
         fi
         install_apk "$apk_download_url" "$package_name"
    fi
    else
      echo -e "${RED}下载APK失败,请检查网络或URL: $apk_download_url${NC}"
      return 1
    fi
}


# 选择卸载应用
uninstall_app() {
    if ! check_adb_connected; then
        connect_adb
        if ! check_adb_connected; then
            return 1
        fi
    fi

    local package_list
    package_list=$(adb shell pm list packages -i | grep -E 'installer=(null|)$' | sed 's/package://g' | awk '{print $1}')

    if [[ -z "$package_list" ]]; then
        echo -e "${RED}没有找到第三方应用, 无法卸载${NC}"
        return 1
    fi

    local package_array
    readarray -t package_array <<< "$package_list"

    local num_packages="${#package_array[@]}"

    echo -e "${YELLOW}请选择要卸载的第三方应用程序 (输入 q 返回主菜单):${NC}"
    echo "---------------------------------------------"
    for i in "${!package_array[@]}"; do
        echo -e "${BLUE}$((i+1)). ${package_array[i]}${NC}"
    done
    echo "---------------------------------------------"

    read -p "请输入应用编号: " app_choice

    if [[ "$app_choice" == "q" ]]; then
        return 0
    fi

    if ! [[ "$app_choice" =~ ^[0-9]+$ ]] || [[ "$app_choice" -lt 1 ]] || [[ "$app_choice" -gt "$num_packages" ]]; then
        echo -e "${RED}无效选择，请重新选择或输入 q 返回主菜单。${NC}"
        return 1
    fi

    local selected_package="${package_array[$((app_choice - 1))]}"

    echo -e "${YELLOW}正在卸载: ${selected_package}${NC}"
    local uninstall_result=$(adb uninstall "$selected_package" 2>&1)
        if [[ "$uninstall_result" == *"Success"* ]]; then
            echo -e "${GREEN}应用 $selected_package 卸载成功！${NC}"
        else
            echo -e "${RED}应用 $selected_package 卸载失败: $uninstall_result${NC}"
        fi
      return 0
}


# 安装当贝市场
install_dbmarket() {
    local message="安装过程若出现弹框,请点击详情后选择【仍然安装】即可"
    local apk_download_url="https://webapk.dangbei.net/update/dangbeimarket.apk"
    local package_name="com.dangbeimarket"
    install_apk "$apk_download_url" "$package_name" "$message"
}


# 安装 my-tv
install_mytv_latest_apk() {
    local message="项目地址: http://10.10.10.13:3000/yaojiwei520/adb/ "
    local apk_base_url="http://10.10.10.13:3000/yaojiwei520/adb/raw/branch/main/OurTV/"

    echo -e "${YELLOW}正在从以下地址获取版本列表:\n$apk_base_url${NC}"

    local selected_apk
    selected_apk=$(select_apk_version "$apk_base_url")
    if [[ $? -ne 0 ]];then
        return 1
    fi
    if [[ -z "$selected_apk" ]];then
        return 1
    fi
    local apk_download_url="${apk_base_url}${selected_apk}"
    local package_name="com.our.tv"
    install_apk "$apk_download_url" "$package_name" "$message"
}

# install kodi
install_kodi_latest_apk() {
    local message="项目地址: http://10.10.10.13:3000/yaojiwei520/adb/ "
    local apk_download_url="http://10.10.10.13:3000/yaojiwei520/adb/raw/branch/main/kodi/kodi-21.2-Omega-arm64-v8a.apk"
    local package_name="com.Omega.kodi"
    echo -e "${YELLOW}使用指定下载地址:\n$apk_download_url${NC}"
    install_apk "$apk_download_url" "$package_name" "$message"
}

get_status() {
    local adb_status
    if check_adb_connected; then
        adb_status="${GREEN}已连接且已授权${NC}"
    else
        adb_status="${RED}未连接${NC}"
    fi
    echo -e "*      与电视盒子的连接状态:$adb_status"
}

# 获取电视盒子型号
get_tvbox_model_name() {
    if check_adb_connected; then
         local model=$(adb shell getprop ro.product.model)
         local manufacturer=$(adb shell getprop ro.product.manufacturer)
         model=$(echo "$model" | tr -d '\r\n')
         manufacturer=$(echo "$manufacturer" | tr -d '\r\n')
        echo -e "*      当前电视盒子型号:${BLUE}$manufacturer $model${NC}"
    else
        echo -e "*      当前电视盒子型号:${BLUE}请先连接ADB${NC}"
    fi
}

# 获取电视盒子时区
get_tvbox_timezone() {
    if check_adb_connected; then
        local device_timezone=$(adb shell getprop persist.sys.timezone)
        local device_time=$(adb shell date "+%Y年%m月%d日 %H:%M")
        echo -e "*      当前电视盒子时区:${YELLOW}$device_timezone${NC}"
        echo -e "*      当前电视盒子时间:${YELLOW}$device_time${NC}"
    else
        echo -e "*      当前电视盒子时区:${BLUE}请先连接ADB${NC}"
        echo -e "*      当前电视盒子时间:${BLUE}请先连接ADB${NC}"
    fi
}


##获取软路由型号信息
get_router_name() {
    if is_x86_64_router; then
        grep "model name" /proc/cpuinfo | head -n 1 | awk -F: '{print $2}' | sed 's/^[ \t]*//;s/[ \t]*$//'
    else
       echo "非 x86 系统"
    fi
}


# 菜单
menu_options=(
    "安装ADB"
    "连接ADB"
    "断开ADB"
    "安装当贝市场"
    "安装tv"
    "安装kodi"
    "卸载指定应用"
)

commands=(
    ["install_adb"]="install_adb"
    ["connect_adb"]="connect_adb"
    ["disconnect_adb"]="disconnect_adb"
    ["install_dbmarket"]="install_dbmarket"
    ["install_tv"]="install_mytv_latest_apk"
    ["install_kodi"]="install_kodi_latest_apk"
    ["uninstall_app"]="uninstall_app"
)

# 处理菜单
handle_choice() {
   local choice="$1"
    case "$choice" in
        1) install_adb;;
        2) connect_adb;;
        3) disconnect_adb;;
        4) install_dbmarket;;
        5) install_mytv_latest_apk;;
        6) install_kodi_latest_apk;;
        7) uninstall_app;;
        *) echo -e "${RED}无效选项,请重新选择。${NC}";;
    esac
}

show_menu() {
    download_common_shell
    mkdir -p /tmp/upload
    clear
    echo "***********************************************************************"
    echo -e "*      ${YELLOW}盒子助手版 当前版本:v${SCRIPT_VERSION}${NC}        "
    echo -e "*      ${GREEN}专治老人不知道如何下载app问题${NC}         "
    echo -e "*      ${RED}请确保电视盒子和OpenWrt路由器处于${NC}${BLUE}同一网段${NC}\n*      ${RED}且电视盒子开启了${NC}${BLUE}USB调试模式(adb开关)${NC}         "
    echo "*      Developed by @yaojiwei        "
    echo "**********************************************************************"
    echo
    echo "*      当前的路由器型号: $(get_router_name)"
    echo "$(get_status)"
    echo "$(get_tvbox_model_name)"
    echo "$(get_tvbox_timezone)"
     echo
    echo "**********************************************************************"
    echo "请选择操作："
    for i in "${!menu_options[@]}"; do
        echo -e "${BLUE}$((i + 1)). ${menu_options[i]}${NC}"
    done
}

show_user_tips() {
    read -p "按 Enter 键继续..."
}

while true; do
    show_menu
    read -p "请输入选项的序号(输入q退出): " choice
    if [[ "$choice" == 'q' ]]; then
        disconnect_adb
        echo -e "${GREEN}您已退出盒子助手,下次运行 ./tv.sh 即可${NC}"
        echo
        break
    fi
  
    if [[ ! "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 ]] || [[ "$choice" -gt "${#menu_options[@]}" ]]; then
        echo -e "${RED}无效选项，请输入 1 到 ${#menu_options[@]} 之间的数字。${NC}"
        show_user_tips
        continue
    fi
    
    handle_choice "$choice"
    show_user_tips
done
