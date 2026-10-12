import subprocess, threading
import psutil

def cpu():
    return psutil.cpu_percent(None)

def ram():
    vm = psutil.virtual_memory()
    return vm.percent, vm.used / 2**30, vm.total / 2**30

class GpuPoller(threading.Thread):
    """Загрузка GPU через nvidia-smi (только NVIDIA). value=None -> недоступно."""
    def __init__(self):
        super().__init__(daemon=True)
        self.value = None
        self._halt = threading.Event()
        self._available = True

    def _query(self):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, creationflags=0x08000000)
            return float(out.stdout.strip().splitlines()[0])
        except FileNotFoundError:
            self._available = False
        except Exception:
            pass
        return None

    def run(self):
        while self._available and not self._halt.wait(2):
            self.value = self._query()

    def stop(self):
        self._halt.set()
