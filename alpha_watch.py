#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alpha_watch.py — Binance Alpha 看盘小工具（纯只读）

只做两件事，不碰钱包、不下单、不收集任何私钥：
  1. rank    按「稳定度」给 Alpha 代币排名，帮你挑刷分损耗小的币
  2. points  按官方积分规则，测算给定交易量能拿多少分
  3. token   查单个 Alpha 代币的行情快照

数据源：币安官方公开接口（无需登录、无需 API Key）
  - 代币列表: /bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list
  - 交易对信息: /bapi/defi/v1/public/alpha-trade/get-exchange-info
  - K 线:      /bapi/defi/v1/public/alpha-trade/klines

依赖：仅 Python 3 标准库（urllib / json / argparse / math），零 pip 安装。

网络要求：需要能访问 www.binance.com 的网络环境。
  如需代理：export https_proxy=http://127.0.0.1:7890 或使用 --proxy 参数。
"""

import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request

BASE = "https://www.binance.com"
TOKEN_LIST_URL = BASE + "/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
EXCHANGE_INFO_URL = BASE + "/bapi/defi/v1/public/alpha-trade/get-exchange-info"
KLINES_URL = BASE + "/bapi/defi/v1/public/alpha-trade/klines"

UA = {"User-Agent": "Mozilla/5.0 (compatible; alpha-watch/1.0)"}
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "points.json")


def _build_opener(proxy):
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener()  # 默认走系统环境变量里的代理


def fetch_json(url, proxy=None, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    try:
        with _build_opener(proxy).open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — 网络错误统一转成中文提示
        raise RuntimeError(f"请求失败: {url}\n原因: {e}\n提示: 需要可访问 www.binance.com 的网络，可用 --proxy 指定代理") from e


def api_data(url, proxy=None, timeout=25):
    body = fetch_json(url, proxy=proxy, timeout=timeout)
    if not isinstance(body, dict) or body.get("code") not in ("000000", 0, None) or body.get("success") is False:
        if isinstance(body, dict) and body.get("code") not in ("000000", 0, None):
            raise RuntimeError(f"接口返回错误: code={body.get('code')} message={body.get('message')}")
    data = body.get("data") if isinstance(body, dict) else body
    return data


def fnum(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def fmt_usd(x):
    if x >= 1_000_000:
        return f"${x / 1_000_000:.1f}M"
    if x >= 1_000:
        return f"${x / 1_000:.1f}K"
    return f"${x:.0f}"


def load_points_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


# ---------------- 代币列表 ----------------

def get_tokens(proxy=None):
    data = api_data(TOKEN_LIST_URL, proxy=proxy)
    tokens = []
    for t in data or []:
        if t.get("offline") or t.get("fullyDelisted"):
            continue
        price = fnum(t.get("price"))
        if price <= 0:
            continue
        high = fnum(t.get("priceHigh24h"))
        low = fnum(t.get("priceLow24h"))
        amp = (high - low) / price * 100 if high > 0 and low > 0 else 999.0
        tokens.append({
            "symbol": t.get("symbol", "?"),
            "name": t.get("name", ""),
            "alpha_id": t.get("alphaId", ""),
            "price": price,
            "amp24h": amp,
            "change24h": fnum(t.get("percentChange24h")),
            "vol24h": fnum(t.get("volume24h")),
            "liquidity": fnum(t.get("liquidity")),
            "mult": int(t.get("mulPoint") or 1),
            "chain": t.get("chainName", ""),
            "count24h": t.get("count24h", "0"),
            "listing_cex": bool(t.get("listingCex")),
        })
    return tokens


def get_klines_symbol_map(proxy=None):
    """alphaId -> 可用于 klines 的交易对 symbol（优先 USDT）"""
    data = api_data(EXCHANGE_INFO_URL, proxy=proxy, timeout=40)
    symbols = data.get("symbols", []) if isinstance(data, dict) else []
    order = {"USDT": 0, "U": 1, "USDC": 2}
    best = {}
    for s in symbols:
        if s.get("status") != "TRADING":
            continue
        base, quote, sym = s.get("baseAsset"), s.get("quoteAsset"), s.get("symbol")
        if quote not in order:
            continue
        if base not in best or order[quote] < order[best[base][1]]:
            best[base] = (sym, quote)
    return {k: v[0] for k, v in best.items()}


def intraday_chop(klines):
    """5 分钟 K 线算日内波动：平均 |涨跌幅| 与单根最大波动"""
    rets, wicks = [], []
    for k in klines:
        try:
            o, h, l, c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
        except (IndexError, ValueError, TypeError):
            continue
        if o <= 0:
            continue
        rets.append(abs(c - o) / o * 100)
        wicks.append((h - l) / o * 100)
    if not rets:
        return None, None
    return sum(rets) / len(rets), max(wicks)


# ---------------- rank ----------------

def cmd_rank(args):
    tokens = get_tokens(proxy=args.proxy)
    tokens = [t for t in tokens if t["vol24h"] >= args.min_vol]
    if args.mult:
        tokens = [t for t in tokens if t["mult"] >= args.mult]
    if args.chain:
        tokens = [t for t in tokens if t["chain"].lower() == args.chain.lower()]
    if not tokens:
        print("没有符合条件的代币（试试放宽 --min-vol / --mult / --chain）。")
        return

    deep_stats = {}
    if args.deep:
        print(f"正在拉取 K 线做深度波动分析（约{min(len(tokens), args.top)} 个币）…", file=sys.stderr)
        sym_map = get_klines_symbol_map(proxy=args.proxy)
        # 先按 24h 振幅粗排，只对头部做 deep
        tokens.sort(key=lambda t: t["amp24h"])
        for t in tokens[:args.top]:
            sym = sym_map.get(t["alpha_id"])
            if not sym:
                continue
            try:
                kl = api_data(f"{KLINES_URL}?symbol={urllib.parse.quote(sym)}&interval=5m&limit=288",
                             proxy=args.proxy)
                avg_ret, max_wick = intraday_chop(kl or [])
                if avg_ret is not None:
                    deep_stats[t["symbol"]] = (avg_ret, max_wick)
            except RuntimeError as e:
                print(f"  跳过 {t['symbol']}: {e}", file=sys.stderr)

    def sort_key(t):
        if args.deep and t["symbol"] in deep_stats:
            avg_ret, max_wick = deep_stats[t["symbol"]]
            return (avg_ret + max_wick / 5, t["amp24h"], -t["vol24h"])
        return (t["amp24h"], -t["vol24h"])

    tokens.sort(key=sort_key)
    rows = tokens[:args.top]

    lines = []
    lines.append(f"# Binance Alpha 稳定度排名（{len(tokens)} 个在架币种中取 Top {len(rows)}）")
    lines.append("")
    head = "| # | 代币 | 价格 | 24h振幅 | 24h交易量 | 流动性 | 积分倍数 | 链 |"
    if args.deep:
        head = "| # | 代币 | 价格 | 24h振幅 | 日内平均波动(5m) | 单根最大影线 | 24h交易量 | 流动性 | 积分倍数 | 链 |"
    lines.append(head)
    lines.append("|" + "---|" * (head.count("|") - 1))
    for i, t in enumerate(rows, 1):
        star = " ⭐" if t["mult"] >= 4 else ""
        base = (f"| {i} | **{t['symbol']}** | {t['price']:.6g} | {t['amp24h']:.2f}% | "
                f"{fmt_usd(t['vol24h'])} | {fmt_usd(t['liquidity'])} | {t['mult']}x{star} | {t['chain']} |")
        if args.deep:
            if t["symbol"] in deep_stats:
                avg_ret, max_wick = deep_stats[t["symbol"]]
                base = (f"| {i} | **{t['symbol']}** | {t['price']:.6g} | {t['amp24h']:.2f}% | "
                        f"{avg_ret:.3f}% | {max_wick:.2f}% | {fmt_usd(t['vol24h'])} | "
                        f"{fmt_usd(t['liquidity'])} | {t['mult']}x{star} | {t['chain']} |")
            else:
                base = base.replace("|", "| - |", 2)  # 占位
        lines.append(base)
    lines.append("")
    lines.append("> 振幅 = (24h最高-24h最低)/现价。振幅越小、交易量越大，刷分时的买卖价差损耗通常越小。")
    lines.append("> 倍数列来自币安官方接口的 mulPoint 字段（⭐ = 4x，同样交易量拿 4 倍积分）。选币前请以 App 内标识为准。")
    lines.append("> 本工具只读公开行情，不构成投资建议；刷分请遵守币安关于 wash trading 的条款。")

    report = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"已写入 {args.out}")
    else:
        print(report)


# ---------------- points ----------------

def volume_points(effective_volume):
    if effective_volume < 2:
        return 0
    return int(math.floor(math.log2(effective_volume / 2))) + 1


def balance_points(balance):
    for threshold, pts in [(100000, 4), (10000, 3), (1000, 2), (100, 1)]:
        if balance >= threshold:
            return pts
    return 0


def cmd_points(args):
    cfg = load_points_config()
    mult = args.mult
    eff = args.volume * mult * (2 if args.double else 1)
    vp = volume_points(eff)
    bp = balance_points(args.balance) if args.balance else 0
    warn = ""
    if args.balance and args.balance < 100:
        warn = "\n⚠️  注意：按官方规则（2025-10-22 起），余额分是 0 时当日交易分不计入总数，请先把合格资产凑到 $100 以上。"
    next_need = 2 ** vp * 2  # 下一分需要的有效交易量
    lines = [
        "# Alpha 积分测算",
        "",
        f"- 计划买入量：${args.volume:,.0f}",
        f"- 代币倍数：{mult}x" + ("（限价单双倍活动再 x2）" if args.double else ""),
        f"- 有效计分交易量：${eff:,.0f}",
        f"- **今日交易分：{vp} 分**" + (f"（距 {vp + 1} 分还差约 ${next_need - eff:,.0f} 有效交易量）" if eff >= 2 else ""),
    ]
    if args.balance:
        lines.append(f"- 余额分：{bp} 分（资产 ${args.balance:,.0f}）")
        lines.append(f"- **今日合计：约 {vp + bp} 分**")
    lines += [
        "",
        "> 规则口径：买入量 $2=1分，每翻一倍多1分（官方 FAQ）；积分按 15 天滚动累计，快照时区 UTC。" + warn,
    ]
    if cfg.get("last_verified"):
        lines.append(f"> 规则最后核对：{cfg['last_verified']}，官方说明：{cfg.get('source', '')}")
    lines.append("> 测算仅供参考，实际以 App 内积分为准。")
    print("\n".join(lines))


# ---------------- token ----------------

def cmd_token(args):
    tokens = get_tokens(proxy=args.proxy)
    key = args.symbol.upper()
    hit = next((t for t in tokens if t["symbol"].upper() == key), None)
    if not hit:
        print(f"没找到 {args.symbol}（可能已下架或不在 Alpha 列表）。")
        return
    print(f"# {hit['symbol']}（{hit['name']}）")
    print(f"- 价格：{hit['price']:.6g}（24h {hit['change24h']:+.2f}%）")
    print(f"- 24h振幅：{hit['amp24h']:.2f}%")
    print(f"- 24h交易量：{fmt_usd(hit['vol24h'])}（{hit['count24h']} 笔）")
    print(f"- 流动性：{fmt_usd(hit['liquidity'])}")
    print(f"- 积分倍数：{hit['mult']}x ｜ 链：{hit['chain']}" + (" ｜ 已上币安现货" if hit["listing_cex"] else ""))


def main():
    ap = argparse.ArgumentParser(description="Binance Alpha 看盘小工具（纯只读，不下单）")
    ap.add_argument("--proxy", default=None, help="代理，如 http://127.0.0.1:7890")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rank", help="按稳定度给 Alpha 代币排名")
    r.add_argument("--top", type=int, default=15, help="显示前 N 名（默认 15）")
    r.add_argument("--min-vol", type=float, default=100000, help="24h交易量下限 USD（默认 100000）")
    r.add_argument("--mult", type=int, default=0, help="只看积分倍数 >= N 的币，如 --mult 4")
    r.add_argument("--chain", default="", help="只看某条链，如 --chain BSC")
    r.add_argument("--deep", action="store_true", help="对头部币种拉 5m K 线做日内波动分析（慢）")
    r.add_argument("--out", default="", help="把报告写到文件（Markdown）")

    p = sub.add_parser("points", help="测算给定交易量能拿多少积分")
    p.add_argument("--volume", type=float, required=True, help="今日计划买入量（USDT，如 1025）")
    p.add_argument("--mult", type=int, default=4, help="代币积分倍数（默认 4，请以 App 内标识为准）")
    p.add_argument("--double", action="store_true", help="限价单/BSC 双倍活动再 x2（以官方公告为准）")
    p.add_argument("--balance", type=float, default=0, help="合格资产总额（USDT），用于算余额分")

    t = sub.add_parser("token", help="查单个代币行情快照")
    t.add_argument("symbol", help="代币符号，如 CT")

    args = ap.parse_args()
    try:
        if args.cmd == "rank":
            cmd_rank(args)
        elif args.cmd == "points":
            cmd_points(args)
        elif args.cmd == "token":
            cmd_token(args)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
