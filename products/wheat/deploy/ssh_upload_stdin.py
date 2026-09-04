# -*- coding: utf-8 -*-
"""stdin 流式上传文件到服务器（绕开两个坑）：
1) paramiko 5.0 的 sftp.open(remote,"wb") 偶发 ENOENT（目录存在也报错）
2) base64 整包塞进命令行参数会触发 "Argument list too long"

用法（环境变量同 ssh_run.py）:
    python ssh_upload_stdin.py <本地文件> <远端路径> [远端后续命令(&& 链)]

示例（monorepo 拆分后服务器布局 = /opt/hello-agents/{wheat,ha_framework}/…）:
    python ssh_upload_stdin.py wheat/app.py /opt/hello-agents/wheat/app.py \
        "chown www-data:www-data /opt/hello-agents/wheat/app.py && systemctl restart hello-agents"
"""
import os
import sys

import paramiko


def main():
    local, remote = sys.argv[1], sys.argv[2]
    post = sys.argv[3] if len(sys.argv) > 3 else None

    host = os.environ.get("HA_SSH_HOST", "47.99.91.10")
    user = os.environ.get("HA_SSH_USER", "root")
    pwd = os.environ.get("HA_SSH_PASS", "")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=pwd, timeout=20)

    chan = client.get_transport().open_session()
    chan.settimeout(3600)
    cmd = f"umask 022; cat > '{remote}'"
    if post:
        cmd += " && " + post
    chan.exec_command(cmd)

    # 本地文件字节流经 stdin 写入远端 `cat` 管道
    with open(local, "rb") as f:
        while True:
            b = f.read(1 << 16)
            if not b:
                break
            chan.sendall(b)
    chan.shutdown("write")

    out = b""
    while True:
        try:
            chunk = chan.recv(8192)
        except Exception:
            break
        if not chunk:
            break
        out += chunk
    sys.stdout.write(out.decode(errors="replace"))
    size = os.path.getsize(local)
    print(f"\n[upload-stdin] {local} -> {remote} ({size} bytes)")
    sys.exit(chan.recv_exit_status())


if __name__ == "__main__":
    main()
