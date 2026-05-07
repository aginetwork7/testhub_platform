"""
TestHub 后端启动脚本，建议开发测试阶段，生产不建议使用
自动使用 config.yaml 中配置的端口
"""
import os
import sys
import yaml
import subprocess
import signal
import time

# 读取 config.yaml 中的端口配置
config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')

try:
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        backend_port = config.get('server', {}).get('backend_port', 8000)
except Exception as e:
    print(f"读取配置文件失败: {e}")
    print(f"配置文件路径: {config_path}")
    backend_port = 8000

print(f"正在启动后端服务器，端口: {backend_port}")

# 获取 manage.py 的绝对路径
script_dir = os.path.dirname(os.path.abspath(__file__))
manage_py_path = os.path.join(script_dir, 'manage.py')

# 子进程列表
processes = []

# 信号处理函数
def cleanup(signum=None, frame=None):
    """关闭所有子进程"""
    print("\n正在关闭服务...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    sys.exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

# 启动服务器
proc_server = subprocess.Popen([sys.executable, manage_py_path, 'runserver', f'0.0.0.0:{backend_port}'])
processes.append(proc_server)

# 启动任务队列
proc_queue = subprocess.Popen([sys.executable, manage_py_path, 'qcluster'])
processes.append(proc_queue)

# 监控进程状态
while True:
    time.sleep(1)
    for proc in processes:
        if proc.poll() is not None and proc.returncode != 0:
            print(f"进程异常退出: {proc.args}, 返回码：{proc.returncode}")
            cleanup()
