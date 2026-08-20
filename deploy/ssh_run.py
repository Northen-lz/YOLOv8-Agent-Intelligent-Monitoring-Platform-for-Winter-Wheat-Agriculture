# -*- coding: utf-8 -*-
"""SSH 远程执行辅助（paramiko）。用法:
    python ssh_run.py "要执行的命令"
    python ssh_run.py --upload 本地文件 远端路径

环境变量: HA_SSH_HOST / HA_SSH_USER / HA_SSH_PASS（缺省自动提示输入）
"""
import os
import sys
import getpass
import paramiko


def _connect():
    host = os.environ.get("HA_SSH_HOST", "47.99.91.10")
    user = os.environ.get("HA_SSH_USER", "root")
    pwd = os.environ.get("HA_SSH_PASS", "")
    if not pwd:
        pwd = getpass.getpass(f"{user}@{host} password: ")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=pwd, timeout=20)
    return client


def _run(client, cmd, timeout=3600):
    chan = client.get_transport().open_session()
    chan.get_pty()
    chan.settimeout(timeout)
    chan.exec_command(cmd)
    out = b""
    while True:
        try:
            chunk = chan.recv(8192)
        except Exception:
            break
        if not chunk:
            break
        out += chunk
        sys.stdout.write(chunk.decode(errors="replace"))
        sys.stdout.flush()
    rc = chan.recv_exit_status()
    client.close()
    print(f"\n[exit {rc}]")
    return rc


def _upload(client, local, remote):
    # paramiko 5.0 的 sftp.put 在部分服务器上打开远端文件时报 ENOENT，
    # 改为 open()+分块写入（实测稳定）
    sftp = client.open_sftp()
    size = os.path.getsize(local)
    sent = 0
    with sftp.open(remote, "wb") as f:
        with open(local, "rb") as src:
            while True:
                b = src.read(1 << 20)
                if not b:
                    break
                f.write(b)
                sent += len(b)
    sftp.close()
    client.close()
    print(f"[upload] {local} -> {remote} ({sent}/{size} bytes)")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--upload":
        client = _connect()
        _upload(client, args[1], args[2])
    elif args:
        client = _connect()
        sys.exit(_run(client, args[0]))
    else:
        print("用法: python ssh_run.py '命令' | python ssh_run.py --upload <本地> <远端>")


if __name__ == "__main__":
    main()
