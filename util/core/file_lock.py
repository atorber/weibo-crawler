"""跨进程文件锁：让主爬与评论回填互斥，避免并发整文件读改写互相覆盖。

实现：
- POSIX（macOS/Linux）：``fcntl.flock``。进程退出时内核自动释放，磁盘上
  残留的锁文件不会造成永久死锁；锁文件本身只作为 flock 的锚点。
- Windows：``msvcrt.locking``（进程退出时内核同样自动释放）。若仍遇到旧版
  ``O_CREAT|O_EXCL`` 残留的锁文件，会按文件内 PID 判断持有者是否存活，
  已死则回收后重试，避免控制台 stop/kill 后无法再启动。
"""

from __future__ import annotations

import os
import re

try:  # POSIX
    import fcntl
except ImportError:  # Windows
    fcntl = None

try:  # Windows
    import msvcrt
except ImportError:
    msvcrt = None

_HOLDER_PID_RE = re.compile(r"^(\d+)\b")


class LockBusy(RuntimeError):
    """锁已被其他进程占用。"""

    def __init__(self, path: str, holder: str = ""):
        self.path = path
        self.holder = holder
        message = "锁被占用: %s" % path
        if holder:
            message += "（持有者: %s）" % holder
        super().__init__(message)


def _parse_holder_pid(holder: str) -> int | None:
    match = _HOLDER_PID_RE.match((holder or "").strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def is_pid_alive(pid: int) -> bool:
    """判断 PID 是否仍在运行（用于回收 Windows 残留锁）。"""
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) == 0:
                return False
            return int(exit_code.value) == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _holder_is_stale(holder: str) -> bool:
    pid = _parse_holder_pid(holder)
    if pid is None:
        # 无法解析 PID 的残留文件：当作可回收，避免永久卡死
        return True
    return not is_pid_alive(pid)


class FileLock:
    """优先非阻塞获取的跨进程文件锁，支持 ``with`` 语法。"""

    def __init__(self, path: str):
        self.path = path
        self._handle = None

    def acquire(self, blocking: bool = False) -> "FileLock":
        directory = os.path.dirname(os.path.abspath(self.path)) or os.getcwd()
        os.makedirs(directory, exist_ok=True)
        if fcntl is not None:
            self._acquire_posix(blocking)
        else:
            self._acquire_windows()
        return self

    def _acquire_posix(self, blocking: bool) -> None:
        handle = open(self.path, "a+", encoding="utf-8")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(handle.fileno(), flags)
        except OSError:
            holder = self._read_holder(handle)
            handle.close()
            raise LockBusy(self.path, holder)
        self._handle = handle
        self._write_holder(handle)

    def _open_lock_file_rw(self):
        """以可定位读写方式打开锁文件（不用 a+：append 下 seek 后写入仍追加）。"""
        try:
            return open(self.path, "r+", encoding="utf-8")
        except FileNotFoundError:
            return open(self.path, "w+", encoding="utf-8")

    def _acquire_windows(self, *, _retried: bool = False) -> None:
        """Windows：msvcrt 字节锁 + 陈旧 O_EXCL 残留回收。"""
        if msvcrt is None:
            # 极端环境兜底：仍用 O_EXCL，但带陈旧回收
            self._acquire_windows_excl(_retried=_retried)
            return

        handle = self._open_lock_file_rw()
        try:
            # msvcrt.locking 需要至少 1 字节可锁区域
            handle.seek(0, os.SEEK_END)
            if handle.tell() < 1:
                handle.write("\n")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            holder = self._read_holder(handle)
            handle.close()
            if not _retried and _holder_is_stale(holder):
                try:
                    os.remove(self.path)
                except OSError:
                    pass
                self._acquire_windows(_retried=True)
                return
            raise LockBusy(self.path, holder)

        self._handle = handle
        # 持锁后再写 holder（r+ 下 seek(0) 可覆盖）；保留首字节作为锁定位。
        try:
            handle.seek(0)
            handle.write("\n%d %s\n" % (os.getpid(), "weibo-crawler"))
            handle.truncate(handle.tell())
            handle.flush()
        except OSError:
            pass

    def _acquire_windows_excl(self, *, _retried: bool = False) -> None:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = ""
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    holder = handle.read().strip()
            except OSError:
                pass
            if not _retried and _holder_is_stale(holder):
                try:
                    os.remove(self.path)
                except OSError:
                    pass
                else:
                    self._acquire_windows_excl(_retried=True)
                    return
            raise LockBusy(self.path, holder)
        self._handle = os.fdopen(fd, "w", encoding="utf-8")
        self._write_holder(self._handle)

    @staticmethod
    def _read_holder(handle) -> str:
        try:
            handle.seek(0)
            return handle.read().strip()
        except OSError:
            return ""

    def _write_holder(self, handle) -> None:
        try:
            handle.seek(0)
            handle.truncate()
            handle.write("%d %s\n" % (os.getpid(), "weibo-crawler"))
            handle.flush()
        except OSError:
            pass

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            handle.close()
            return

        if msvcrt is not None:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            handle.close()
            # 与 POSIX 一致：保留锚点文件；内核锁已释放即可再次获取
            return

        handle.close()
        try:
            os.remove(self.path)
        except OSError:
            pass

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False


def lock_path_for_output(output_dir: str) -> str:
    """主爬与回填共用的锁文件路径（放在数据输出目录根部）。"""
    return os.path.join(os.path.abspath(output_dir), ".weibo_crawler.lock")


def resolve_output_dir(project_root: str, configured) -> str:
    """把 ``output_directory`` 配置解析为绝对路径（绝对路径原样返回）。"""
    value = str(configured or "weibo_data")
    if os.path.isabs(value):
        return value
    return os.path.join(project_root, value)
