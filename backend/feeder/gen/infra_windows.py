"""WINDOWS: services and perfmon metrics, AppLocker, PowerShell (classic and operational), Sysmon, Windows Defender and
forwarded events (security logons, process creation, PowerShell).

Topology: 5 hosts (a domain controller, file server, app server, SQL server and a workstation). Windows event streams are
sent as the documents the Elastic Agent winlog input produces (the integration's own ingest pipeline then runs on them).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra
from .infra import GROUP, S, WINDOWS_HOSTS

CORP = "CORP"
USERS = [(n, w) for n, w in zip(["alice.martin", "bob.chen", "carol.novak", "dave.okafor", "erin.ito", "frank.silva", "grace.haddad", "svc-sql", "svc-backup", "administrator"],
                                [8, 7, 6, 5, 4, 3, 2, 2, 1, 1])]
DOMAIN_SID = "S-1-5-21-3623811015-3361044348-30300820"


def sid(name: str) -> str:
    return f"{DOMAIN_SID}-{1000 + infra.stable('sid', name) % 9000}"


def fqdn(h: str) -> str:
    return f"{h.lower()}.corp.example.org"


def _host(c: Ctx, kind_mod: int = 5) -> str:
    return WINDOWS_HOSTS[c.rng.randrange(kind_mod) % len(WINDOWS_HOSTS)]


def _base(key: str, host: str, ts: datetime) -> dict:
    """Event document from the stream sample, re-hosted; the sample's own raw XML and timestamps are dropped."""
    d = infra.sample(key)
    for k in ("_tmp",):
        d.pop(k, None)
    d["host"] = infra.host_block(fqdn(host), "windows")
    d["host"]["name"] = fqdn(host)
    d["agent"] = infra.agent_block(host, "filebeat")
    d["event"].pop("original", None)
    d["event"].pop("ingested", None)
    d["event"]["created"] = profile.iso(ts)
    d.get("winlog", {})["computer_name"] = fqdn(host)
    d.get("winlog", {})["record_id"] = str(100000 + int(ts.timestamp()) % 900000 + infra.stable(host) % 1000)
    d.get("winlog", {}).setdefault("process", {})
    d["winlog"]["process"] = {"pid": 800 + infra.stable(host, "wp") % 3000, "thread": {"id": 1000 + infra.stable(host, "wt") % 5000}}
    d.pop("cloud", None)
    d.get("data_stream", {}).pop("namespace", None)
    return d


# ---- services (metrics, TSDB) -----------------------------------------------------------------------------------------------
SERVICES = [("W32Time", "Windows Time", "Automatic", "LocalService"), ("EventLog", "Windows Event Log", "Automatic", "NT AUTHORITY\\LocalService"),
            ("Dnscache", "DNS Client", "Automatic", "NT AUTHORITY\\NetworkService"), ("Spooler", "Print Spooler", "Automatic", "LocalSystem"),
            ("WinRM", "Windows Remote Management (WS-Management)", "Automatic", "NT AUTHORITY\\NetworkService"),
            ("MSSQLSERVER", "SQL Server (MSSQLSERVER)", "Automatic", "CORP\\svc-sql"), ("W3SVC", "World Wide Web Publishing Service", "Automatic", "LocalSystem"),
            ("BITS", "Background Intelligent Transfer Service", "Manual", "LocalSystem"), ("WinDefend", "Microsoft Defender Antivirus Service", "Automatic", "LocalSystem"),
            ("LanmanServer", "Server", "Automatic", "LocalSystem")]
SVC_PER_HOST = 8


def _service(c: Ctx) -> dict:
    host = WINDOWS_HOSTS[c.i // SVC_PER_HOST % len(WINDOWS_HOSTS)]
    name, display, start, acct = SERVICES[(c.i + c.i // SVC_PER_HOST * 3) % len(SERVICES)]
    r = c.rng
    # one believable flaky service: Spooler on the workstation stops now and then (about a minute in 40), BITS (manual) is mostly stopped
    flaky = name == "Spooler" and host == "WIN-WKS07" and r.random() < 0.18
    state = "Stopped" if flaky or (name == "BITS" and r.random() < 0.8) else "Running"
    d = infra.metric_base("windows/service", host, "windows", "windows") if "windows/service" in infra.S and infra.fields_path("windows/service").exists() and infra.S["windows/service"].template_path.exists() else _svc_empty(host)
    d["host"]["name"] = host
    pid = 0 if state == "Stopped" else 400 + infra.stable(host, name) % 8000
    up = 0 if state == "Stopped" else (infra.stable(host, name, "up") % 20 + 1) * 86400_000 + int(c.ts.timestamp() % 86400) * 1000
    d["windows"] = {"service": {"display_name": display, "id": f"{host}_{name}".replace("-", "_")[:40] + f"_{infra.stable(host, name) % 1000}", "name": name,
                                "path_name": f"C:\\Windows\\System32\\svchost.exe -k {name}", "pid": pid, "start_name": acct, "start_type": start,
                                "state": state, "exit_code": "0" if state == "Running" else "1066", "uptime": {"ms": up}}}
    d["service"] = {"type": "windows"}
    d["event"] = {"module": "windows", "duration": 1_000_000 + c.rng.randrange(900_000)}
    d["metricset"] = {"name": "service", "period": 600000}
    return d


def _svc_empty(host: str) -> dict:
    return {"host": infra.host_block(host, "windows"), "agent": infra.agent_block(host, "metricbeat"), "ecs": {"version": "8.17.0"}}


PERF = [("Processor", "_Total", "pct_processor_time"), ("Memory", "", "available_mbytes"), ("LogicalDisk", "C:", "pct_free_space"),
        ("PhysicalDisk", "0 C:", "avg_disk_queue_length"), ("Network Interface", "Ethernet0", "bytes_total_per_sec")]


def _perfmon(c: Ctx) -> dict:
    host = WINDOWS_HOSTS[c.i % len(WINDOWS_HOSTS)]
    r = c.rng
    d = _svc_empty(host)
    cpu = min(99.0, round((12 + 55 * min(c.load, 1.5) / 1.5 + r.gauss(0, 6)) * (1.6 if host == "WIN-SQL01" else 1.0), 2))
    d["windows"] = {"perfmon": {"object": "Processor", "instance": "_Total", "processor": {"pct_processor_time": max(0.5, cpu), "pct_privileged_time": round(max(0.2, cpu * 0.3), 2)},
                                "memory": {"available_mbytes": int(8000 - 2500 * min(c.load, 1.5) + r.gauss(0, 120)), "pages_per_sec": round(r.uniform(0, 60), 2)},
                                "logicaldisk": {"pct_free_space": round(52 - (infra.stable(host) % 20) + r.gauss(0, 0.2), 2)}}}
    d["event"] = {"module": "windows"}
    d["metricset"] = {"name": "perfmon", "period": 300000}
    d["service"] = {"type": "windows"}
    return d


# ---- AppLocker ----------------------------------------------------------------------------------------------------------------
# (path, original name, product, publisher org, country, version, sha256 seed)
APPS = [("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "CHROME.EXE", "GOOGLE CHROME", "GOOGLE LLC", "US", "130.0.6723.92"),
        ("C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE", "WINWORD.EXE", "MICROSOFT OFFICE", "MICROSOFT CORPORATION", "US", "16.0.17928.20114"),
        ("C:\\Program Files\\Git\\bin\\git.exe", "GIT.EXE", "GIT", "JOHANNES SCHINDELIN", "DE", "2.47.0.01"),
        ("C:\\Users\\Public\\Downloads\\setup_tool.exe", "SETUP_TOOL.EXE", "UNKNOWN TOOLS", "ACME FREEWARE LTD", "NL", "1.0.2.0"),
        ("C:\\Windows\\System32\\cmd.exe", "CMD.EXE", "MICROSOFT WINDOWS OPERATING SYSTEM", "MICROSOFT WINDOWS", "US", "10.0.20348.2700"),
        ("C:\\Program Files\\7-Zip\\7z.exe", "7Z.EXE", "7-ZIP", "IGOR PAVLOV", "RU", "24.08.00"),
        ("C:\\Users\\alice.martin\\AppData\\Local\\Temp\\update_helper.exe", "UPDATE_HELPER.EXE", "UPDATE HELPER", "UNKNOWN PUBLISHER", "CN", "3.1.4.0"),
        ("C:\\Program Files\\Slack\\slack.exe", "SLACK.EXE", "SLACK", "SLACK TECHNOLOGIES LLC", "US", "4.40.131")]
PACKAGES = [("MICROSOFT.BINGNEWS", "MICROSOFT CORPORATION", "US", "4.55.62231.00", "APPX"), ("MICROSOFT.TODOS", "MICROSOFT CORPORATION", "US", "2.100.61791.00", "APPX"),
            ("MICROSOFTTEAMS", "MICROSOFT CORPORATION", "US", "24295.605.3225.8804", "APPX"), ("SPOTIFYAB.SPOTIFYMUSIC", "SPOTIFY AB", "SE", "1.2.50.0", "APPX"),
            ("MICROSOFT.WINDOWSTERMINAL", "MICROSOFT CORPORATION", "US", "1.21.2701.0", "APPX")]
SCRIPTS = [("C:\\Scripts\\backup-nightly.ps1", "backup-nightly.ps1"), ("C:\\Users\\bob.chen\\Desktop\\report.vbs", "report.vbs"),
           ("C:\\Installers\\agent-setup.msi", "agent-setup.msi"), ("C:\\Temp\\tmp4F2A.ps1", "tmp4F2A.ps1")]


def _applocker(key: str, policy: str, codes: dict[str, float], script: bool = False, packaged: bool = False):
    chan = {"applocker_exe_and_dll": "EXE and DLL", "applocker_msi_and_script": "MSI and Script", "applocker_packaged_app_deployment": "Packaged app-Deployment",
            "applocker_packaged_app_execution": "Packaged app-Execution"}[key.split("/")[1]]
    lvl = {"8002": "information", "8003": "warning", "8004": "error", "8005": "information", "8006": "warning", "8007": "error", "8020": "information",
           "8021": "warning", "8022": "error", "8023": "information", "8024": "warning", "8025": "error"}

    def build(c: Ctx) -> dict:
        r = c.rng
        host = _host(c)
        d = _base(key, host, c.ts)
        code = profile.pick(r, codes)
        user, _ = USERS[r.randrange(7)] if host == "WIN-WKS07" or True else USERS[0]
        user_sid = sid(user)
        if script:
            path, fname = SCRIPTS[r.randrange(len(SCRIPTS))]
            prod, org, ctry, ver, orig = "", "MICROSOFT CORPORATION" if r.random() < 0.3 else "", "US" if r.random() < 0.3 else "", "0.0.0.00", ""
        else:
            path, orig, prod, org, ctry, ver = APPS[r.randrange(len(APPS))]
            fname = path.rsplit("\\", 1)[1].lower()
        if packaged:
            prod, org, ctry, ver, orig = PACKAGES[r.randrange(len(PACKAGES))]
            path, fname = f"C:\\Program Files\\WindowsApps\\{prod}_{ver}\\app.exe", "app.exe"
            orig = "APPX"
        sha = hashlib.sha256((path + ver).encode()).hexdigest().upper()
        rule = "-" if code in ("8003", "8006") else f"{policy} rule (default): publisher allow" if code in ("8002", "8005") else f"{policy} rule: deny unsigned"
        d["event"].update({"code": code, "action": "None", "kind": "event", "category": ["process"], "type": ["start"], "provider": "Microsoft-Windows-AppLocker", "dataset": key.replace("/", ".").replace("windows.", "windows.")})
        d["event"]["dataset"] = S[key].dataset
        d["log"] = {"level": lvl.get(code, "information")}
        d["file"] = {"hash": {"sha256": sha}, "name": fname, "path": path, "pe": {"file_version": ver, "original_file_name": orig, "product": prod},
                     "x509": {"subject": {"country": [ctry] if ctry else [], "organization": [org] if org else []}}}
        d["user"] = {"id": user_sid, "name": user, "domain": CORP}
        d["related"] = {"user": [user, user_sid], "hash": [sha]}
        if packaged:
            d["file"] = {"pe": {"file_version": ver, "original_file_name": "APPX", "product": prod},
                         "x509": {"subject": {"common_name": [org], "country": [ctry], "locality": ["REDMOND"], "organization": [org], "state_or_province": ["WASHINGTON"]}}}
            ud = {"Fqbn": f"CN={org}, O={org}, L=REDMOND, S=WASHINGTON, C={ctry}\\{prod}\\APPX\\{ver}", "FqbnLength": 100, "Package": prod, "PackageLength": str(len(prod)),
                  "PolicyName": "APPX", "PolicyNameLength": 4, "RuleId": "{a9e18c21-ff8f-43cf-b9fc-db40eed693ba}", "RuleName": "(Default Rule) All signed packaged apps" if code != "8022" else "Block unsigned packaged apps",
                  "RuleNameLength": 39, "RuleSddl": "D:(XA;;FX;;;S-1-1-0)", "RuleSddlLength": 20, "TargetProcessId": 2000 + r.randrange(40000), "TargetUser": user_sid, "xml_name": "RuleAndFileData"}
            if code in ("8020", "8021", "8022"):
                ud.pop("TargetProcessId")
        d["winlog"].update({"channel": f"Microsoft-Windows-AppLocker/{chan}", "event_id": code, "level": lvl.get(code, "information"), "opcode": "Info", "task": "None",
                            "provider_name": "Microsoft-Windows-AppLocker", "provider_guid": "{cbda4dbf-8d5d-4f69-9578-be14aa540d22}", "time_created": profile.iso(c.ts),
                            "user": {"identifier": user_sid},
                            "user_data": {"FileHash": sha, "FileHashLength": 32, "FilePath": "%OSDRIVE%" + path[2:].upper(), "FilePathLength": len(path) + 7,
                                          "Fqbn": f"O={org}, S=WASHINGTON, C={ctry}\\{prod}\\{orig}\\{ver}" if org else "-", "FqbnLength": 60, "FullFilePath": path,
                                          "FullFilePathLength": len(path), "PolicyName": policy, "PolicyNameLength": len(policy), "RuleId": "{" + "%032x" % r.getrandbits(128) + "}"[:0] + "}"
                                          if False else "{00000000-0000-0000-0000-000000000000}", "RuleName": rule, "RuleNameLength": len(rule), "RuleSddl": "-", "RuleSddlLength": 1,
                                          "TargetLogonId": "0x%x" % (0x14fcb7 + r.randrange(9999)), "TargetProcessId": 2000 + r.randrange(40000), "TargetUser": user_sid,
                                          "xml_name": "RuleAndFileData"}})
        if packaged:
            d["winlog"]["user_data"] = ud
        d["tags"] = ["forwarded", "preserve_original_event"]
        return d
    return build


# ---- PowerShell ---------------------------------------------------------------------------------------------------------------
PS_CMDS = ["Get-Process", "Get-Service", "Get-ChildItem", "Invoke-WebRequest", "Set-ExecutionPolicy", "Start-Service", "Get-WinEvent", "Test-NetConnection",
           "Import-Module", "Get-ADUser", "Invoke-Command", "New-ScheduledTask", "Get-Content", "Copy-Item", "Get-EventLog", "Restart-Service"]
PS_USERS = ["CORP\\administrator", "CORP\\svc-backup", "CORP\\alice.martin", "CORP\\bob.chen", "NT AUTHORITY\\SYSTEM"]
PS_SCRIPTS = ["C:\\Scripts\\backup-nightly.ps1", "C:\\Scripts\\patch-report.ps1", "C:\\Users\\alice.martin\\Documents\\deploy.ps1", "C:\\Scripts\\healthcheck.ps1"]
PS_PROVIDERS = [("Certificate", "Started"), ("Registry", "Started"), ("Alias", "Started"), ("FileSystem", "Started"), ("Environment", "Stopped"), ("Function", "Started")]


def _ps_classic(c: Ctx) -> dict:
    r = c.rng
    host = _host(c)
    d = _base("windows/powershell", host, c.ts)
    code = profile.pick(r, {"600": 0.55, "400": 0.225, "403": 0.225})
    prov, state = PS_PROVIDERS[r.randrange(len(PS_PROVIDERS))]
    eng = "5.1.20348.2700"
    app = r.choice(["C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile -File " + r.choice(PS_SCRIPTS), "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell_ise.exe " + r.choice(PS_SCRIPTS)])
    d["event"].update({"code": code, "provider": "PowerShell", "category": ["process"], "type": ["info"], "kind": "event", "sequence": r.randrange(1, 90), "dataset": S["windows/powershell"].dataset})
    d["log"] = {"level": "information"}
    runspace = profile.uuid_for(r)
    d["powershell"] = {"engine": {"version": eng, "previous_state": "Available" if code == "403" else "None", "new_state": "Stopped" if code == "403" else "Available"},
                       "pipeline_id": str(r.randrange(1, 60)), "process": {"executable_version": eng}, "provider": {"name": prov, "new_state": state}, "runspace_id": runspace,
                       "command": {"name": r.choice(PS_CMDS), "path": "", "type": "Cmdlet", "invocation_details": [{"name": "ParameterBinding", "type": "Command", "related_command": r.choice(PS_CMDS), "value": "Name=*"}]},
                       "connected_user": {"name": r.choice(PS_USERS), "domain": CORP}}
    parts = app.split(" ", 1)
    d["process"] = {"args": app.split(" "), "args_count": len(app.split(" ")), "command_line": app, "entity_id": profile.uuid_for(r), "title": "Windows PowerShell"}
    d["user"] = {"name": d["powershell"]["connected_user"]["name"].split("\\")[-1], "domain": CORP}
    d["related"] = {"user": [d["user"]["name"]]}
    d["winlog"].update({"channel": "Windows PowerShell", "event_id": code, "keywords": ["Classic"], "provider_name": "PowerShell"})
    d["tags"] = ["forwarded", "preserve_original_event"]
    return d


SCRIPT_BLOCKS = ["Get-Service | Where-Object Status -eq 'Running' | Select-Object Name, DisplayName", "param($Path) Get-ChildItem -Recurse $Path | Measure-Object -Property Length -Sum",
                 "$ErrorActionPreference='Stop'; Import-Module ActiveDirectory; Get-ADUser -Filter {Enabled -eq $true} | Measure-Object",
                 "Invoke-WebRequest -Uri https://updates.example.org/manifest.json -UseBasicParsing | ConvertFrom-Json",
                 "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625} -MaxEvents 50"]


def _ps_operational(c: Ctx) -> dict:
    r = c.rng
    host = _host(c)
    d = _base("windows/powershell_operational", host, c.ts)
    code = profile.pick(r, {"4104": 0.5, "4103": 0.35, "4105": 0.07, "4106": 0.08})
    user, _ = USERS[r.randrange(len(USERS))]
    block = r.choice(SCRIPT_BLOCKS)
    lvl = {"4104": "verbose", "4103": "information", "4105": "verbose", "4106": "verbose"}[code]
    d["event"].update({"code": code, "provider": "Microsoft-Windows-PowerShell", "category": ["process"], "type": ["start" if code != "4106" else "end"], "kind": "event",
                       "dataset": S["windows/powershell_operational"].dataset})
    d["log"] = {"level": lvl}
    d["powershell"] = {"file": {"script_block_id": profile.uuid_for(r), "script_block_text": block, "script_block_hash": hashlib.sha1(block.encode()).hexdigest().upper(), "script_block_length": len(block)},  # noqa: S324
                       "runspace_id": profile.uuid_for(r), "sequence": 1, "total": 1}
    if code == "4103":
        # raw winlog event data: the integration pipeline splits ContextInfo / Payload into powershell.* and process.*
        cmd = r.choice(PS_CMDS)
        host_app = "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -NoProfile -File " + r.choice(PS_SCRIPTS)
        ctx_lines = [("Severity", "Informational"), ("Host Name", "ConsoleHost"), ("Host Version", "5.1.20348.2700"), ("Host ID", profile.uuid_for(r)),
                     ("Host Application", host_app), ("Engine Version", "5.1.20348.2700"), ("Runspace ID", profile.uuid_for(r)), ("Pipeline ID", str(r.randrange(1, 60))),
                     ("Command Name", cmd), ("Command Type", "Cmdlet"), ("Script Name", ""), ("Command Path", ""), ("Sequence Number", str(r.randrange(10, 900))),
                     ("User", f"{CORP}\\{user}"), ("Connected User", ""), ("Shell ID", "Microsoft.PowerShell")]
        d["winlog"]["event_data"] = {"ContextInfo": "\n".join(f"        {k} = {v}" for k, v in ctx_lines),
                                    "Payload": f'CommandInvocation({cmd}): "{cmd}"\nParameterBinding({cmd}): name="Name"; value="{r.choice(["sqlservr", "w3wp", "*", "C:\\Temp"])}"',
                                    "UserData": ""}
        for k in ("powershell", "process", "file"):
            d.pop(k, None)
        d["event"]["code"] = "4103"
        d["log"] = {"level": "information"}
        d["user"] = {"id": sid(user)}
        d["winlog"].update({"channel": "Microsoft-Windows-PowerShell/Operational", "event_id": "4103", "provider_name": "Microsoft-Windows-PowerShell",
                            "provider_guid": "{a0c1853b-5c40-4b15-8766-3cf1c58f985a}", "user": {"identifier": sid(user)}})
        d["tags"] = ["forwarded", "preserve_original_event"]
        return d
    d["user"] = {"id": sid(user), "name": user, "domain": CORP}
    d["related"] = {"user": [user]}
    d["winlog"].update({"channel": "Microsoft-Windows-PowerShell/Operational", "event_id": code, "provider_name": "Microsoft-Windows-PowerShell",
                        "provider_guid": "{a0c1853b-5c40-4b15-8766-3cf1c58f985a}", "user": {"identifier": sid(user)}})
    d["tags"] = ["forwarded", "preserve_original_event"]
    return d


# ---- Sysmon -------------------------------------------------------------------------------------------------------------------
IMAGES = [("C:\\Windows\\System32\\svchost.exe", "svchost.exe"), ("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "chrome.exe"),
          ("C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "powershell.exe"), ("C:\\Windows\\System32\\cmd.exe", "cmd.exe"),
          ("C:\\Windows\\System32\\wbem\\WmiPrvSE.exe", "WmiPrvSE.exe"), ("C:\\Program Files\\Microsoft SQL Server\\MSSQL16\\MSSQL\\Binn\\sqlservr.exe", "sqlservr.exe"),
          ("C:\\Windows\\explorer.exe", "explorer.exe"), ("C:\\Windows\\System32\\rundll32.exe", "rundll32.exe")]
DNS_Q = ["login.microsoftonline.com", "update.example.org", "files.corp.example.org", "api.github.com", "www.msn.com", "telemetry.example.net", "evil-c2.badhost.xyz"]
DEST_IPS = ["204.79.197.203", "20.190.159.4", "140.82.112.5", "13.107.42.14", "10.20.5.20", "10.20.7.8", "185.220.101.9"]


def _sysmon(c: Ctx) -> dict:
    r = c.rng
    host = _host(c)
    d = _base("windows/sysmon_operational", host, c.ts)
    code = profile.pick(r, {"1": 0.28, "3": 0.25, "22": 0.22, "11": 0.15, "13": 0.07, "7": 0.03})
    img, name = IMAGES[r.randrange(len(IMAGES))]
    user, _ = USERS[r.randrange(len(USERS))]
    pid = 500 + r.randrange(9000)
    guid = "{" + profile.uuid_for(r) + "}"
    names = {"1": ("Process Create (rule: ProcessCreate)", ["process"], ["start"]), "3": ("Network connection detected (rule: NetworkConnect)", ["network"], ["connection", "start", "protocol"]),
             "22": ("DNSEvent (DNS query)", ["network"], ["connection", "protocol", "info"]), "11": ("File created (rule: FileCreate)", ["file"], ["creation"]),
             "13": ("Registry value set (rule: RegistryEvent)", ["registry"], ["change"]), "7": ("Image loaded (rule: ImageLoad)", ["process"], ["change"])}
    act, cat, typ = names[code]
    d["event"].update({"code": code, "action": act, "category": cat, "type": typ, "kind": "event", "provider": "Microsoft-Windows-Sysmon", "dataset": S["windows/sysmon_operational"].dataset})
    d["log"] = {"level": "information"}
    for k in ("dns", "network", "sysmon", "related", "file", "destination", "source", "registry"):
        d.pop(k, None)
    d["process"] = {"entity_id": guid, "executable": img, "name": name, "pid": pid}
    d["user"] = {"id": "S-1-5-18" if name in ("svchost.exe", "WmiPrvSE.exe", "sqlservr.exe") else sid(user), "name": user, "domain": CORP}
    if code == "1":
        cl = f'"{img}" ' + r.choice(["-k netsvcs", "-NoProfile -File C:\\Scripts\\backup-nightly.ps1", "/c whoami /all", "--type=renderer", "-Embedding"])
        d["process"].update({"command_line": cl, "args": cl.replace('"', "").split(" "), "working_directory": "C:\\Windows\\System32\\", "parent": {"name": "services.exe", "pid": 668, "executable": "C:\\Windows\\System32\\services.exe", "entity_id": "{" + profile.uuid_for(r) + "}"},
                              "pe": {"original_file_name": name.upper()}, "hash": {"sha256": hashlib.sha256(img.encode()).hexdigest()}})
        d["sysmon"] = {"file": {"description": name, "product": "Microsoft Windows"}}
    elif code in ("3", "22"):
        if code == "3":
            dip = r.choice(DEST_IPS)
            d["network"] = {"protocol": "tcp", "transport": "tcp", "direction": "egress", "type": "ipv4"}
            d["source"] = {"ip": d_ip(host), "port": 49152 + r.randrange(16000)}
            d["destination"] = {"ip": dip, "port": r.choice([443, 443, 443, 80, 1433, 445, 53])}
            d["related"] = {"ip": [d["source"]["ip"], dip]}
        else:
            q = r.choice(DNS_Q)
            d["network"] = {"protocol": "dns"}
            d["dns"] = {"question": {"name": q, "registered_domain": ".".join(q.split(".")[-2:]), "top_level_domain": q.split(".")[-1]}, "resolved_ip": [r.choice(DEST_IPS)]}
            d["sysmon"] = {"dns": {"status": "SUCCESS"}}
            d["related"] = {"hosts": [q], "ip": d["dns"]["resolved_ip"]}
    elif code == "11":
        d["file"] = {"path": f"C:\\Users\\{user}\\AppData\\Local\\Temp\\tmp{r.randrange(9999)}.dat", "name": f"tmp{r.randrange(9999)}.dat"}
    elif code == "13":
        d["registry"] = {"path": "HKLM\\System\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\{1}\\DhcpIPAddress", "key": "HKLM\\System\\CurrentControlSet\\Services", "value": "DhcpIPAddress",
                         "data": {"strings": ["10.20.1.5"], "type": "SZ"}}
    d["winlog"].update({"channel": "Microsoft-Windows-Sysmon/Operational", "event_id": code, "opcode": "Info", "provider_name": "Microsoft-Windows-Sysmon",
                        "provider_guid": "{5770385f-c22a-43e0-bf4c-06f5698ffbd9}", "user": {"identifier": d["user"]["id"]}, "version": 5})
    d["tags"] = ["forwarded", "preserve_original_event"]
    return d


def d_ip(host: str) -> str:
    return infra.host_block(host, "windows")["ip"][0]


# ---- Defender ----------------------------------------------------------------------------------------------------------------
THREATS = [("Trojan:Win32/Detplock", "Severe", "Trojan", "1117", "malware-quarantined"), ("PUA:Win32/Presenoker", "Low", "Potentially Unwanted Software", "1116", "malware-detected"),
           ("Virus:DOS/EICAR_Test_File", "Severe", "Virus", "1116", "malware-detected"), ("Backdoor:Win32/Cobaltstrike", "Severe", "Backdoor", "1117", "malware-quarantined")]


def _defender(c: Ctx) -> dict:
    r = c.rng
    host = _host(c)
    d = _base("windows/windows_defender", host, c.ts)
    name, sev, cat, code, act = THREATS[r.randrange(len(THREATS))]
    user, _ = USERS[r.randrange(7)]
    path = f"C:\\Users\\{user}\\Downloads\\invoice_{r.randrange(9999)}.exe"
    d["event"].update({"code": code, "action": act, "category": ["malware"], "type": ["info"], "provider": "Microsoft-Windows-Windows Defender", "kind": "event",
                       "outcome": "success", "dataset": S["windows/windows_defender"].dataset})
    d["file"] = {"extension": "exe", "name": path.rsplit("\\", 1)[1], "path": path}
    d["log"] = {"level": "warning" if code == "1116" else "information"}
    d["message"] = f"Microsoft Defender Antivirus has taken action to protect this machine from malware or other potentially unwanted software.\n \tName: {name}\n \tSeverity: {sev}\n \tCategory: {cat}\n \tPath: file:_{path}"
    d["user"] = {"domain": CORP, "name": user}
    d["windows_defender"] = {"evidence_paths": [path]}
    d["winlog"].update({"channel": "Microsoft-Windows-Windows Defender/Operational", "event_id": code})
    d["winlog"].setdefault("event_data", {})
    d["winlog"]["event_data"].update({"Threat_Name": name, "Severity_Name": sev, "Category_Name": cat, "Path": f"file:_{path}"})
    d["tags"] = ["forwarded", "preserve_original_event"]
    return d


# ---- forwarded: Security logons, process creation (4688) and PowerShell ---------------------------------------------------------
def _forwarded(c: Ctx) -> dict:
    r = c.rng
    host = _host(c)
    d = _base("windows/forwarded", host, c.ts)
    code = profile.pick(r, {"4624": 0.42, "4625": 0.08, "4672": 0.15, "4688": 0.2, "4768": 0.08, "4720": 0.01, "4104": 0.06})
    if code == "4104":
        d = _ps_operational(c)
        d["event"]["dataset"] = S["windows/forwarded"].dataset
        return d
    user, _ = USERS[r.randrange(len(USERS))]
    ok = code != "4625"
    act = {"4624": "logged-in", "4625": "logon-failed", "4672": "logged-in-special", "4688": "created-process", "4768": "kerberos-authentication-ticket-requested", "4720": "added-user-account"}[code]
    cat = {"4624": ["authentication"], "4625": ["authentication"], "4672": ["iam", "authentication"], "4688": ["process"], "4768": ["authentication"], "4720": ["iam"]}[code]
    d["event"].update({"code": code, "action": act, "category": cat, "type": ["start"] if code in ("4688",) else ["info"], "kind": "event", "outcome": "success" if ok else "failure",
                       "provider": "Microsoft-Windows-Security-Auditing", "dataset": S["windows/forwarded"].dataset})
    d.pop("powershell", None)
    d["log"] = {"level": "information"}
    d["user"] = {"name": user, "domain": CORP, "id": sid(user)}
    d.pop("source", None)
    if code in ("4624", "4625", "4768"):
        d["source"] = {"ip": r.choice(["10.20.9.14", "10.20.9.77", "185.220.101.9"]), "port": 49152 + r.randrange(16000)}
    if code in ("4624", "4625"):
        d["winlog"]["logon"] = {"type": r.choice(["Network", "Interactive", "RemoteInteractive", "Service"]), "id": "0x%x" % r.randrange(1 << 20)}
        d["winlog"]["event_data"] = {"LogonType": "3", "AuthenticationPackageName": "NTLM" if code == "4625" else "Kerberos", "TargetUserName": user}
    if code == "4688":
        img, nm = IMAGES[r.randrange(len(IMAGES))]
        d["process"] = {"executable": img, "name": nm, "pid": 800 + r.randrange(9000), "command_line": f'"{img}"'}
    d["related"] = {"user": [user], "ip": [d["source"]["ip"]] if "source" in d else []}
    d["winlog"].update({"channel": "Security", "event_id": code, "provider_name": "Microsoft-Windows-Security-Auditing", "provider_guid": "{54849625-5478-4994-a5ba-3e3b0328c30d}",
                        "user": {"identifier": sid(user)}, "keywords": ["Audit Success" if ok else "Audit Failure"], "outcome": "success" if ok else "failure"})
    d["tags"] = ["forwarded", "preserve_original_event"]
    return d


N_SVC = SVC_PER_HOST * len(WINDOWS_HOSTS)
registry.register(
    GROUP,
    Generator(S["windows/service"], _service, mode="entities", entities=N_SVC, every_min=10),
    Generator(S["windows/perfmon"], _perfmon, mode="entities", entities=len(WINDOWS_HOSTS), every_min=5),
    Generator(S["windows/applocker_exe_and_dll"], _applocker("windows/applocker_exe_and_dll", "EXE", {"8002": 0.7, "8003": 0.2, "8004": 0.1}), rate_per_min=1.2),
    Generator(S["windows/applocker_msi_and_script"], _applocker("windows/applocker_msi_and_script", "SCRIPT", {"8005": 0.55, "8006": 0.3, "8007": 0.15}, True), rate_per_min=0.5),
    Generator(S["windows/applocker_packaged_app_deployment"], _applocker("windows/applocker_packaged_app_deployment", "PACKAGED_APP", {"8020": 0.6, "8021": 0.25, "8022": 0.15}, packaged=True), rate_per_min=0.15),
    Generator(S["windows/applocker_packaged_app_execution"], _applocker("windows/applocker_packaged_app_execution", "PACKAGED_APP", {"8023": 0.6, "8024": 0.25, "8025": 0.15}, packaged=True), rate_per_min=0.3),
    Generator(S["windows/powershell"], _ps_classic, rate_per_min=1.0),
    Generator(S["windows/powershell_operational"], _ps_operational, rate_per_min=1.2),
    Generator(S["windows/sysmon_operational"], _sysmon, rate_per_min=3.0),
    Generator(S["windows/windows_defender"], _defender, rate_per_min=0.08),
    Generator(S["windows/forwarded"], _forwarded, rate_per_min=2.5),
)
