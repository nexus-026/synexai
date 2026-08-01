import re
import socket
from typing import Dict, Any
import httpx


class NetworkEngine:
    """
    Network analysis engine.
    Performs basic network diagnostics without requiring root for most operations.
    """

    async def analyze(self, message: str) -> Dict[str, Any]:
        lower = message.lower()

        # Extract domain/IP
        m = re.search(r'(?:ping|traceroute|dns|whois|check|scan|is)\s+([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)', lower)
        target = m.group(1) if m else "google.com"

        if "ping" in lower or "up" in lower or "down" in lower or "reachable" in lower:
            return await self._ping_check(target)
        if "dns" in lower or "resolve" in lower:
            return await self._dns_lookup(target)
        if "whois" in lower:
            return await self._whois_lookup(target)
        if "ip" in lower and "my" in lower:
            return await self._my_ip()
        if "ssl" in lower or "cert" in lower:
            return await self._ssl_check(target)
        if "port" in lower or "open" in lower:
            return await self._port_scan(target)

        # Default: DNS + ping summary
        dns = await self._dns_lookup(target)
        ping = await self._ping_check(target)
        return {
            "success": True,
            "type": "network",
            "response": f"**Network Analysis for {target}**\n\n{dns.get('response', '')}\n\n{ping.get('response', '')}",
            "sources": [],
        }

    async def _ping_check(self, target: str) -> Dict[str, Any]:
        try:
            # HTTP-based reachability check (safer than ICMP in containers)
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.head(f"http://{target}", follow_redirects=True)
                return {
                    "success": True,
                    "type": "network",
                    "response": f"✅ **{target}** is reachable (HTTP {r.status_code}, latency ~{r.elapsed.total_seconds()*1000:.0f}ms).",
                    "data": {"status_code": r.status_code, "latency_ms": round(r.elapsed.total_seconds() * 1000, 2)},
                    "sources": [],
                }
        except Exception as e:
            return {
                "success": True,
                "type": "network",
                "response": f"❌ **{target}** appears unreachable via HTTP.\nError: {e}",
                "sources": [],
            }

    async def _dns_lookup(self, target: str) -> Dict[str, Any]:
        try:
            info = socket.getaddrinfo(target, None)
            ips = list(set([rec[4][0] for rec in info]))
            return {
                "success": True,
                "type": "network",
                "response": f"🌐 **DNS for {target}**\n\nResolved IPs:\n" + "\n".join([f"• {ip}" for ip in ips]),
                "data": {"ips": ips},
                "sources": [],
            }
        except Exception as e:
            return {
                "success": True,
                "type": "network",
                "response": f"❌ DNS lookup failed for {target}.\nError: {e}",
                "sources": [],
            }

    async def _whois_lookup(self, target: str) -> Dict[str, Any]:
        # Simplified whois via RDAP/whoisjson API
        try:
            url = f"https://rdap.org/domain/{target}"
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, headers={"Accept": "application/json"})
                if r.status_code == 200:
                    data = r.json()
                    events = data.get("events", [])
                    created = next((e.get("eventDate", "") for e in events if e.get("eventAction") == "registration"), "N/A")
                    expires = next((e.get("eventDate", "") for e in events if e.get("eventAction") == "expiration"), "N/A")
                    return {
                        "success": True,
                        "type": "network",
                        "response": f"📋 **WHOIS for {target}**\n\nCreated: {created}\nExpires: {expires}\nRegistrar: {data.get('entities',[{}])[0].get('vcardArray',[None,[]])[1][1][3] if data.get('entities') else 'N/A'}",
                        "sources": [{"title": "RDAP.org", "url": f"https://rdap.org/domain/{target}", "type": "api", "source": "RDAP"}],
                    }
        except Exception:
            pass
        return {
            "success": True,
            "type": "network",
            "response": f"📋 WHOIS lookup for {target} requires a dedicated WHOIS library or API key for full details.",
            "sources": [],
        }

    async def _my_ip(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("https://api.ipify.org?format=json")
                data = r.json()
                ip = data.get("ip", "unknown")
                return {
                    "success": True,
                    "type": "network",
                    "response": f"🌐 **Your Public IP:** {ip}",
                    "data": {"ip": ip},
                    "sources": [{"title": "ipify", "url": "https://www.ipify.org", "type": "api", "source": "ipify"}],
                }
        except Exception as e:
            return {
                "success": False,
                "type": "network",
                "response": f"Could not determine public IP: {e}",
                "sources": [],
            }

    async def _ssl_check(self, target: str) -> Dict[str, Any]:
        import ssl
        import certifi
        try:
            context = ssl.create_default_context(cafile=certifi.where())
            with socket.create_connection((target, 443), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=target) as ssock:
                    cert = ssock.getpeercert()
                    cipher = ssock.cipher()
                    version = ssock.version()
                    return {
                        "success": True,
                        "type": "network",
                        "response": (f"🔒 **SSL Certificate for {target}**\n\n"
                                     f"Version: {version}\n"
                                     f"Cipher: {cipher[0]}\n"
                                     f"Issuer: {cert.get('issuer', 'N/A')}\n"
                                     f"Not Before: {cert.get('notBefore', 'N/A')}\n"
                                     f"Not After: {cert.get('notAfter', 'N/A')}"),
                        "sources": [],
                    }
        except Exception as e:
            return {
                "success": True,
                "type": "network",
                "response": f"❌ SSL check failed for {target}: {e}",
                "sources": [],
            }

    async def _port_scan(self, target: str) -> Dict[str, Any]:
        # Lightweight port check on common ports
        common_ports = [80, 443, 22, 21, 25, 3306, 5432, 8080]
        open_ports = []
        for port in common_ports:
            try:
                with socket.create_connection((target, port), timeout=2):
                    open_ports.append(port)
            except Exception:
                pass
        return {
            "success": True,
            "type": "network",
            "response": f"🔌 **Port Scan for {target}**\n\nOpen ports: {', '.join(map(str, open_ports)) if open_ports else 'None detected among common ports.'}",
            "data": {"open_ports": open_ports},
            "sources": [],
        }
