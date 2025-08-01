import os
import json
import time
import requests
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed
import geoip2.database

from config import *
from ip_test import test_top_c_segments


def get_cidr_list():
    try:
        resp = requests.get(API_URL, timeout=TIMEOUT)
        if resp.status_code == 200:
            return [line.strip() for line in resp.text.splitlines() if line.strip()]
    except Exception as e:
        print(f"CIDR获取失败: {str(e)}")
    return []


def cidr_to_c_segments(cidr):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        mask = network.prefixlen
        first = int(network.network_address)
        last = int(network.broadcast_address)
        c_segments = set()
        for ip_int in range(first, last + 1):
            ip_str = str(ipaddress.IPv4Address(ip_int))
            c = '.'.join(ip_str.split('.')[:3]) + '.0'
            c_segments.add(f"{c}/{mask}")
        return list(c_segments)
    except:
        return []


def get_ip_country(ip, geo_reader):
    try:
        response = geo_reader.country(ip)
        return response.country.name or "Unknown"
    except Exception:
        return "Unknown"


def save_to_json(results, filename):
    country_dict = {}
    for ip, country in results:
        country_dict.setdefault(country, []).append(ip)
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(country_dict, f, ensure_ascii=False, indent=2)


def main(output='json'):
    start_time = time.time()
    if not os.path.exists(GEOIP_DB_FILE):
        url = LOCAL_DB_URL
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(GEOIP_DB_FILE, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        except Exception as e:
            print(f"数据库获取失败: {str(e)}")
            return

    geo_reader = geoip2.database.Reader(GEOIP_DB_FILE)
    cidr_list = get_cidr_list()
    if not cidr_list:
        return

    all_c_segments = set()
    for cidr in cidr_list:
        all_c_segments.update(cidr_to_c_segments(cidr))

    results = []
    with ThreadPoolExecutor(max_workers=THREADS//2) as executor:
        futures = {executor.submit(get_ip_country, c.split(
            '/')[0], geo_reader): c for c in all_c_segments}
        for future in as_completed(futures):
            c_with_mask = futures[future]
            country = future.result()
            if country in TARGET_REGION:
                results.append((c_with_mask, country))

    c_segments = [c for c, country in results]

    top_ips, top_c_segments = test_top_c_segments(c_segments)
    if output == 'json':
        save_to_json(results, 'as_cdn_ips.json')
        with open('top_cdn_ips.json', 'w', encoding='utf-8') as f:
            json.dump(top_ips, f, ensure_ascii=False, indent=2)
        with open('top_cdn_c_segments.json', 'w', encoding='utf-8') as f:
            json.dump(top_c_segments, f, ensure_ascii=False, indent=2)
    total_time = time.time() - start_time
    print(f"CDN节点测速完成，共 {len(c_segments)} 个C段，耗时 {total_time:.2f} 秒）")


if __name__ == "__main__":
    main('json')
