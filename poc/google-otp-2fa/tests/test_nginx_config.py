import shutil
import subprocess
from pathlib import Path


def test_nginx_config_syntax():
    nginx = shutil.which("nginx")
    if not nginx:
        return  # documented as static-only check skipped
    conf = Path(__file__).parents[1] / "nginx" / "nginx.conf"
    # Syntax check needs resolvable upstream names; use offline stub
    stub = conf.read_text()
    stub = stub.replace("legacy-web:5000", "127.0.0.1:59999")
    stub = stub.replace("mfa-service:5001", "127.0.0.1:59998")
    stub = "\n".join(
        line for line in stub.splitlines() if not line.strip().startswith("pid ")
    )
    tmp = Path("/tmp/nginx-poc-test.conf")
    tmp.write_text(stub)
    proc = subprocess.run(
        [nginx, "-t", "-c", str(tmp), "-g", "pid /tmp/nginx-poc.pid;"],
        capture_output=True,
        text=True,
    )
    assert "syntax is ok" in proc.stderr or "syntax is ok" in proc.stdout
