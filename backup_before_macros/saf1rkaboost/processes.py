import getpass, os
import psutil

SYSROOT = os.environ.get("SystemRoot", r"C:\Windows").lower()
ME = getpass.getuser().lower()
CPUS = psutil.cpu_count() or 1

PROTECTED_NAMES = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "fontdrvhost.exe", "audiodg.exe",
    "sihost.exe", "taskhostw.exe", "ctfmon.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "shellexperiencehost.exe", "runtimebroker.exe", "securityhealthservice.exe",
    "securityhealthsystray.exe", "msmpeng.exe", "nissrv.exe"}
LAUNCHERS = {"steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "battle.net.exe", "origin.exe",
             "eadesktop.exe", "ubisoftconnect.exe", "upc.exe", "galaxyclient.exe", "rockstarservice.exe"}
KEYWORDS = ("antivirus", "defender", "kaspersky", "avast", "avg", "bitdefender", "eset", "norton",
            "mcafee", "malwarebytes", "sophos", "easyanticheat", "battleye", "beservice", "vanguard",
            "vgc", "vgtray", "faceit", "xigncode", "nprotect", "anticheat", "gameguard",
            "nvidia", "nvcontainer", "amd", "radeon", "realtek", "intel")

def _reason(i):
    name = (i.get("name") or "").lower()
    user = i.get("username") or ""
    exe = (i.get("exe") or "").lower()
    if not name or i["pid"] in (0, 4):
        return "system"
    if i["pid"] == os.getpid():
        return "saf1rkaboost"
    if name in PROTECTED_NAMES:
        return "процесс Windows"
    if name in LAUNCHERS:
        return "лаунчер игр"
    if any(k in name for k in KEYWORDS):
        return "антивирус/драйвер/античит"
    if not user or user.split("\\")[-1].lower() != ME:
        return "чужой/системный аккаунт"
    if not exe:
        return "нет доступа"
    if exe.startswith(SYSROOT) or "windows defender" in exe:
        return "компонент Windows"
    return None

def protection_reason(pid, keep=()):
    if pid in keep:
        return "игра/saf1rkaboost"
    try:
        info = psutil.Process(pid).as_dict(["pid", "name", "username", "exe"])
    except psutil.Error:
        return "процесс недоступен"
    return _reason(info)

def snapshot(sort="cpu", limit=30):
    rows = []
    for p in psutil.process_iter(["pid", "name", "username", "exe", "cpu_percent", "memory_info"]):
        i = p.info
        if i["pid"] == 0 or not i.get("memory_info"):
            continue
        rows.append({"pid": i["pid"], "name": i["name"] or "?", "cpu": (i["cpu_percent"] or 0) / CPUS,
                     "ram": i["memory_info"].rss / 2**20, "reason": _reason(i)})
    rows.sort(key=lambda r: r["cpu" if sort == "cpu" else "ram"], reverse=True)
    return rows[:limit]

def terminate(pid, keep=()):
    r = protection_reason(pid, keep)
    if r:
        raise PermissionError(f"защищён ({r})")
    p = psutil.Process(pid)
    p.terminate()
    try:
        p.wait(3)
    except psutil.TimeoutExpired:
        p.kill()
