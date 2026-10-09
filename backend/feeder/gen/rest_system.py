"""SYSTEM integration: Linux auth log (system.auth, RAW syslog lines), Windows Security events (system.security, winlogbeat
shaped raw events that the package pipeline maps to ECS) and system.memory with swap (Host overview "Swap usage").

Windows Security: a small domain (CORP) with a domain controller, a file server and workstations. Each event code carries the
event_data keys of the real Windows event; the package pipeline `logs-system.security-2.23.0` produces user.*, group.*, source.*,
file.path, rule.* ... from them. The codes are the ones the six Windows Security dashboards filter on.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from .. import profile, registry
from ..registry import Ctx, Generator
from . import infra, rest

AUTH = rest.S["system/auth"]
SEC = rest.S["system/security"]
MEM = rest.S["system/memory"]
LINUX_HOSTS = ["web-sin-01", "web-sin-02", "db-sin-01", "bastion-sin-01"]
DOMAIN, DNS = "CORP", "corp.example.org"
SID_BASE = "S-1-5-21-3623811015-3361044348-30300820"
HOSTS = [("WIN-DC01", "dc"), ("WIN-DC02", "dc"), ("WIN-FS01", "srv"), ("WIN-APP01", "srv"), ("WIN-WKS07", "wks"), ("WIN-WKS12", "wks")]
USERS = ["alice.martin", "bob.chen", "carol.novak", "dave.okafor", "erin.ito", "frank.silva", "grace.haddad", "heidi.kowalski", "ivan.reyes", "judy.tan",
         "svc-backup", "svc-sql", "administrator", "helpdesk01"]
ADMINS = ["administrator", "svc-backup", "helpdesk01"]
GROUPS = ["Domain Admins", "Server Operators", "Backup Operators", "Remote Desktop Users", "Finance-RW", "Engineering", "VPN-Users", "Helpdesk"]
EXT_IPS = ["185.220.101.9", "175.16.199.0", "81.2.69.142", "89.160.20.112", "216.160.83.56"]


def _sid(name: str) -> str:
    return f"{SID_BASE}-{1000 + infra.stable(name) % 9000}"


# ------------------------------------------------ Linux auth.log (raw syslog lines) -----------------------------------------------
NEW_USERS = ["jdoe", "mnguyen", "deploy", "analyst2", "svc-monitor", "tester07", "kpatel", "backup-op"]
SHELLS = ["/bin/bash", "/bin/bash", "/bin/sh", "/usr/sbin/nologin", "/bin/zsh"]


def _auth(c: Ctx) -> dict:
    r = c.rng
    host = LINUX_HOSTS[r.randrange(len(LINUX_HOSTS))]
    ts = f"{c.ts:%b} {c.ts.day:2d} {c.ts:%H:%M:%S}"
    pid = r.randrange(500, 30000)
    user = r.choice(["alice", "bob", "carol", "dave", "deploy", "ops"])
    k = r.random()
    if k < 0.12:
        n = r.randrange(1001, 1100)
        name = r.choice(NEW_USERS) + str(r.randrange(10))
        if r.random() < 0.5:
            line = f"{ts} {host} useradd[{pid}]: new user: name={name}, UID={n}, GID={n}, home=/home/{name}, shell={r.choice(SHELLS)}"
        else:
            line = f"{ts} {host} groupadd[{pid}]: new group: name={r.choice(['developers', 'ops', 'audit', 'docker', name])}, GID={n}"
    elif k < 0.22:
        line = f"{ts} {host} groupadd[{pid}]: new group: name={r.choice(['developers', 'ops', 'audit', 'docker'])}{r.randrange(10)}, GID={r.randrange(1100, 1200)}"
    elif k < 0.40:
        cmd = r.choice(["/bin/cat /etc/shadow", "/usr/bin/vi /etc/ssh/sshd_config", "/sbin/reboot", "/usr/bin/rm -rf /var/lib/app"])
        err = r.choice(["user NOT in sudoers", "3 incorrect password attempts", "command not allowed"])
        line = f"{ts} {host} sudo:    {user} : {err} ; TTY=pts/{r.randrange(4)} ; PWD=/home/{user} ; USER=root ; COMMAND={cmd}"
    elif k < 0.55:
        cmd = r.choice(["/usr/bin/apt update", "/bin/systemctl restart nginx", "/usr/bin/journalctl -u sshd", "/usr/bin/docker ps"])
        line = f"{ts} {host} sudo:    {user} : TTY=pts/{r.randrange(4)} ; PWD=/home/{user} ; USER=root ; COMMAND={cmd}"
    elif k < 0.80:
        ip = r.choice(EXT_IPS + ["10.20.9.14", "10.20.9.77"])
        if r.random() < 0.55:
            method = r.choices(["publickey", "password", "keyboard-interactive/pam"], weights=[6, 3, 1])[0]
            tail = " RSA SHA256:" + hashlib.sha256(user.encode()).hexdigest()[:43] if method == "publickey" else ""
            line = f"{ts} {host} sshd[{pid}]: Accepted {method} for {user} from {ip} port {r.randrange(20000, 60000)} ssh2{':' + tail if tail else ''}"
        else:
            who = r.choice(["invalid user admin", "invalid user oracle", "root", user])
            line = f"{ts} {host} sshd[{pid}]: Failed password for {who} from {ip} port {r.randrange(20000, 60000)} ssh2"
    else:
        line = f"{ts} {host} sshd[{pid}]: pam_unix(sshd:session): session opened for user {user}(uid={r.randrange(1000, 1010)}) by (uid=0)"
    d = infra.log_base(host, "/var/log/auth.log")
    d["message"] = line
    d["event"] = {"timezone": "+00:00"}
    return d


# ------------------------------------------------ Windows Security -------------------------------------------------------------
class St:
    """Per event state: who did it, where, to whom."""

    def __init__(self, c: Ctx):
        r = c.rng
        self.r = r
        self.c = c
        self.host, self.kind = HOSTS[r.randrange(len(HOSTS))]
        self.subj = r.choice(ADMINS) if r.random() < 0.5 else r.choice(USERS)
        self.tgt = r.choice(USERS)
        self.new = r.choice(["tmp.contractor", "new.hire", "intern.sg", "svc-deploy", "lab.user"]) + str(r.randrange(100))
        self.group = r.choice(GROUPS)
        self.ip = r.choice(EXT_IPS) if r.random() < 0.12 else f"10.20.9.{r.randrange(10, 90)}"
        self.logon = "0x%x" % r.randrange(0x20000, 0x9fffff)
        self.pid = r.randrange(400, 9000)

    def v(self, key: str):
        r, s = self.r, self
        dn = lambda n: f"CN={n},OU=Staff,DC=corp,DC=example,DC=org"  # noqa: E731
        t = {
            "SubjectUserSid": _sid(s.subj), "SubjectUserName": s.subj, "SubjectDomainName": DOMAIN, "SubjectLogonId": s.logon,
            "TargetUserSid": _sid(s.tgt), "TargetUserName": s.tgt, "TargetDomainName": DOMAIN, "TargetLogonId": "0x%x" % r.randrange(0x20000, 0x9fffff),
            "TargetSid": _sid(s.tgt), "TargetServerName": "localhost", "TargetInfo": "localhost", "TargetDomainSid": SID_BASE,
            "LogonType": str(r.choices([2, 3, 7, 10, 5], weights=[3, 8, 2, 3, 1])[0]), "LogonProcessName": r.choice(["NtLmSsp ", "Kerberos", "User32 "]),
            "AuthenticationPackageName": r.choice(["NTLM", "Kerberos", "Negotiate"]), "WorkstationName": r.choice([h for h, _k in HOSTS]), "LogonGuid": "{00000000-0000-0000-0000-000000000000}",
            "TransmittedServices": "-", "LmPackageName": "NTLM V2", "KeyLength": "128", "ProcessId": "0x%x" % s.pid, "ProcessName": r.choice(
                ["C:\\Windows\\System32\\lsass.exe", "C:\\Windows\\System32\\svchost.exe", "C:\\Windows\\explorer.exe", "C:\\Program Files\\App\\app.exe"]),
            "IpAddress": s.ip, "IpPort": str(r.randrange(49152, 65000)), "ImpersonationLevel": "%%1833", "RestrictedAdminMode": "-", "TargetOutboundUserName": "-",
            "TargetOutboundDomainName": "-", "VirtualAccount": "%%1843", "TargetLinkedLogonId": "0x0", "ElevatedToken": "%%1842",
            "Status": "0xc000006d", "SubStatus": r.choice(["0xc000006a", "0xc0000064", "0xc0000234"]), "FailureReason": "%%2313",
            "PrivilegeList": "SeSecurityPrivilege\r\n\t\t\tSeBackupPrivilege\r\n\t\t\tSeRestorePrivilege\r\n\t\t\tSeTakeOwnershipPrivilege",
            "ObjectServer": r.choice(["Security", "DS"]), "ObjectType": r.choice(["File", "Key", "Process"]), "HandleId": "0x%x" % r.randrange(0x100, 0xfff),
            "AccessList": "%%4416\r\n\t\t\t\t", "AccessMask": "0x1", "OperationType": "Object Access",
            "ObjectName": r.choice(["C:\\Shares\\Finance\\budget-2026.xlsx", "C:\\Shares\\HR\\payroll.csv", "C:\\Windows\\System32\\config\\SAM", "\\REGISTRY\\MACHINE\\SOFTWARE\\Policies"]),
            "MemberName": dn(s.tgt), "MemberSid": _sid(s.tgt), "OldTargetUserName": s.tgt, "NewTargetUserName": s.new,
            "SamAccountName": s.tgt, "DisplayName": s.tgt.replace(".", " ").title(), "UserPrincipalName": f"{s.tgt}@{DNS}", "PrimaryGroupId": "513",
            "OldUacValue": "0x15", "NewUacValue": "0x10", "UserAccountControl": "%%2080", "PasswordLastSet": "%%1794", "AccountExpires": "%%1794",
            "CallerProcessName": "C:\\Windows\\System32\\lsass.exe", "Workstation": r.choice([h for h, _k in HOSTS]),
            "StatusDescription": r.choice(["Success", "Success", "Password does not meet complexity", "Password too short", "Password history violation"]),
            "StatusCode": r.choice(["0", "0", "0", "8453", "8438"]), "Options": r.choice(["0", "1", "16", "2", "20"]), "ClassName": r.choice(["USB", "DiskDrive", "HIDClass", "Net", "Printer"]),
            "LocationInformation": r.choice(["Port_#0001.Hub_#0003", "Port_#0002.Hub_#0001", "PCI bus 0, device 20, function 0"]), "DeviceId": "USB\\VID_0781&PID_5581\\4C5300",
            "DeviceDescription": r.choice(["USB Mass Storage Device", "Logitech HID Keyboard", "HP LaserJet"]), "ClassId": "{36fc9e60-c465-11cf-8056-444553540000}",
            "Operation": r.choice(["Machine", "Local", "Domain"]), "ProviderName": r.choice(["Microsoft Software Key Storage Provider", "Microsoft Enhanced Cryptographic Provider v1.0"]),
            "ObjectClass": r.choice(["user", "group", "computer", "organizationalUnit", "groupPolicyContainer"]), "ObjectDN": dn(s.tgt), "ObjectGUID": "{" + "%032x" % r.getrandbits(128) + "}",
            "AttributeLDAPDisplayName": r.choice(["userAccountControl", "memberOf", "description", "scriptPath", "adminCount", "msDS-AllowedToDelegateTo"]),
            "AttributeValue": "512", "OpCorrelationID": "{" + "%032x" % r.getrandbits(128) + "}", "AppCorrelationID": "-", "DSName": DNS, "DSType": "%%14676",
            "FileName": r.choice(["C:\\Shares\\Finance\\q3.xlsx", "C:\\Users\\Public\\data.bin"]), "LinkName": "C:\\Shares\\Finance\\q3-link.xlsx", "SourceProcessId": "0x%x" % s.pid,
            "TargetProcessId": "0x%x" % r.randrange(400, 9000), "FailureReasonsOutcome": "0", "FilterType": r.choice(["%%14595", "%%14592"]),
            "FilterName": r.choice(["Block Outbound SMB", "Allow DNS", "Default Outbound"]), "ChangeType": r.choice(["%%5448", "%%5449", "%%5450"]), "ProviderContextName": "Microsoft Windows Firewall",
            "ProfileUsed": r.choice(["0x1", "0x2", "0x4"]), "RuleId": "{" + "%032x" % r.getrandbits(128) + "}", "RuleName": r.choice(["Core Networking - DNS (UDP-Out)", "Remote Desktop - User Mode (TCP-In)", "File and Printer Sharing (SMB-In)"]),
            "Direction": "%%14593", "SourceAddress": s.ip, "SourcePort": str(r.randrange(49152, 65000)), "Protocol": "6", "TdoDirection": r.choice(["1", "2", "3"]), "FailureReason": "0x0", "RemoteAddress": s.ip, "AccountName": s.tgt, "AccountDomain": DOMAIN,
            "ClientAddress": s.ip, "ClientName": r.choice([h for h, _k in HOSTS]), "param1": r.choice(["C:\\Windows\\System32\\drivers\\unsigned.sys", "C:\\Program Files\\App\\plugin.dll"]), "param2": "\\Device\\HarddiskVolume3", "SidList": "-",
            "GroupMembership": "%{S-1-5-21-1}\r\n\t\t\t%{S-1-5-32-544}", "EventIdx": "1", "EventCountTotal": "1", "ServiceName": "krbtgt", "TicketOptions": "0x40810010", "TicketEncryptionType": "0x12",
            "Properties": "%{bf967a86-0de6-11d0-a285-00aa003049e2}", "AccessGranted": "1", "GroupType": "-2147483646",
        }
        return t.get(key, "-")


def _keys(*parts: str) -> list[str]:
    out: list[str] = []
    for p in parts:
        out += FAMILIES.get(p, [p])
    return out


FAMILIES = {
    "subj": ["SubjectUserSid", "SubjectUserName", "SubjectDomainName", "SubjectLogonId"],
    "tgt": ["TargetUserSid", "TargetUserName", "TargetDomainName"],
    "acct": ["SamAccountName", "DisplayName", "UserPrincipalName", "PrimaryGroupId", "OldUacValue", "NewUacValue", "UserAccountControl", "PasswordLastSet", "AccountExpires"],
    "grp": ["TargetUserName", "TargetDomainName", "TargetSid", "SamAccountName", "GroupType"],
    "member": ["MemberName", "MemberSid"],
    "net": ["IpAddress", "IpPort"],
    "proc": ["ProcessId", "ProcessName"],
    "obj": ["ObjectServer", "ObjectType", "ObjectName", "HandleId"],
    "ad": ["OpCorrelationID", "AppCorrelationID", "DSName", "DSType", "ObjectDN", "ObjectGUID", "ObjectClass"],
    "fw": ["ProfileUsed", "RuleId", "RuleName"],
}
# code -> (event_data keys, weight). Weights: logons and privilege use dominate, rare AD and crypto events keep the dashboards populated.
SPEC: dict[str, tuple[list[str], float]] = {
    "4624": (_keys("subj", "TargetUserSid", "TargetUserName", "TargetDomainName", "TargetLogonId", "LogonType", "LogonProcessName", "AuthenticationPackageName", "WorkstationName", "LogonGuid",
                   "TransmittedServices", "LmPackageName", "KeyLength", "proc", "net", "ImpersonationLevel", "RestrictedAdminMode", "TargetOutboundUserName", "TargetOutboundDomainName", "VirtualAccount",
                   "TargetLinkedLogonId", "ElevatedToken"), 30),
    "4625": (_keys("subj", "tgt", "Status", "FailureReason", "SubStatus", "LogonType", "LogonProcessName", "AuthenticationPackageName", "WorkstationName", "TransmittedServices", "LmPackageName", "KeyLength",
                   "proc", "net"), 6),
    "4627": (_keys("subj", "tgt", "TargetLogonId", "LogonType", "EventIdx", "EventCountTotal", "GroupMembership"), 3),
    "4634": (_keys("tgt", "TargetLogonId", "LogonType"), 8), "4647": (_keys("tgt", "TargetLogonId"), 2),
    "4648": (_keys("subj", "LogonGuid", "TargetUserName", "TargetDomainName", "TargetServerName", "TargetInfo", "proc", "net"), 3),
    "4658": (_keys("subj", "ObjectServer", "HandleId", "proc"), 1),
    "4659": (_keys("subj", "obj", "proc"), 0.4), "4660": (_keys("subj", "obj", "proc"), 0.8),
    "4662": (_keys("subj", "ObjectServer", "OperationType", "ObjectType", "ObjectName", "HandleId", "AccessList", "AccessMask", "Properties"), 3),
    "4663": (_keys("subj", "obj", "AccessList", "AccessMask", "proc"), 4), "4664": (_keys("subj", "FileName", "LinkName", "ProcessId"), 0.3),
    "4672": (_keys("subj", "PrivilegeList"), 10), "4675": (_keys("subj", "TargetUserSid", "TargetDomainSid", "TdoDirection"), 0.5),
    "4690": (_keys("subj", "SourceProcessId", "TargetProcessId"), 0.5), "4691": (_keys("subj", "ObjectServer", "ObjectType", "ObjectName", "HandleId"), 0.5),
    "4692": (_keys("subj", "FailureReason"), 0.3), "4695": (_keys("subj", "FailureReason"), 0.5),
    "4704": (_keys("subj", "TargetSid", "PrivilegeList"), 0.5), "4705": (_keys("subj", "TargetSid", "PrivilegeList"), 0.5),
    "4720": (_keys("subj", "tgt", "acct"), 1), "4722": (_keys("subj", "tgt", "TargetSid"), 1), "4723": (_keys("subj", "tgt"), 1), "4724": (_keys("subj", "tgt"), 1),
    "4725": (_keys("subj", "tgt"), 1), "4726": (_keys("subj", "tgt"), 0.6), "4738": (_keys("subj", "tgt", "acct"), 1.5), "4740": (_keys("tgt", "SubjectUserSid", "SubjectUserName", "SubjectDomainName", "SubjectLogonId"), 1),
    "4767": (_keys("subj", "tgt"), 0.6), "4771": (_keys("tgt", "ServiceName", "TicketOptions", "Status", "net"), 2), "4781": (_keys("subj", "OldTargetUserName", "NewTargetUserName", "TargetDomainName"), 0.6),
    "4778": (_keys("subj", "AccountName", "AccountDomain", "ClientAddress", "ClientName"), 1), "4779": (_keys("subj", "AccountName", "AccountDomain", "ClientAddress", "ClientName"), 1),
    "4793": (_keys("subj", "Workstation", "tgt", "StatusDescription"), 1), "4798": (_keys("subj", "tgt", "CallerProcessName", "proc"), 2), "4799": (_keys("subj", "grp", "CallerProcessName", "proc"), 2),
    "4800": (_keys("tgt", "TargetLogonId"), 2), "4801": (_keys("tgt", "TargetLogonId"), 2),
    "4868": (_keys("subj", "tgt"), 0.1), "4869": (_keys("subj", "tgt"), 0.1), "4876": (_keys("subj"), 0.1),
    "4931": (_keys("subj", "Options", "StatusCode", "DSName", "ObjectDN"), 0.5), "4932": (_keys("subj", "Options", "DSName", "ObjectDN"), 0.6), "4933": (_keys("subj", "Options", "StatusCode", "DSName", "ObjectDN"), 0.6),
    "4945": (_keys("ProfileUsed", "RuleId", "RuleName"), 0.8), "4953": (_keys("fw"), 0.4), "4957": (_keys("fw"), 0.4),
    "4962": (_keys("RemoteAddress", "SourceAddress", "SourcePort"), 0.4), "4963": (_keys("RemoteAddress", "SourceAddress"), 0.4), "4965": (_keys("RemoteAddress", "SourceAddress"), 0.4),
    "5038": (_keys("param1", "param2"), 0.3), "5058": (_keys("subj", "ProviderName", "Operation"), 0.5), "5059": (_keys("subj", "ProviderName", "Operation"), 0.4), "5061": (_keys("subj", "ProviderName", "Operation"), 0.8),
    "5136": (_keys("subj", "ad", "AttributeLDAPDisplayName", "AttributeValue", "OperationType"), 3), "5441": (_keys("ProfileUsed", "FilterType", "FilterName"), 0.4), "5446": (_keys("ProviderContextName", "ChangeType"), 0.4),
    "5447": (_keys("ProviderContextName", "FilterName", "ChangeType"), 0.4), "5449": (_keys("ProviderContextName", "ChangeType"), 0.4),
    "6416": (_keys("subj", "DeviceId", "DeviceDescription", "ClassId", "ClassName", "LocationInformation"), 1), "6419": (_keys("subj", "DeviceId", "DeviceDescription", "ClassName"), 0.5),
    "6420": (_keys("subj", "DeviceId", "DeviceDescription", "ClassName"), 0.5), "6421": (_keys("subj", "DeviceId", "DeviceDescription", "ClassName"), 0.5), "6422": (_keys("subj", "DeviceId", "DeviceDescription", "ClassName"), 0.5),
}
# account management events handled by group
for _c in list(range(4727, 4765)) + [4744, 4745, 4746, 4747, 4748, 4749, 4750, 4751, 4752, 4753, 4754, 4755, 4756, 4757, 4758, 4759, 4760, 4761, 4762, 4763, 4764]:
    SPEC.setdefault(str(_c), (_keys("subj", "grp", "member"), 0.5))
for _c in (4783, 4784, 4785, 4786, 4787, 4788, 4789, 4790, 4791, 4792):
    SPEC.setdefault(str(_c), (_keys("subj", "grp", "member"), 0.3))
for _c in (4731, 4732, 4733, 4728, 4729, 4756, 4757):
    SPEC[str(_c)] = (_keys("subj", "grp", "member"), 1.2)
FAIL_CODES = {"4625", "4771", "4776"}
SEC_CODES = list(SPEC)
SEC_WEIGHTS = [SPEC[k][1] for k in SEC_CODES]
GUID = {"4624": "{54849625-5478-4994-a5ba-3e3b0328c30d}"}


def _security(c: Ctx, code: str | None = None) -> dict:
    r = c.rng
    code = code or r.choices(SEC_CODES, weights=SEC_WEIGHTS)[0]
    st = St(c)
    host = f"{st.host}.{DNS}"
    keys, _w = SPEC[code]
    ed = {k: st.v(k) for k in keys}
    if code == "4625":
        ed["TargetUserName"] = r.choice(USERS + ["admin", "guest", "sqlsvc"])
        ed["LogonType"] = r.choice(["3", "3", "10", "2"])
    d = {"winlog": {"api": "wineventlog", "channel": "Security", "computer_name": host, "event_id": code, "keywords": ["Audit Failure" if code in FAIL_CODES else "Audit Success"],
                    "opcode": "Info", "process": {"pid": 628, "thread": {"id": r.randrange(700, 9000)}}, "provider_guid": GUID.get(code, "{54849625-5478-4994-a5ba-3e3b0328c30d}"),
                    "provider_name": "Microsoft-Windows-Security-Auditing", "record_id": str(r.randrange(10_000, 99_000_000)), "task": "Logon", "event_data": ed,
                    "time_created": profile.iso(c.ts)},
         "event": {"code": code, "provider": "Microsoft-Windows-Security-Auditing", "outcome": "failure" if code in FAIL_CODES else "success"},
         "host": {"name": host}, "log": {"level": "information"}, "input": {"type": "winlog"}, "tags": ["preserve_original_event"],
         "agent": infra.agent_block(st.host, "filebeat"), "message": f"Windows Security event {code} on {host}"}
    return d


# ------------------------------------------------ system.memory with swap ---------------------------------------------------------
MEM_HOSTS = [(h, 8 << 30 if h.startswith("web") else 16 << 30) for h in ("web-sin-01", "web-sin-02", "db-sin-01", "bastion-sin-01")]


def _memory(c: Ctx) -> dict:
    name, total = MEM_HOSTS[c.i % len(MEM_HOSTS)]
    r = c.rng
    pct = min(0.95, 0.35 + 0.3 * min(c.load, 1.5) / 1.5 + 0.05 * infra.wave(c.ts, 300, 1.0, name) / 2 + r.uniform(0, 0.02))
    used = int(total * pct)
    swap_total = 2 << 30
    swap_pct = min(0.9, max(0.0, (pct - 0.55) * 1.2 + r.uniform(0.01, 0.06)))
    swap_used = int(swap_total * swap_pct)
    cached = int(total * 0.22)
    d = {"agent": infra.agent_block(name, "metricbeat"), "ecs": {"version": "8.0.0"}, "event": {"dataset": "system.memory", "duration": r.randrange(150000, 500000), "module": "system"},
         "host": {**infra.host_block(name)}, "metricset": {"name": "memory", "period": 10000}, "service": {"type": "system"},
         "system": {"memory": {"actual": {"free": total - used + cached, "used": {"bytes": used - cached, "pct": round((used - cached) / total, 4)}}, "cached": cached, "free": total - used,
                               "swap": {"free": swap_total - swap_used, "total": swap_total, "used": {"bytes": swap_used, "pct": round(swap_pct, 4)}}, "total": total,
                               "used": {"bytes": used, "pct": round(pct, 4)}}}}
    return d


registry.register(rest.GROUP, Generator(AUTH, _auth, rate_per_min=1.0), Generator(SEC, _security, rate_per_min=3.0),
                  Generator(MEM, _memory, mode="entities", entities=len(MEM_HOSTS), every_min=10))
