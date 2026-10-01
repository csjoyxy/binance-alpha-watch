# Binance Alpha 看盘小工具

每天刷 Alpha 积分前，先看一眼哪个币最稳、今天这笔交易量能换多少分。

**纯只读工具**：只调币安官方公开行情接口，不下单、不连钱包、不收集任何私钥/助记词。

> English summary at the bottom.

## 功能

| 命令 | 干嘛用 |
|---|---|
| `python alpha_watch.py rank` | 按**稳定度**给在架 Alpha 代币排名（24h 振幅 + 交易量 + 流动性），标出 4x 积分加成币 |
| `python alpha_watch.py rank --deep` | 对头部币种再拉 5m K 线，算日内平均波动和单根最大影线（更准，稍慢） |
| `python alpha_watch.py points --volume 1025` | 按官方积分规则测算：今天这笔买入量能拿多少交易分 |
| `python alpha_watch.py token BSB` | 查单个币的行情快照 |

## 快速开始

```bash
# 零依赖，只要 Python 3
python alpha_watch.py rank --top 15 --mult 4      # 只看 4x 加成币的稳定度排名
python alpha_watch.py rank --deep --top 5         # 深度波动分析
python alpha_watch.py points --volume 1025 --mult 4 --balance 1500
python alpha_watch.py token DGAI
```

输出是 Markdown 表格，可直接用 `--out report.md` 存成文件。

常用过滤：`--min-vol 100000`（24h 交易量下限，默认 10 万 U）、`--chain BSC`（只看某链）。

### 示例

```
# Binance Alpha 稳定度排名
| # | 代币 | 价格 | 24h振幅 | 24h交易量 | 流动性 | 积分倍数 | 链 |
| 1 | **BSB** | 0.100766 | 4.13% | $1.7M | $1.4M | 4x ⭐ | BSC |
| 2 | **DGAI** | 0.909687 | 4.36% | $9.5M | $3.0M | 4x ⭐ | BSC |
```

```
# Alpha 积分测算
- 计划买入量：$1,025 ｜ 代币倍数：4x ｜ 有效计分交易量：$4,100
- 今日交易分：12 分（距 13 分还差约 $4,092 有效交易量）
- 余额分：2 分 ｜ 今日合计：约 14 分
```

## 积分规则口径（2026-10-01 核对）

- **余额分**：$100–$1,000→1分/天；$1,000–$10,000→2分；$10,000–$100,000→3分；≥$100,000→4分。
  2025-10-22 起：余额分为 0 时，当日交易分不计入总数。
- **交易分**：只统计**买入量**（卖出不扣分）。$2=1分，买入量每翻一倍多1分。
- 带倍数代币（如 4x）按 `买入量 × 倍数` 计分；限价单双倍等活动以币安官方公告为准。
- 15 天滚动累计，快照时区 UTC。规则细节见 [`config/points.json`](config/points.json)，官方说明：https://www.binance.com/en-PH/learn/how-to-earn-and-use-binance-alpha-points

## 网络要求

需要能访问 `www.binance.com` 的网络环境（部分地区需代理）：

```bash
export https_proxy=http://127.0.0.1:7890
# 或
python alpha_watch.py rank --proxy http://127.0.0.1:7890
```

## 安全与合规声明

- 本工具**只读**币安官方公开市场数据接口，不执行任何交易，不请求、不存储任何私钥、助记词或 API Key。
- 币安条款禁止为刷积分而进行 wash trading（对敲刷量），违规可能被清零积分或限制账号。本工具是看盘辅助，不提供自动交易功能，请手动下单并遵守平台规则。
- 输出仅供参考，不构成投资建议；积分规则以币安 App 内实时显示为准。

## License

MIT

---

## English

A read-only CLI helper for Binance Alpha points farmers: ranks listed Alpha tokens by
stability (24h range, volume, liquidity; optional 5m-kline intraday analysis via `--deep`),
flags multiplier tokens (e.g. 4x from Binance's official `mulPoint` field), and estimates
daily Alpha points for a planned buy volume using the official points formula
(`$2 = 1 pt`, +1 pt per doubling; 15-day rolling window).

Zero dependencies — Python 3 stdlib only. No trading, no wallet connection, no keys.
Needs network access to `www.binance.com` (use `--proxy` if required).
