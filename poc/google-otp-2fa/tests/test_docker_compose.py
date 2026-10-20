import re
from pathlib import Path


def test_only_nginx_publishes_host_ports():
    text = (Path(__file__).parents[1] / "docker-compose.yml").read_text()
    # Collect services that define host port mappings (lines like "8080:80")
    blocks = re.split(r"\n(?=\S)", text)
    for block in blocks:
        name = block.split(":", 1)[0].strip()
        if name in ("legacy-web", "mfa-adapter", "mfa-service", "privacyidea", "pi-db"):
            assert "ports:" not in block, f"{name} must not expose host ports"
    assert re.search(r"nginx-proxy:[\s\S]*?ports:\s*\n\s*-\s*[\"']?8080:80", text)
