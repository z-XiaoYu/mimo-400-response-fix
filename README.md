MiMo API 代理 — 使用说明

方法一：
第 1 步：填入你的 API Key
用记事本打开 mimo_proxy.py，找到第 16~17 行：

API_KEY = ""  # <-- Paste your Key, e.g. API_KEY = "tp-xxxxxxxxxxxx"

把你的 Key 粘贴到引号里，比如：
API_KEY = "tp-xxxxxxxxxxxxxxxxxxxx"
Key 怎么来？ 登录 https://xiaomimimo.com 控制台，复制 Token Plan Key（tp- 开头）

保存文件。

第 2 步：安装依赖
打开 CMD，执行：

pip install flask requests

第 3 步：启动代理

cd <mimo_proxy.py 所在目录>
python mimo_proxy.py --port 1999

看到 Running on http://0.0.0.0:1999 说明成功。
⚠️ 首次启动 Windows 可能弹防火墙提示，必须点"允许"

第 4 步：在 Trae 中配置
打开 Trae → 设置 → 模型 → 添加自定义模型
服务商	OpenAI
模型 ID	mimo-v2.5-pro
自定义请求地址	http://<你的局域网IP>:1999/v1
不会自动补充地址需要填写完整URL的Agent需要填写：http://<你的局域网IP>:1999/v1/chat/completions
API Key	你的 MiMo API Key（tp- 开头）
怎么查你的局域网 IP？
打开 CMD 输入 ipconfig，找"WLAN"下的 IPv4 地址，比如 192.168.1.10
那请求地址就是 http://192.168.1.10:1999/v1
完整URL地址是：http://192.168.1.10:1999/v1/chat/completions

方法二：

使用 start_proxy.bat

用记事本打开 start_proxy.bat
找到 set MIMO_API_KEY= 这一行，在等号后面填上 Key：set MIMO_API_KEY=tp-xxxxxxxxxxxxxxxxxxxx
把 start_proxy.bat 和 mimo_proxy.py 放在同一个文件夹
双击 start_proxy.bat
它会自动检查 Python、自动安装依赖、自动启动代理。

在 Trae 中配置
打开 Trae → 设置 → 模型 → 添加自定义模型
服务商	OpenAI
模型 ID	mimo-v2.5-pro
自定义请求地址	http://<你的局域网IP>:1999/v1/chat/completions
API Key	你的 MiMo API Key（tp- 开头）
怎么查你的局域网 IP？
打开 CMD 输入 ipconfig，找"WLAN"下的 IPv4 地址，比如 192.168.1.10
那请求地址就是 http://192.168.1.10:1999/v1/chat/completions
