import subprocess
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import re


def ping_ip(ip):
    try:
        result = subprocess.run(
            ["ping", "-c", "3", "-W", "1", ip], capture_output=True, text=True, timeout=3
        )
        output = result.stdout
        delay = 9999
        loss_rate = 100
        for line in output.splitlines():
            delay = re.findall(r"time=(\d+\.?\d*) ms", output)
            loss_match = re.search(r"(\d+)% packet loss", output)
            if not loss_match:
                return (None, None)
            loss_rate = int(loss_match.group(1))
            avg_delay = sum(float(t) for t in delay) / len(delay)
        return avg_delay, loss_rate
    except Exception:
        return 9999, 100


def check_port(ip):
    try:
        with socket.create_connection((ip, 443), timeout=2):
            return True
    except Exception:
        return False


def score_ip(avg_delay, loss_rate, port_accessibility):
    if loss_rate == 100 or not port_accessibility:
        return 0
    delay_score = max(0, 40 - (avg_delay / 5))
    loss_score = 40 * (1 - loss_rate / 100)
    port_score = 20 if port_accessibility else 0
    return delay_score + loss_score + port_score


def ping_c_segment(c_segment):
    base_ip = c_segment.split('/')[0]
    parts = base_ip.split('.')
    if parts[-1] == '0':
        parts[-1] = '1'
        base_ip = '.'.join(parts)
    return ping_ip(base_ip)


def select_top_c_segments(c_segments):
    results = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(ping_c_segment, c): c for c in c_segments}
        for future in as_completed(futures):
            c = futures[future]
            avg_delay, loss_rate = future.result()
            results.append((c, avg_delay, loss_rate))
    top = sorted(results, key=lambda x: x[1])[:5]
    return [c for c, _, _ in top]


def test_top_c_segments(c_segments):
    top5_c_segments = select_top_c_segments(c_segments)
    all_ips = []
    for c_segment in top5_c_segments:
        base_ip = c_segment.split('/')[0]
        all_ips.extend(
            [f"{'.'.join(base_ip.split('.')[:3])}.{i}" for i in range(1, 255)])
    scored = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = {executor.submit(ping_ip, ip): ip for ip in all_ips}
        ping_results = []
        for future in as_completed(futures):
            ip = futures[future]
            avg_delay, loss_rate = future.result()
            ping_results.append((ip, avg_delay, loss_rate))

    with ThreadPoolExecutor(max_workers=50) as executor:
        port_futures = {executor.submit(check_port, ip): (
            ip, avg_delay, loss_rate) for ip, avg_delay, loss_rate in ping_results}
        for future in as_completed(port_futures):
            ip, avg_delay, loss_rate = port_futures[future]
            port_accessibility = future.result()
            score = score_ip(avg_delay, loss_rate, port_accessibility)
            scored.append({
                'ip': ip,
                'score': score,
                'avg_delay': avg_delay,
                'loss_rate': loss_rate
            })
    top = sorted(scored, key=lambda x: x['score'], reverse=True)[:15]
    return top, top5_c_segments
