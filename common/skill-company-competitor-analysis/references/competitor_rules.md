# Competitor Relationship Rules

## Core Distinction

`Canonical cycle` means exposure. It does not mean product-market competition.

Example: `2330 台積電` can have `PC_Consumer` exposure in canonical-cycle performance, but it is not a competitor of `2357 華碩`.

## Relationship Types

| relationship_type | Meaning | Include by default |
|---|---|---|
| `brand_competitor` | Competes in end products or branded systems | yes |
| `chip_competitor` | Competes in semiconductor products / IC design end markets | yes |
| `foundry_competitor` | Competes in wafer foundry / semiconductor manufacturing services | yes |
| `server_peer` | Competes or overlaps in server / AI rack / infrastructure systems | yes |
| `odm_peer` | Manufacturing or ODM peer; may not compete as a brand | yes, but label clearly |
| `supplier_or_component` | Upstream component, semiconductor, memory, power, connector, or supplier | no |
| `customer_or_channel` | Downstream customer, retailer, telco, channel, or platform | no |

## Taiwan Supply-Chain Rules

Use `data/ic.tpex.org.tw/raw_SupplyChain_F000.csv`:

- Start from the target company's `F000 電腦及週邊設備` rows.
- Prefer target rows where `位置 = 下游` for end-product peers.
- Match other companies sharing the same downstream `子分類`.
- Treat `上游` rows as supplier/component candidates unless a known brand/server rule overrides them.

For `2357 華碩`, the useful downstream product seeds are:

- `筆記型電腦`
- `桌上型電腦`
- `精簡型電腦`
- `伺服器`
- `其他電腦及週邊設備`

## Default Known Peer Rules

For PC brand targets such as `2357`:

- `brand_competitor`: `2353` Acer, `2376` Gigabyte, `2377` MSI, `DELL`, `HPQ`, `LNVGY`
- `odm_peer`: `2317` Hon Hai, `2324` Compal, `2356` Inventec, `2382` Quanta, `3231` Wistron, `4938` Pegatron
- `server_peer`: `6669` Wiwynn, `2382` Quanta, `3231` Wistron, `2356` Inventec, `2317` Hon Hai, `DELL`, `HPE`
- `supplier_or_component`: `2330` TSMC, `2308` Delta, `2344` Winbond, `2408` Nanya, `2451` Transcend, `8299` Phison unless user explicitly asks for component or supply-chain exposure.



For ODM / cloud-server manufacturing targets such as `2382` Quanta:

- `odm_peer`: `2317` Hon Hai, `2324` Compal, `2356` Inventec, `3231` Wistron, `4938` Pegatron. These are manufacturing/ODM peers and may not compete as brands.
- `server_peer`: `6669` Wiwynn plus server-overlapping ODM peers such as `2317`, `2356`, and `3231` when analyzing cloud server / AI server exposure.
- Do not classify upstream component suppliers such as `2330` TSMC or `2308` Delta as competitors for `2382` unless the user explicitly requests supplier exposure.

For IPC / industrial computer targets such as `2395`:

- `brand_competitor`: `2397` DFI, `2405` FIC, `3022` IEI, `3088` Axiomtek, `3416` Winmate, `3479` Avalue, `3515` ASRock Industrial, `6166` ADLINK, `6245` Lanner, `6414` Ennoconn, `6579` AAEON, `8050` Avalue/Portwell-adjacent IPC peer, `8234` Nexcom when supply-chain data marks shared downstream `工業電腦`.
- Do not blindly apply the PC-brand supplier/component exclusion list to IPC targets. For example, `3022` is an IPC competitor for `2395`, even if it can look like a component/supply-chain company in a PC-brand analysis.


For IC design / connectivity chip targets such as `2379` Realtek:

- `chip_competitor`: `2454` MediaTek, `6526` Airoha, `AVGO` Broadcom, `QCOM` Qualcomm. These overlap in Wi-Fi/connectivity, broadband/networking, mobile/edge connectivity, Ethernet/switching, or adjacent communications IC markets.
- Do not classify foundry, packaging, memory, or downstream device brands as competitors unless the user explicitly asks for supply-chain exposure.

For wafer foundry targets such as `2330` TSMC:

- `foundry_competitor`: `2303` UMC, `GFS` GlobalFoundries, `INTC` Intel Foundry, `0981.HK` SMIC, and `005930.KS` Samsung Foundry.
- `IC設計` / `IP設計` companies are customers or ecosystem partners, not foundry competitors.
- Equipment, materials, testing, packaging, and power suppliers are supply-chain exposure, not product-market competitors.
- `TSM` ADR is the same economic company as `2330`; do not include it as a competitor for `2330`.

If a company matches multiple rules, choose the most specific product-market relationship in this order:

1. `brand_competitor`
2. `chip_competitor`
3. `foundry_competitor`
4. `server_peer`
5. `odm_peer`
6. `supplier_or_component`
7. `customer_or_channel`

## Quarterly Performance Metrics

Taiwan:

- Revenue: `獲利金額_億_營業_收入`
- Gross profit: `獲利金額_億_營業_毛利`
- Profit: `獲利金額_億_營業_利益`
- GM: `獲利率_pct_營業_毛利`, or compute `gross_profit / revenue * 100`
- YoY: same metric vs same quarter one year earlier

US:

- Revenue: `total_revenue`, scaled to `USD 十億`
- Profit: `operating_income`, scaled to `USD 十億`
- GM: `gross_margin * 100` when stored as a ratio
- Revenue YoY: use `revenue_yoy_pct` if present; otherwise compute same fiscal quarter YoY
- Profit YoY: compute same fiscal quarter YoY

Avoid forward estimates unless the user explicitly asks for forecasts.
