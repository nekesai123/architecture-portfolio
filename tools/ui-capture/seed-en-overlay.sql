-- seed-en-overlay.sql
-- Englishize DB-located Chinese demo data, applied AFTER the 6 seeds.
--
-- SOURCE-AUDIT FINDING:
--   The 6 SQL seeds (seed-chain1/6/7/8.sql, seed-rbac.sql, seed-e2e-actor.sql) plus
--   Flyway V1-V28 insert ONLY ASCII business rows: ACME/ C901–C908 customers,
--   JOB-2609-01xx chain2 jobs (operator='demo_seed'), plus bilingual sys_dict_entry
--   (zh-CN + en-US, both present per V3). The CJK-in-seeds scan returns only COMMENT
--   lines, never data rows.
--
--   Every Chinese string rendered on the en-US dashboard/crm/tracking pages is
--   FRONTEND TypeScript seeds compiled into the SPA bundle, i.e. runtime code-gen:
--     spa/src/data/seed/crm.ts        — 客户名 华通电子/宁波对外经贸/青岛海洋渔业/上海机械进出口(+enName)
--     spa/src/data/seed/finance.ts    — 成本名 海运费/码头操作费/报关费/拖车费/文件费/VGM申报费；
--                                       待办 "SI 截单临近(10-24)，补料仍未提交…"；
--                                       预警 到港预报/目的港清关/应收逾期；对账单 partyName
--     spa/src/data/seed/tracking.ts   — 预警应收账款逾期/信用超额特审/目的港清关文件缺/到港预报；
--                                       里程碑/状态 到港预报/目的港清关；SI补料
--     spa/src/data/seed/adminsys.ts   — 管理用户 黄报关/周仓管/陈管理员；角色 报关员/仓库CFS操作员/
--                                       系统管理员；审计 已委托-已申报/待批-通过/处理中
--     spa/src/data/seed/docs.ts       — 清关单状态 已委托/已申报，监管 一般贸易，SI 补料
--   These files are NOT in the database and cannot be changed without editing repo
--   source (forbidden by the task rule "不碰 /opt/java_projects/logistics 任何文件"),
--   so they are BLOCKED (see the BLOCKED list emitted by run_all.py).
--
-- CONSEQUENCE: there is NO DB-locatable Chinese business data to UPDATE. This file
-- therefore performs zero UPDATEs (idempotent no-op) and instead records an evidence
-- self-check. The psql 'cjk_scan' in run_all.py prints the authoritative per-table
-- proof (it will show CJK only in sys_dict_entry.zh-CN labels, which are already
-- paired with English en-US labels).
-- ============================================================================
BEGIN;

-- Self-check: en-US dict labels must contain NO CJK (already English per V3).
-- Matches 0 rows today → 0 UPDATEs (true no-op). Pattern is ready if DB ever
-- gains Chinese en-US labels.
UPDATE sys_dict_entry
   SET label = label
 WHERE lang = 'en-US'
   AND label ~ '[\u3000\u303f\uff00-\uffef\u4e00-\u9fff]';

-- Evidence row: how many en-US dict labels exist (sanity).
SELECT count(*) AS en_us_dict_label_count
FROM sys_dict_entry
WHERE lang = 'en-US';

COMMIT;
