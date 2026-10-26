import subprocess
import sys
import os


def run_scripts():
    try:
        # 使用 Python 解释器路径
        python_path = sys.executable

        # 启动 service.py
        service_process = subprocess.Popen([python_path, "service.py"])
        print("service.py 已启动")

        # 启动 app.py
        app_process = subprocess.Popen([python_path, "app.py"])
        print("app.py 已启动")

        # 等待进程结束
        service_process.wait()
        app_process.wait()

    except KeyboardInterrupt:
        print("\n正在关闭所有进程...")
        # 在 Windows 上使用 taskkill
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(service_process.pid)])  # noqa:501
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(app_process.pid)])  # noqa:501
        # 在 Unix/Linux 上使用 kill
        else:
            service_process.terminate()
            app_process.terminate()
        print("所有进程已关闭")

    except Exception as e:
        print(f"发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("正在启动应用程序...")
    run_scripts()
